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
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.master_data.models import CropTaxonomyImportBatch
from app.modules.master_data.models.crop import CropTaxonomyEdge, CropTaxonomyNode


router = APIRouter(prefix="/api/v1/crop-catalog/csv", tags=["crop-catalog-csv"])

CSV_COLUMNS = [
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
REQUIRED_COLUMNS = {"code", "canonical_name", "node_type", "level"}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000
VALID_NODE_TYPES = {"ROOT", "AGRONOMIC", "ECONOMIC", "BOTANICAL", "GROWTH_HABIT", "SEASONAL", "PROPAGATION"}


def _csv_response(content: str, file_name: str) -> Response:
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


def _write_csv(rows: list[dict]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore")
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
    return _csv_response(_write_csv([row]), "agri-os-crop-taxonomy-template.csv")


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
    return _csv_response(_write_csv([_export_row(db, node_by_id, node) for node in nodes]), f"agri-os-crop-taxonomy-{date_stamp}.csv")


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
    missing = sorted(REQUIRED_COLUMNS - headers)
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
