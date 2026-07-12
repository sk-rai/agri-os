"""CSV validation workflow for crop taxonomy master data.

This module intentionally starts with validate-only behavior. Applying taxonomy
changes has higher blast radius because crops, workflow templates, and project
catalogs can all depend on these nodes. The first admin import step therefore
parses, normalizes, and reports planned changes without mutating data.
"""

from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.master_data.models import CropCatalogImportBatch, CropPropagationImportBatch, CropTaxonomyImportBatch
from app.modules.master_data.models.crop import (
    Crop,
    CropCategory,
    CropPropagationOption,
    CropPropagationType,
    CropTaxonomyAssignment,
    CropTaxonomyEdge,
    CropTaxonomyNode,
)


router = APIRouter(prefix="/api/v1/crop-catalog/csv", tags=["crop-catalog-csv"])

TAXONOMY_CSV_COLUMNS = [
    "code",
    "canonical_name",
    "node_type",
    "level",
    "display_order",
    "parent_codes",
    "description",
    "aliases_json",
    "metadata_json",
]
TAXONOMY_REQUIRED_COLUMNS = {"code", "canonical_name", "node_type", "level"}
PROPAGATION_CSV_COLUMNS = [
    "code",
    "canonical_name",
    "establishment_type",
    "description",
    "aliases_json",
    "metadata_json",
]
PROPAGATION_REQUIRED_COLUMNS = {"code", "canonical_name", "establishment_type"}
CROP_CSV_COLUMNS = [
    "code",
    "category_code",
    "canonical_name",
    "scientific_name",
    "typical_duration_days",
    "suitable_seasons",
    "suitable_soil_types",
    "taxonomy_codes",
    "primary_taxonomy_code",
    "propagation_options",
    "default_propagation_code",
    "description",
    "aliases_json",
]
CROP_REQUIRED_COLUMNS = {"code", "category_code", "canonical_name"}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000
VALID_NODE_TYPES = {"ROOT", "AGRONOMIC", "ECONOMIC", "BOTANICAL", "GROWTH_HABIT", "SEASONAL", "PROPAGATION"}
VALID_ESTABLISHMENT_TYPES = {"SEED", "TRANSPLANT", "VEGETATIVE", "PERENNIAL_PLANTING"}


class CropTaxonomyApplyRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


def _csv_response(content: str, file_name: str) -> Response:
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


def _write_csv(rows: list[dict], fieldnames: list[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _parse_json_field(value: Optional[str], *, expected_type: type, field: str, errors: list[dict]):
    raw = (value or "").strip()
    if not raw:
        return [] if expected_type is list else {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        errors.append({"field": field, "code": "INVALID_JSON", "message": f"{field} must be valid JSON"})
        return [] if expected_type is list else {}
    if not isinstance(parsed, expected_type):
        errors.append({"field": field, "code": "INVALID_JSON_TYPE", "message": f"{field} must be a JSON {expected_type.__name__}"})
        return [] if expected_type is list else {}
    return parsed


def _parent_codes(raw: Optional[str]) -> list[str]:
    return sorted({value.strip().upper() for value in (raw or "").replace(",", "|").split("|") if value.strip()})


def _normalize_row(raw: dict[str, str], row_number: int) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    code = (raw.get("code") or "").strip().upper().replace(" ", "_")
    canonical_name = (raw.get("canonical_name") or "").strip()
    node_type = (raw.get("node_type") or "").strip().upper() or "AGRONOMIC"
    parent_codes = _parent_codes(raw.get("parent_codes"))

    level: Optional[int] = None
    try:
        level = int((raw.get("level") or "").strip())
        if level < 0:
            raise ValueError
    except ValueError:
        errors.append({"field": "level", "code": "INVALID_INTEGER", "message": "level must be a non-negative integer"})

    display_order = 0
    if (raw.get("display_order") or "").strip():
        try:
            display_order = int((raw.get("display_order") or "").strip())
        except ValueError:
            errors.append({"field": "display_order", "code": "INVALID_INTEGER", "message": "display_order must be an integer"})

    aliases = _parse_json_field(raw.get("aliases_json"), expected_type=list, field="aliases_json", errors=errors)
    metadata = _parse_json_field(raw.get("metadata_json"), expected_type=dict, field="metadata_json", errors=errors)

    if not re.fullmatch(r"[A-Z0-9_]{2,50}", code):
        errors.append({"field": "code", "code": "INVALID_CODE", "message": "Use 2-50 uppercase letters, numbers, or underscores"})
    if not canonical_name:
        errors.append({"field": "canonical_name", "code": "REQUIRED", "message": "canonical_name is required"})
    if len(canonical_name) > 150:
        errors.append({"field": "canonical_name", "code": "TOO_LONG", "message": "canonical_name exceeds 150 characters"})
    if node_type not in VALID_NODE_TYPES:
        errors.append({"field": "node_type", "code": "INVALID_NODE_TYPE", "message": f"node_type must be one of: {', '.join(sorted(VALID_NODE_TYPES))}"})
    if code in parent_codes:
        errors.append({"field": "parent_codes", "code": "SELF_PARENT", "message": "A taxonomy node cannot be its own parent"})
    if level == 0 and parent_codes:
        warnings.append({"field": "parent_codes", "code": "ROOT_WITH_PARENT", "message": "Level 0 nodes usually should not have parents"})
    if level and level > 0 and not parent_codes:
        warnings.append({"field": "parent_codes", "code": "NON_ROOT_WITHOUT_PARENT", "message": "Non-root taxonomy node has no parent"})

    normalized = {
        "code": code,
        "canonical_name": canonical_name,
        "node_type": node_type,
        "level": level,
        "display_order": display_order,
        "parent_codes": parent_codes,
        "description": (raw.get("description") or "").strip() or None,
        "aliases": aliases,
        "metadata": metadata,
    }
    return {
        "row_number": row_number,
        "code": code,
        "errors": errors,
        "warnings": warnings,
        "normalized": normalized,
    }


def _node_parent_codes(db: Session, node_by_id: dict, node: CropTaxonomyNode) -> list[str]:
    edges = db.query(CropTaxonomyEdge).filter(CropTaxonomyEdge.child_node_id == node.id, CropTaxonomyEdge.is_active == True).all()
    return sorted(node_by_id[edge.parent_node_id].code for edge in edges if edge.parent_node_id in node_by_id)


def _comparable_node(db: Session, node_by_id: dict, node: CropTaxonomyNode) -> dict:
    return {
        "code": node.code,
        "canonical_name": node.canonical_name,
        "node_type": node.node_type,
        "level": node.level,
        "display_order": node.display_order,
        "parent_codes": _node_parent_codes(db, node_by_id, node),
        "description": node.description,
        "aliases": node.aliases or [],
        "metadata": node.metadata_ or {},
    }


def _export_row(db: Session, node_by_id: dict, node: CropTaxonomyNode) -> dict:
    return {
        "code": node.code,
        "canonical_name": node.canonical_name,
        "node_type": node.node_type,
        "level": node.level,
        "display_order": node.display_order,
        "parent_codes": "|".join(_node_parent_codes(db, node_by_id, node)),
        "description": node.description or "",
        "aliases_json": json.dumps(node.aliases or [], ensure_ascii=False, separators=(",", ":")),
        "metadata_json": json.dumps(node.metadata_ or {}, ensure_ascii=False, separators=(",", ":")),
    }


def _batch_payload(batch: CropTaxonomyImportBatch) -> dict:
    report = batch.validation_report or {}
    return {
        "batch_id": str(batch.id),
        "file_name": batch.file_name,
        "status": batch.status,
        "can_apply": batch.status == "VALIDATED" and report.get("can_apply", False) and batch.expires_at > datetime.now(timezone.utc),
        "expires_at": batch.expires_at.isoformat(),
        "applied_at": batch.applied_at.isoformat() if batch.applied_at else None,
        "created_at": batch.created_at.isoformat(),
        "report": report,
    }


@router.get("/taxonomy/template")
def download_crop_taxonomy_csv_template(
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    row = {
        "code": "EXAMPLE_CROP_GROUP",
        "canonical_name": "Example Crop Group",
        "node_type": "AGRONOMIC",
        "level": "2",
        "display_order": "10",
        "parent_codes": "FIELD_CROP",
        "description": "Example taxonomy node",
        "aliases_json": '[{"lang":"en","name":"Example alias"}]',
        "metadata_json": '{"source":"admin_upload"}',
    }
    return _csv_response(_write_csv([row], TAXONOMY_CSV_COLUMNS), "agri-os-crop-taxonomy-template.csv")


@router.get("/taxonomy/export")
def export_crop_taxonomy_csv(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    query = db.query(CropTaxonomyNode)
    if not include_inactive:
        query = query.filter(CropTaxonomyNode.is_active == True)
    nodes = query.order_by(CropTaxonomyNode.level, CropTaxonomyNode.display_order, CropTaxonomyNode.code).all()
    node_by_id = {node.id: node for node in db.query(CropTaxonomyNode).all()}
    date_stamp = datetime.now(timezone.utc).date().isoformat()
    return _csv_response(_write_csv([_export_row(db, node_by_id, node) for node in nodes], TAXONOMY_CSV_COLUMNS), f"agri-os-crop-taxonomy-{date_stamp}.csv")


@router.post("/taxonomy/validate")
async def validate_crop_taxonomy_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "CSV file exceeds 2 MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV header row is required")
    headers = {header.strip() for header in reader.fieldnames if header}
    missing = sorted(TAXONOMY_REQUIRED_COLUMNS - headers)
    if missing:
        raise HTTPException(400, {"error": "MISSING_COLUMNS", "columns": missing})
    raw_rows = list(reader)
    if not raw_rows:
        raise HTTPException(400, "CSV contains no data rows")
    if len(raw_rows) > MAX_ROWS:
        raise HTTPException(413, f"CSV exceeds {MAX_ROWS} rows")

    rows = [_normalize_row(raw, index) for index, raw in enumerate(raw_rows, start=2)]
    seen: dict[str, int] = {}
    for row in rows:
        code = row["code"]
        if code in seen:
            row["errors"].append({"field": "code", "code": "DUPLICATE_CODE_IN_FILE", "message": f"Code also appears on row {seen[code]}"})
        elif code:
            seen[code] = row["row_number"]

    file_codes = set(seen)
    existing_nodes = db.query(CropTaxonomyNode).filter(CropTaxonomyNode.is_active == True).all()
    existing_by_code = {node.code: node for node in existing_nodes}
    node_by_id = {node.id: node for node in existing_nodes}
    existing_codes = set(existing_by_code)

    for row in rows:
        unknown_parents = sorted(set(row["normalized"]["parent_codes"]) - existing_codes - file_codes)
        if unknown_parents:
            row["errors"].append({"field": "parent_codes", "code": "UNKNOWN_PARENT", "message": f"Unknown parent codes: {', '.join(unknown_parents)}"})

    counts = {"total": len(rows), "create": 0, "update": 0, "unchanged": 0, "invalid": 0, "warnings": 0}
    for row in rows:
        existing = existing_by_code.get(row["code"])
        if row["errors"]:
            row["action"] = "INVALID"
        elif not existing:
            row["action"] = "CREATE"
        elif _comparable_node(db, node_by_id, existing) == row["normalized"]:
            row["action"] = "UNCHANGED"
        else:
            row["action"] = "UPDATE"
        counts[row["action"].lower()] += 1
        counts["warnings"] += len(row["warnings"])

    counts["errors"] = sum(len(row["errors"]) for row in rows)
    can_apply = counts["errors"] == 0
    report = {
        "schema_version": "crop_taxonomy_csv_validation.v1",
        "mode": "VALIDATE_ONLY",
        "file_name": file.filename,
        "can_apply": can_apply,
        "summary": counts,
        "rows": rows,
        "message": "Validation passed. Apply endpoint is intentionally not available yet." if can_apply else "Validation failed. Fix errors and upload again.",
    }
    now = datetime.now(timezone.utc)
    batch = CropTaxonomyImportBatch(
        tenant_id=x_tenant_id,
        actor_id=principal.user_id,
        file_name=(file.filename or "crop-taxonomy.csv")[:255],
        status="VALIDATED" if can_apply else "INVALID",
        normalized_rows=[row["normalized"] for row in rows if not row["errors"]],
        validation_report=report,
        expires_at=now + timedelta(hours=2),
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    db.commit()
    payload = _batch_payload(batch)
    return {**report, "batch_id": payload["batch_id"], "status": payload["status"], "expires_at": payload["expires_at"]}


@router.post("/taxonomy/imports/{batch_id}/apply")
def apply_crop_taxonomy_import(
    batch_id: uuid.UUID,
    body: CropTaxonomyApplyRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    batch = db.query(CropTaxonomyImportBatch).filter(
        CropTaxonomyImportBatch.id == batch_id,
        CropTaxonomyImportBatch.tenant_id == x_tenant_id,
        CropTaxonomyImportBatch.is_active == True,
    ).first()
    if not batch:
        raise HTTPException(404, "Taxonomy import batch not found")
    if batch.status != "VALIDATED":
        raise HTTPException(409, f"Taxonomy import batch status is {batch.status}")
    if batch.expires_at <= datetime.now(timezone.utc):
        batch.status = "EXPIRED"
        batch.updated_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(409, "Taxonomy import batch has expired; validate the CSV again")

    rows = batch.normalized_rows or []
    if not rows:
        raise HTTPException(409, "Taxonomy import batch has no valid rows to apply")

    now = datetime.now(timezone.utc)
    existing_nodes = db.query(CropTaxonomyNode).filter(CropTaxonomyNode.is_active == True).all()
    nodes_by_code = {node.code: node for node in existing_nodes}
    missing_parents = sorted({
        parent_code
        for row in rows
        for parent_code in row.get("parent_codes", [])
        if parent_code not in nodes_by_code and parent_code not in {candidate.get("code") for candidate in rows}
    })
    if missing_parents:
        batch.status = "STALE"
        batch.updated_at = now
        db.commit()
        raise HTTPException(409, f"Taxonomy parents changed since validation: {', '.join(missing_parents)}")

    applied_counts = {"created": 0, "updated": 0, "unchanged": 0, "edges_created": 0, "edges_restored": 0, "edges_disabled": 0}

    # First pass: create/update all nodes so same-file parent references resolve.
    for row in rows:
        code = row["code"]
        node = nodes_by_code.get(code)
        before = None if not node else {
            "canonical_name": node.canonical_name,
            "description": node.description,
            "node_type": node.node_type,
            "level": node.level,
            "display_order": node.display_order,
            "aliases": node.aliases or [],
            "metadata": node.metadata_ or {},
        }
        if not node:
            node = CropTaxonomyNode(code=code, created_at=now, updated_at=now, is_active=True)
            db.add(node)
            nodes_by_code[code] = node
            applied_counts["created"] += 1
        node.canonical_name = row["canonical_name"]
        node.description = row.get("description")
        node.node_type = row["node_type"]
        node.level = row["level"]
        node.display_order = row["display_order"]
        node.aliases = row.get("aliases") or []
        node.metadata_ = row.get("metadata") or {}
        node.updated_at = now
        after = {
            "canonical_name": node.canonical_name,
            "description": node.description,
            "node_type": node.node_type,
            "level": node.level,
            "display_order": node.display_order,
            "aliases": node.aliases or [],
            "metadata": node.metadata_ or {},
        }
        if before is None:
            continue
        if before == after:
            applied_counts["unchanged"] += 1
        else:
            applied_counts["updated"] += 1
    db.flush()

    # Second pass: reconcile parent edges for nodes included in this batch.
    for row in rows:
        child = nodes_by_code[row["code"]]
        desired_parent_ids = {nodes_by_code[parent_code].id for parent_code in row.get("parent_codes", [])}
        current_edges = db.query(CropTaxonomyEdge).filter(CropTaxonomyEdge.child_node_id == child.id).all()
        edge_by_parent = {edge.parent_node_id: edge for edge in current_edges}
        for edge in current_edges:
            if edge.parent_node_id not in desired_parent_ids and edge.is_active:
                edge.is_active = False
                edge.updated_at = now
                applied_counts["edges_disabled"] += 1
        for parent_id in desired_parent_ids:
            edge = edge_by_parent.get(parent_id)
            if edge:
                if not edge.is_active:
                    edge.is_active = True
                    edge.updated_at = now
                    applied_counts["edges_restored"] += 1
                continue
            db.add(CropTaxonomyEdge(
                parent_node_id=parent_id,
                child_node_id=child.id,
                relationship_type="IS_A",
                display_order=0,
                created_at=now,
                updated_at=now,
                is_active=True,
            ))
            applied_counts["edges_created"] += 1

    batch.status = "APPLIED"
    batch.applied_at = now
    batch.updated_at = now
    report = dict(batch.validation_report or {})
    report["applied_counts"] = applied_counts
    report["apply_reason"] = body.reason
    report["applied_by"] = str(principal.user_id)
    batch.validation_report = report
    db.commit()
    return _batch_payload(batch)


# --- Propagation type CSV lifecycle -------------------------------------------------

def _normalize_propagation_row(raw: dict[str, str], row_number: int) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    code = (raw.get("code") or "").strip().upper().replace(" ", "_")
    canonical_name = (raw.get("canonical_name") or "").strip()
    establishment_type = (raw.get("establishment_type") or "").strip().upper()
    aliases = _parse_json_field(raw.get("aliases_json"), expected_type=list, field="aliases_json", errors=errors)
    metadata = _parse_json_field(raw.get("metadata_json"), expected_type=dict, field="metadata_json", errors=errors)
    if not re.fullmatch(r"[A-Z0-9_]{2,50}", code):
        errors.append({"field": "code", "code": "INVALID_CODE", "message": "Use 2-50 uppercase letters, numbers, or underscores"})
    if not canonical_name:
        errors.append({"field": "canonical_name", "code": "REQUIRED", "message": "canonical_name is required"})
    if len(canonical_name) > 150:
        errors.append({"field": "canonical_name", "code": "TOO_LONG", "message": "canonical_name exceeds 150 characters"})
    if establishment_type not in VALID_ESTABLISHMENT_TYPES:
        errors.append({"field": "establishment_type", "code": "INVALID_ESTABLISHMENT_TYPE", "message": f"establishment_type must be one of: {', '.join(sorted(VALID_ESTABLISHMENT_TYPES))}"})
    if not (raw.get("description") or "").strip():
        warnings.append({"field": "description", "code": "MISSING_DESCRIPTION", "message": "Description is recommended for admin clarity"})
    normalized = {
        "code": code,
        "canonical_name": canonical_name,
        "establishment_type": establishment_type,
        "description": (raw.get("description") or "").strip() or None,
        "aliases": aliases,
        "metadata": metadata,
    }
    return {"row_number": row_number, "code": code, "errors": errors, "warnings": warnings, "normalized": normalized}


def _comparable_propagation(item: CropPropagationType) -> dict:
    return {
        "code": item.code,
        "canonical_name": item.canonical_name,
        "establishment_type": item.establishment_type,
        "description": item.description,
        "aliases": item.aliases or [],
        "metadata": item.metadata_ or {},
    }


def _export_propagation_row(item: CropPropagationType) -> dict:
    return {
        "code": item.code,
        "canonical_name": item.canonical_name,
        "establishment_type": item.establishment_type,
        "description": item.description or "",
        "aliases_json": json.dumps(item.aliases or [], ensure_ascii=False, separators=(",", ":")),
        "metadata_json": json.dumps(item.metadata_ or {}, ensure_ascii=False, separators=(",", ":")),
    }


def _propagation_batch_payload(batch: CropPropagationImportBatch) -> dict:
    report = batch.validation_report or {}
    return {
        "batch_id": str(batch.id),
        "file_name": batch.file_name,
        "status": batch.status,
        "can_apply": batch.status == "VALIDATED" and report.get("can_apply", False) and batch.expires_at > datetime.now(timezone.utc),
        "expires_at": batch.expires_at.isoformat(),
        "applied_at": batch.applied_at.isoformat() if batch.applied_at else None,
        "created_at": batch.created_at.isoformat(),
        "report": report,
    }


@router.get("/propagation-types/template")
def download_propagation_csv_template(principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW))):
    row = {
        "code": "EXAMPLE_PROPAGATION",
        "canonical_name": "Example Propagation",
        "establishment_type": "SEED",
        "description": "Example crop establishment method",
        "aliases_json": '[{"lang":"en","name":"Example alias"}]',
        "metadata_json": '{"source":"admin_upload"}',
    }
    return _csv_response(_write_csv([row], PROPAGATION_CSV_COLUMNS), "agri-os-crop-propagation-template.csv")


@router.get("/propagation-types/export")
def export_propagation_csv(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    query = db.query(CropPropagationType)
    if not include_inactive:
        query = query.filter(CropPropagationType.is_active == True)
    items = query.order_by(CropPropagationType.code).all()
    date_stamp = datetime.now(timezone.utc).date().isoformat()
    return _csv_response(_write_csv([_export_propagation_row(item) for item in items], PROPAGATION_CSV_COLUMNS), f"agri-os-crop-propagation-{date_stamp}.csv")


@router.post("/propagation-types/validate")
async def validate_propagation_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "CSV file exceeds 2 MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 encoded")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV header row is required")
    headers = {header.strip() for header in reader.fieldnames if header}
    missing = sorted(PROPAGATION_REQUIRED_COLUMNS - headers)
    if missing:
        raise HTTPException(400, {"error": "MISSING_COLUMNS", "columns": missing})
    raw_rows = list(reader)
    if not raw_rows:
        raise HTTPException(400, "CSV contains no data rows")
    if len(raw_rows) > MAX_ROWS:
        raise HTTPException(413, f"CSV exceeds {MAX_ROWS} rows")
    rows = [_normalize_propagation_row(raw, index) for index, raw in enumerate(raw_rows, start=2)]
    seen: dict[str, int] = {}
    for row in rows:
        code = row["code"]
        if code in seen:
            row["errors"].append({"field": "code", "code": "DUPLICATE_CODE_IN_FILE", "message": f"Code also appears on row {seen[code]}"})
        elif code:
            seen[code] = row["row_number"]
    existing_by_code = {item.code: item for item in db.query(CropPropagationType).filter(CropPropagationType.code.in_(list(seen))).all()} if seen else {}
    counts = {"total": len(rows), "create": 0, "update": 0, "unchanged": 0, "invalid": 0, "warnings": 0}
    for row in rows:
        existing = existing_by_code.get(row["code"])
        if row["errors"]:
            row["action"] = "INVALID"
        elif not existing:
            row["action"] = "CREATE"
        elif _comparable_propagation(existing) == row["normalized"]:
            row["action"] = "UNCHANGED"
        else:
            row["action"] = "UPDATE"
        counts[row["action"].lower()] += 1
        counts["warnings"] += len(row["warnings"])
    counts["errors"] = sum(len(row["errors"]) for row in rows)
    can_apply = counts["errors"] == 0
    report = {
        "schema_version": "crop_propagation_csv_validation.v1",
        "mode": "VALIDATE_ONLY",
        "file_name": file.filename,
        "can_apply": can_apply,
        "summary": counts,
        "rows": rows,
        "message": "Validation passed. Batch can be applied." if can_apply else "Validation failed. Fix errors and upload again.",
    }
    now = datetime.now(timezone.utc)
    batch = CropPropagationImportBatch(
        tenant_id=x_tenant_id,
        actor_id=principal.user_id,
        file_name=(file.filename or "crop-propagation.csv")[:255],
        status="VALIDATED" if can_apply else "INVALID",
        normalized_rows=[row["normalized"] for row in rows if not row["errors"]],
        validation_report=report,
        expires_at=now + timedelta(hours=2),
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    db.commit()
    payload = _propagation_batch_payload(batch)
    return {**report, "batch_id": payload["batch_id"], "status": payload["status"], "expires_at": payload["expires_at"]}


@router.post("/propagation-types/imports/{batch_id}/apply")
def apply_propagation_import(
    batch_id: uuid.UUID,
    body: CropTaxonomyApplyRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    batch = db.query(CropPropagationImportBatch).filter(CropPropagationImportBatch.id == batch_id, CropPropagationImportBatch.tenant_id == x_tenant_id, CropPropagationImportBatch.is_active == True).first()
    if not batch:
        raise HTTPException(404, "Propagation import batch not found")
    if batch.status != "VALIDATED":
        raise HTTPException(409, f"Propagation import batch status is {batch.status}")
    if batch.expires_at <= datetime.now(timezone.utc):
        batch.status = "EXPIRED"
        batch.updated_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(409, "Propagation import batch has expired; validate the CSV again")
    rows = batch.normalized_rows or []
    if not rows:
        raise HTTPException(409, "Propagation import batch has no valid rows to apply")
    now = datetime.now(timezone.utc)
    existing_by_code = {item.code: item for item in db.query(CropPropagationType).filter(CropPropagationType.is_active == True).all()}
    applied_counts = {"created": 0, "updated": 0, "unchanged": 0}
    for row in rows:
        item = existing_by_code.get(row["code"])
        before = _comparable_propagation(item) if item else None
        if not item:
            item = CropPropagationType(code=row["code"], created_at=now, updated_at=now, is_active=True)
            db.add(item)
            existing_by_code[item.code] = item
            applied_counts["created"] += 1
        item.canonical_name = row["canonical_name"]
        item.establishment_type = row["establishment_type"]
        item.description = row.get("description")
        item.aliases = row.get("aliases") or []
        item.metadata_ = row.get("metadata") or {}
        item.updated_at = now
        if before is None:
            continue
        after = _comparable_propagation(item)
        if before == after:
            applied_counts["unchanged"] += 1
        else:
            applied_counts["updated"] += 1
    batch.status = "APPLIED"
    batch.applied_at = now
    batch.updated_at = now
    report = dict(batch.validation_report or {})
    report["applied_counts"] = applied_counts
    report["apply_reason"] = body.reason
    report["applied_by"] = str(principal.user_id)
    batch.validation_report = report
    db.commit()
    return _propagation_batch_payload(batch)


@router.get("/propagation-types/imports")
def list_propagation_imports(
    limit: int = Query(30, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(VALIDATED|INVALID|APPLIED|EXPIRED|STALE)$"),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    query = db.query(CropPropagationImportBatch).filter(CropPropagationImportBatch.tenant_id == x_tenant_id, CropPropagationImportBatch.is_active == True)
    if status:
        query = query.filter(CropPropagationImportBatch.status == status.upper())
    batches = query.order_by(CropPropagationImportBatch.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "crop_propagation_imports.v1",
        "tenant_id": x_tenant_id,
        "status": status.upper() if status else None,
        "count": len(batches),
        "imports": [_propagation_batch_payload(batch) for batch in batches],
    }


@router.get("/taxonomy/imports")
def list_crop_taxonomy_imports(
    limit: int = Query(30, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(VALIDATED|INVALID|APPLIED|EXPIRED|STALE)$"),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    query = db.query(CropTaxonomyImportBatch).filter(
        CropTaxonomyImportBatch.tenant_id == x_tenant_id,
        CropTaxonomyImportBatch.is_active == True,
    )
    if status:
        query = query.filter(CropTaxonomyImportBatch.status == status.upper())
    batches = query.order_by(CropTaxonomyImportBatch.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "crop_taxonomy_imports.v1",
        "tenant_id": x_tenant_id,
        "status": status.upper() if status else None,
        "count": len(batches),
        "imports": [_batch_payload(batch) for batch in batches],
    }


# --- Crop catalog CSV lifecycle ------------------------------------------------------

def _split_codes(raw: Optional[str]) -> list[str]:
    return sorted({value.strip().upper().replace(" ", "_") for value in (raw or "").replace(",", "|").split("|") if value.strip()})


def _normalize_crop_row(raw: dict[str, str], row_number: int) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    code = (raw.get("code") or "").strip().upper().replace(" ", "_")
    category_code = (raw.get("category_code") or "").strip().upper().replace(" ", "_")
    canonical_name = (raw.get("canonical_name") or "").strip()
    taxonomy_codes = _split_codes(raw.get("taxonomy_codes"))
    propagation_options = _split_codes(raw.get("propagation_options"))
    primary_taxonomy_code = (raw.get("primary_taxonomy_code") or "").strip().upper().replace(" ", "_") or (taxonomy_codes[0] if taxonomy_codes else None)
    default_propagation_code = (raw.get("default_propagation_code") or "").strip().upper().replace(" ", "_") or (propagation_options[0] if propagation_options else None)
    aliases = _parse_json_field(raw.get("aliases_json"), expected_type=list, field="aliases_json", errors=errors)

    typical_duration_days: Optional[int] = None
    if (raw.get("typical_duration_days") or "").strip():
        try:
            typical_duration_days = int((raw.get("typical_duration_days") or "").strip())
            if typical_duration_days <= 0:
                raise ValueError
        except ValueError:
            errors.append({"field": "typical_duration_days", "code": "INVALID_INTEGER", "message": "typical_duration_days must be a positive integer"})

    if not re.fullmatch(r"[A-Z0-9_]{2,30}", code):
        errors.append({"field": "code", "code": "INVALID_CODE", "message": "Use 2-30 uppercase letters, numbers, or underscores"})
    if not re.fullmatch(r"[A-Z0-9_]{2,30}", category_code):
        errors.append({"field": "category_code", "code": "INVALID_CATEGORY_CODE", "message": "category_code must reference an existing crop category code"})
    if not canonical_name:
        errors.append({"field": "canonical_name", "code": "REQUIRED", "message": "canonical_name is required"})
    if len(canonical_name) > 100:
        errors.append({"field": "canonical_name", "code": "TOO_LONG", "message": "canonical_name exceeds 100 characters"})
    if len((raw.get("scientific_name") or "").strip()) > 150:
        errors.append({"field": "scientific_name", "code": "TOO_LONG", "message": "scientific_name exceeds 150 characters"})
    if primary_taxonomy_code and primary_taxonomy_code not in taxonomy_codes:
        errors.append({"field": "primary_taxonomy_code", "code": "PRIMARY_NOT_IN_TAXONOMY_CODES", "message": "primary_taxonomy_code must be included in taxonomy_codes"})
    if default_propagation_code and default_propagation_code not in propagation_options:
        errors.append({"field": "default_propagation_code", "code": "DEFAULT_NOT_IN_PROPAGATION_OPTIONS", "message": "default_propagation_code must be included in propagation_options"})
    if not taxonomy_codes:
        warnings.append({"field": "taxonomy_codes", "code": "MISSING_TAXONOMY", "message": "Crop has no taxonomy assignments"})
    if not propagation_options:
        warnings.append({"field": "propagation_options", "code": "MISSING_PROPAGATION", "message": "Crop has no propagation options"})

    normalized = {
        "code": code,
        "category_code": category_code,
        "canonical_name": canonical_name,
        "scientific_name": (raw.get("scientific_name") or "").strip() or None,
        "typical_duration_days": typical_duration_days,
        "suitable_seasons": _split_codes(raw.get("suitable_seasons")),
        "suitable_soil_types": _split_codes(raw.get("suitable_soil_types")),
        "taxonomy_codes": taxonomy_codes,
        "primary_taxonomy_code": primary_taxonomy_code,
        "propagation_options": propagation_options,
        "default_propagation_code": default_propagation_code,
        "description": (raw.get("description") or "").strip() or None,
        "aliases": aliases,
    }
    return {"row_number": row_number, "code": code, "errors": errors, "warnings": warnings, "normalized": normalized}


def _crop_taxonomy_state(db: Session, crop: Crop) -> tuple[list[str], Optional[str]]:
    rows = db.query(CropTaxonomyAssignment, CropTaxonomyNode).join(
        CropTaxonomyNode,
        CropTaxonomyNode.id == CropTaxonomyAssignment.taxonomy_node_id,
    ).filter(
        CropTaxonomyAssignment.crop_id == crop.id,
        CropTaxonomyAssignment.is_active == True,
        CropTaxonomyNode.is_active == True,
    ).all()
    codes = sorted({node.code for assignment, node in rows})
    primary = next((node.code for assignment, node in rows if assignment.is_primary), None)
    return codes, primary


def _crop_propagation_state(db: Session, crop: Crop) -> tuple[list[str], Optional[str]]:
    rows = db.query(CropPropagationOption, CropPropagationType).join(
        CropPropagationType,
        CropPropagationType.id == CropPropagationOption.propagation_type_id,
    ).filter(
        CropPropagationOption.crop_id == crop.id,
        CropPropagationOption.season_code.is_(None),
        CropPropagationOption.is_active == True,
        CropPropagationType.is_active == True,
    ).all()
    codes = sorted({ptype.code for option, ptype in rows})
    default = next((ptype.code for option, ptype in rows if option.is_default), None)
    return codes, default


def _comparable_crop(db: Session, crop: Crop) -> dict:
    taxonomy_codes, primary_taxonomy_code = _crop_taxonomy_state(db, crop)
    propagation_codes, default_propagation_code = _crop_propagation_state(db, crop)
    return {
        "code": crop.code,
        "category_code": crop.category.code if crop.category else None,
        "canonical_name": crop.canonical_name,
        "scientific_name": crop.scientific_name,
        "typical_duration_days": crop.typical_duration_days,
        "suitable_seasons": sorted(crop.suitable_seasons or []),
        "suitable_soil_types": sorted(crop.suitable_soil_types or []),
        "taxonomy_codes": taxonomy_codes,
        "primary_taxonomy_code": primary_taxonomy_code,
        "propagation_options": propagation_codes,
        "default_propagation_code": default_propagation_code,
        "description": crop.description,
        "aliases": crop.aliases or [],
    }


def _export_crop_row(db: Session, crop: Crop) -> dict:
    taxonomy_codes, primary_taxonomy_code = _crop_taxonomy_state(db, crop)
    propagation_codes, default_propagation_code = _crop_propagation_state(db, crop)
    return {
        "code": crop.code,
        "category_code": crop.category.code if crop.category else "",
        "canonical_name": crop.canonical_name,
        "scientific_name": crop.scientific_name or "",
        "typical_duration_days": crop.typical_duration_days or "",
        "suitable_seasons": "|".join(sorted(crop.suitable_seasons or [])),
        "suitable_soil_types": "|".join(sorted(crop.suitable_soil_types or [])),
        "taxonomy_codes": "|".join(taxonomy_codes),
        "primary_taxonomy_code": primary_taxonomy_code or "",
        "propagation_options": "|".join(propagation_codes),
        "default_propagation_code": default_propagation_code or "",
        "description": crop.description or "",
        "aliases_json": json.dumps(crop.aliases or [], ensure_ascii=False, separators=(",", ":")),
    }


def _crop_batch_payload(batch: CropCatalogImportBatch) -> dict:
    report = batch.validation_report or {}
    return {
        "batch_id": str(batch.id),
        "file_name": batch.file_name,
        "status": batch.status,
        "can_apply": batch.status == "VALIDATED" and report.get("can_apply", False) and batch.expires_at > datetime.now(timezone.utc),
        "expires_at": batch.expires_at.isoformat(),
        "applied_at": batch.applied_at.isoformat() if batch.applied_at else None,
        "created_at": batch.created_at.isoformat(),
        "report": report,
    }


@router.get("/crops/template")
def download_crops_csv_template(principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW))):
    row = {
        "code": "EXAMPLE_CROP",
        "category_code": "CEREALS",
        "canonical_name": "Example Crop",
        "scientific_name": "Example scientific name",
        "typical_duration_days": "120",
        "suitable_seasons": "KHARIF|RABI",
        "suitable_soil_types": "LOAM|CLAY",
        "taxonomy_codes": "FIELD_CROP|CEREAL",
        "primary_taxonomy_code": "FIELD_CROP",
        "propagation_options": "DIRECT_SEEDED|NURSERY_TRANSPLANT",
        "default_propagation_code": "DIRECT_SEEDED",
        "description": "Example crop row",
        "aliases_json": '[{"lang":"en","name":"Example alias"}]',
    }
    return _csv_response(_write_csv([row], CROP_CSV_COLUMNS), "agri-os-crops-template.csv")


@router.get("/crops/export")
def export_crops_csv(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    query = db.query(Crop)
    if not include_inactive:
        query = query.filter(Crop.is_active == True)
    crops = query.order_by(Crop.code).all()
    date_stamp = datetime.now(timezone.utc).date().isoformat()
    return _csv_response(_write_csv([_export_crop_row(db, crop) for crop in crops], CROP_CSV_COLUMNS), f"agri-os-crops-{date_stamp}.csv")


@router.post("/crops/validate")
async def validate_crops_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "CSV file exceeds 2 MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 encoded")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV header row is required")
    headers = {header.strip() for header in reader.fieldnames if header}
    missing = sorted(CROP_REQUIRED_COLUMNS - headers)
    if missing:
        raise HTTPException(400, {"error": "MISSING_COLUMNS", "columns": missing})
    raw_rows = list(reader)
    if not raw_rows:
        raise HTTPException(400, "CSV contains no data rows")
    if len(raw_rows) > MAX_ROWS:
        raise HTTPException(413, f"CSV exceeds {MAX_ROWS} rows")

    rows = [_normalize_crop_row(raw, index) for index, raw in enumerate(raw_rows, start=2)]
    seen: dict[str, int] = {}
    for row in rows:
        code = row["code"]
        if code in seen:
            row["errors"].append({"field": "code", "code": "DUPLICATE_CODE_IN_FILE", "message": f"Code also appears on row {seen[code]}"})
        elif code:
            seen[code] = row["row_number"]

    categories_by_code = {item.code: item for item in db.query(CropCategory).filter(CropCategory.is_active == True).all()}
    taxonomy_by_code = {item.code: item for item in db.query(CropTaxonomyNode).filter(CropTaxonomyNode.is_active == True).all()}
    propagation_by_code = {item.code: item for item in db.query(CropPropagationType).filter(CropPropagationType.is_active == True).all()}
    existing_by_code = {item.code: item for item in db.query(Crop).filter(Crop.code.in_(list(seen))).all()} if seen else {}

    for row in rows:
        normalized = row["normalized"]
        if normalized["category_code"] not in categories_by_code:
            row["errors"].append({"field": "category_code", "code": "UNKNOWN_CATEGORY", "message": f"Unknown crop category: {normalized['category_code']}"})
        missing_taxonomy = sorted(set(normalized["taxonomy_codes"]) - set(taxonomy_by_code))
        if missing_taxonomy:
            row["errors"].append({"field": "taxonomy_codes", "code": "UNKNOWN_TAXONOMY", "message": f"Unknown taxonomy codes: {', '.join(missing_taxonomy)}"})
        missing_propagation = sorted(set(normalized["propagation_options"]) - set(propagation_by_code))
        if missing_propagation:
            row["errors"].append({"field": "propagation_options", "code": "UNKNOWN_PROPAGATION", "message": f"Unknown propagation codes: {', '.join(missing_propagation)}"})

    counts = {"total": len(rows), "create": 0, "update": 0, "unchanged": 0, "invalid": 0, "warnings": 0}
    for row in rows:
        existing = existing_by_code.get(row["code"])
        if row["errors"]:
            row["action"] = "INVALID"
        elif not existing:
            row["action"] = "CREATE"
        elif _comparable_crop(db, existing) == row["normalized"]:
            row["action"] = "UNCHANGED"
        else:
            row["action"] = "UPDATE"
        counts[row["action"].lower()] += 1
        counts["warnings"] += len(row["warnings"])
    counts["errors"] = sum(len(row["errors"]) for row in rows)
    can_apply = counts["errors"] == 0
    report = {
        "schema_version": "crop_catalog_csv_validation.v1",
        "mode": "VALIDATE_ONLY",
        "file_name": file.filename,
        "can_apply": can_apply,
        "summary": counts,
        "rows": rows,
        "message": "Validation passed. Batch can be applied." if can_apply else "Validation failed. Fix errors and upload again.",
    }
    now = datetime.now(timezone.utc)
    batch = CropCatalogImportBatch(
        tenant_id=x_tenant_id,
        actor_id=principal.user_id,
        file_name=(file.filename or "crops.csv")[:255],
        status="VALIDATED" if can_apply else "INVALID",
        normalized_rows=[row["normalized"] for row in rows if not row["errors"]],
        validation_report=report,
        expires_at=now + timedelta(hours=2),
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    db.commit()
    payload = _crop_batch_payload(batch)
    return {**report, "batch_id": payload["batch_id"], "status": payload["status"], "expires_at": payload["expires_at"]}


@router.post("/crops/imports/{batch_id}/apply")
def apply_crops_import(
    batch_id: uuid.UUID,
    body: CropTaxonomyApplyRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    batch = db.query(CropCatalogImportBatch).filter(CropCatalogImportBatch.id == batch_id, CropCatalogImportBatch.tenant_id == x_tenant_id, CropCatalogImportBatch.is_active == True).first()
    if not batch:
        raise HTTPException(404, "Crop import batch not found")
    if batch.status != "VALIDATED":
        raise HTTPException(409, f"Crop import batch status is {batch.status}")
    if batch.expires_at <= datetime.now(timezone.utc):
        batch.status = "EXPIRED"
        batch.updated_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(409, "Crop import batch has expired; validate the CSV again")
    rows = batch.normalized_rows or []
    if not rows:
        raise HTTPException(409, "Crop import batch has no valid rows to apply")

    now = datetime.now(timezone.utc)
    categories_by_code = {item.code: item for item in db.query(CropCategory).filter(CropCategory.is_active == True).all()}
    taxonomy_by_code = {item.code: item for item in db.query(CropTaxonomyNode).filter(CropTaxonomyNode.is_active == True).all()}
    propagation_by_code = {item.code: item for item in db.query(CropPropagationType).filter(CropPropagationType.is_active == True).all()}
    stale_categories = sorted({row["category_code"] for row in rows if row["category_code"] not in categories_by_code})
    stale_taxonomy = sorted({code for row in rows for code in row.get("taxonomy_codes", []) if code not in taxonomy_by_code})
    stale_propagation = sorted({code for row in rows for code in row.get("propagation_options", []) if code not in propagation_by_code})
    if stale_categories or stale_taxonomy or stale_propagation:
        batch.status = "STALE"
        batch.updated_at = now
        db.commit()
        raise HTTPException(409, {"error": "STALE_REFERENCES", "categories": stale_categories, "taxonomy": stale_taxonomy, "propagation": stale_propagation})

    existing_by_code = {item.code: item for item in db.query(Crop).filter(Crop.code.in_([row["code"] for row in rows])).all()}
    applied_counts = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "taxonomy_assignments_created": 0,
        "taxonomy_assignments_restored": 0,
        "taxonomy_assignments_disabled": 0,
        "propagation_options_created": 0,
        "propagation_options_restored": 0,
        "propagation_options_disabled": 0,
    }

    for row in rows:
        crop = existing_by_code.get(row["code"])
        before = _comparable_crop(db, crop) if crop else None
        if not crop:
            crop = Crop(code=row["code"], created_at=now, updated_at=now, is_active=True)
            db.add(crop)
            existing_by_code[crop.code] = crop
            applied_counts["created"] += 1
        crop.category = categories_by_code[row["category_code"]]
        crop.canonical_name = row["canonical_name"]
        crop.scientific_name = row.get("scientific_name")
        crop.typical_duration_days = row.get("typical_duration_days")
        crop.suitable_seasons = row.get("suitable_seasons") or []
        crop.suitable_soil_types = row.get("suitable_soil_types") or []
        crop.description = row.get("description")
        crop.aliases = row.get("aliases") or []
        crop.is_active = True
        crop.updated_at = now
        db.flush()

        desired_taxonomy_ids = {taxonomy_by_code[code].id for code in row.get("taxonomy_codes", [])}
        primary_taxonomy_id = taxonomy_by_code[row["primary_taxonomy_code"]].id if row.get("primary_taxonomy_code") else None
        assignments = db.query(CropTaxonomyAssignment).filter(CropTaxonomyAssignment.crop_id == crop.id).all()
        assignment_by_node = {assignment.taxonomy_node_id: assignment for assignment in assignments}
        for assignment in assignments:
            if assignment.taxonomy_node_id not in desired_taxonomy_ids and assignment.is_active:
                assignment.is_active = False
                assignment.updated_at = now
                applied_counts["taxonomy_assignments_disabled"] += 1
        for taxonomy_id in desired_taxonomy_ids:
            assignment = assignment_by_node.get(taxonomy_id)
            is_primary = taxonomy_id == primary_taxonomy_id
            if assignment:
                if not assignment.is_active:
                    applied_counts["taxonomy_assignments_restored"] += 1
                assignment.is_active = True
                assignment.assignment_type = "PRIMARY" if is_primary else "SECONDARY"
                assignment.is_primary = is_primary
                assignment.source = "CSV_IMPORT"
                assignment.updated_at = now
            else:
                db.add(CropTaxonomyAssignment(
                    crop_id=crop.id,
                    taxonomy_node_id=taxonomy_id,
                    assignment_type="PRIMARY" if is_primary else "SECONDARY",
                    is_primary=is_primary,
                    source="CSV_IMPORT",
                    created_at=now,
                    updated_at=now,
                    is_active=True,
                ))
                applied_counts["taxonomy_assignments_created"] += 1

        desired_propagation_ids = {propagation_by_code[code].id for code in row.get("propagation_options", [])}
        default_propagation_id = propagation_by_code[row["default_propagation_code"]].id if row.get("default_propagation_code") else None
        options = db.query(CropPropagationOption).filter(CropPropagationOption.crop_id == crop.id, CropPropagationOption.season_code.is_(None)).all()
        option_by_type = {option.propagation_type_id: option for option in options}
        for option in options:
            if option.propagation_type_id not in desired_propagation_ids and option.is_active:
                option.is_active = False
                option.updated_at = now
                applied_counts["propagation_options_disabled"] += 1
        for propagation_id in desired_propagation_ids:
            option = option_by_type.get(propagation_id)
            is_default = propagation_id == default_propagation_id
            if option:
                if not option.is_active:
                    applied_counts["propagation_options_restored"] += 1
                option.is_active = True
                option.is_default = is_default
                option.updated_at = now
            else:
                db.add(CropPropagationOption(
                    crop_id=crop.id,
                    propagation_type_id=propagation_id,
                    season_code=None,
                    is_default=is_default,
                    metadata_={"source": "CSV_IMPORT"},
                    created_at=now,
                    updated_at=now,
                    is_active=True,
                ))
                applied_counts["propagation_options_created"] += 1
        db.flush()
        if before is None:
            continue
        after = _comparable_crop(db, crop)
        if before == after:
            applied_counts["unchanged"] += 1
        else:
            applied_counts["updated"] += 1

    batch.status = "APPLIED"
    batch.applied_at = now
    batch.updated_at = now
    report = dict(batch.validation_report or {})
    report["applied_counts"] = applied_counts
    report["apply_reason"] = body.reason
    report["applied_by"] = str(principal.user_id)
    batch.validation_report = report
    db.commit()
    return _crop_batch_payload(batch)


@router.get("/crops/imports")
def list_crop_imports(
    limit: int = Query(30, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(VALIDATED|INVALID|APPLIED|EXPIRED|STALE)$"),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    query = db.query(CropCatalogImportBatch).filter(CropCatalogImportBatch.tenant_id == x_tenant_id, CropCatalogImportBatch.is_active == True)
    if status:
        query = query.filter(CropCatalogImportBatch.status == status.upper())
    batches = query.order_by(CropCatalogImportBatch.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "crop_catalog_imports.v1",
        "tenant_id": x_tenant_id,
        "status": status.upper() if status else None,
        "count": len(batches),
        "imports": [_crop_batch_payload(batch) for batch in batches],
    }
