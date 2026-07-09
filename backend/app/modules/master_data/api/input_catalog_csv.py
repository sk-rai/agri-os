"""CSV import/export workflow for agricultural input master data."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import io
import json
import re
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.master_data.api.input_catalog import _record_input_audit, input_payload
from app.modules.master_data.models import (
    AgriculturalInput,
    InputCatalogImportBatch,
    InputCategory,
)
from app.modules.master_data.models.crop import Crop


router = APIRouter(prefix="/api/v1/input-catalog/csv", tags=["input-catalog-csv"])

CSV_COLUMNS = [
    "code",
    "category_code",
    "canonical_name",
    "brand_name",
    "composition",
    "unit",
    "standard_weight",
    "applicable_crops",
    "application_method",
    "safety_instructions",
    "aliases_json",
]
REQUIRED_COLUMNS = {"code", "category_code", "canonical_name", "unit"}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000


class InputCsvApplyRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


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


def _export_row(item: AgriculturalInput) -> dict:
    return {
        "code": item.code,
        "category_code": item.category.code if item.category else "",
        "canonical_name": item.canonical_name,
        "brand_name": item.brand_name or "",
        "composition": item.composition or "",
        "unit": item.unit,
        "standard_weight": str(item.standard_weight) if item.standard_weight is not None else "",
        "applicable_crops": "|".join(item.applicable_crops or []),
        "application_method": item.application_method or "",
        "safety_instructions": item.safety_instructions or "",
        "aliases_json": json.dumps(item.aliases or [], ensure_ascii=False, separators=(",", ":")),
    }


def _nullable(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def _normalize_row(raw: dict[str, str], row_number: int, categories: set[str], crops: set[str]) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    code = (raw.get("code") or "").strip().upper().replace(" ", "_")
    category_code = (raw.get("category_code") or "").strip().upper()
    canonical_name = (raw.get("canonical_name") or "").strip()
    unit = (raw.get("unit") or "").strip()
    crop_codes = sorted({
        value.strip().upper()
        for value in (raw.get("applicable_crops") or "").replace(",", "|").split("|")
        if value.strip()
    })
    aliases = []
    aliases_raw = (raw.get("aliases_json") or "").strip()
    if aliases_raw:
        try:
            aliases = json.loads(aliases_raw)
            if not isinstance(aliases, list) or not all(isinstance(value, dict) for value in aliases):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            errors.append({"field": "aliases_json", "code": "INVALID_JSON_ARRAY", "message": "aliases_json must be a JSON array of objects"})
            aliases = []
    standard_weight = _nullable(raw.get("standard_weight"))
    if standard_weight is not None:
        try:
            parsed_weight = Decimal(standard_weight)
            if parsed_weight < 0:
                raise InvalidOperation
            standard_weight = str(parsed_weight)
        except (InvalidOperation, ValueError):
            errors.append({"field": "standard_weight", "code": "INVALID_NUMBER", "message": "standard_weight must be non-negative"})
            standard_weight = None
    if not re.fullmatch(r"[A-Z0-9_]{2,50}", code):
        errors.append({"field": "code", "code": "INVALID_CODE", "message": "Use 2-50 uppercase letters, numbers, or underscores"})
    if category_code not in categories:
        errors.append({"field": "category_code", "code": "UNKNOWN_CATEGORY", "message": f"Unknown category {category_code or '-'}"})
    if not canonical_name:
        errors.append({"field": "canonical_name", "code": "REQUIRED", "message": "canonical_name is required"})
    if len(canonical_name) > 200:
        errors.append({"field": "canonical_name", "code": "TOO_LONG", "message": "canonical_name exceeds 200 characters"})
    if not unit:
        errors.append({"field": "unit", "code": "REQUIRED", "message": "unit is required"})
    if len(unit) > 20:
        errors.append({"field": "unit", "code": "TOO_LONG", "message": "unit exceeds 20 characters"})
    unknown_crops = sorted(set(crop_codes) - crops)
    if unknown_crops:
        errors.append({"field": "applicable_crops", "code": "UNKNOWN_CROP", "message": f"Unknown crops: {', '.join(unknown_crops)}"})
    if not crop_codes:
        warnings.append({"field": "applicable_crops", "code": "ALL_CROPS", "message": "Empty crop scope means generally applicable"})
    normalized = {
        "code": code,
        "category_code": category_code,
        "canonical_name": canonical_name,
        "brand_name": _nullable(raw.get("brand_name")),
        "composition": _nullable(raw.get("composition")),
        "unit": unit,
        "standard_weight": standard_weight,
        "applicable_crops": crop_codes,
        "application_method": _nullable(raw.get("application_method")),
        "safety_instructions": _nullable(raw.get("safety_instructions")),
        "aliases": aliases,
    }
    return {
        "row_number": row_number,
        "code": code,
        "errors": errors,
        "warnings": warnings,
        "normalized": normalized,
    }


def _comparable_payload(item: AgriculturalInput) -> dict:
    return {
        "code": item.code,
        "category_code": item.category.code if item.category else None,
        "canonical_name": item.canonical_name,
        "brand_name": item.brand_name,
        "composition": item.composition,
        "unit": item.unit,
        "standard_weight": str(item.standard_weight) if item.standard_weight is not None else None,
        "applicable_crops": sorted(item.applicable_crops or []),
        "application_method": item.application_method,
        "safety_instructions": item.safety_instructions,
        "aliases": item.aliases or [],
    }


def _batch_payload(batch: InputCatalogImportBatch) -> dict:
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


@router.get("/template")
def download_input_csv_template(
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    row = {
        "code": "EXAMPLE_INPUT_CODE",
        "category_code": "FERTILIZER",
        "canonical_name": "Example Input",
        "brand_name": "",
        "composition": "Example composition",
        "unit": "kg",
        "standard_weight": "50",
        "applicable_crops": "RICE|WHEAT",
        "application_method": "Apply as recommended",
        "safety_instructions": "Follow label instructions",
        "aliases_json": '[{"lang":"en","name":"Example alias"}]',
    }
    return _csv_response(_write_csv([row]), "agri-os-input-catalog-template.csv")


@router.get("/export")
def export_input_catalog_csv(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    query = db.query(AgriculturalInput).join(InputCategory)
    if not include_inactive:
        query = query.filter(AgriculturalInput.is_active == True)
    items = query.order_by(InputCategory.code, AgriculturalInput.code).all()
    date_stamp = datetime.now(timezone.utc).date().isoformat()
    return _csv_response(_write_csv([_export_row(item) for item in items]), f"agri-os-input-catalog-{date_stamp}.csv")


@router.post("/validate")
async def validate_input_catalog_csv(
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

    categories = {row.code for row in db.query(InputCategory.code).filter(InputCategory.is_active == True).all()}
    crops = {row.code for row in db.query(Crop.code).filter(Crop.is_active == True).all()}
    rows = [_normalize_row(raw, index, categories, crops) for index, raw in enumerate(raw_rows, start=2)]
    seen: dict[str, int] = {}
    for row in rows:
        code = row["code"]
        if code in seen:
            row["errors"].append({
                "field": "code",
                "code": "DUPLICATE_CODE_IN_FILE",
                "message": f"Code also appears on row {seen[code]}",
            })
        elif code:
            seen[code] = row["row_number"]

    existing_by_code = {
        item.code: item
        for item in db.query(AgriculturalInput).filter(AgriculturalInput.code.in_(list(seen))).all()
    } if seen else {}
    counts = {"total": len(rows), "create": 0, "update": 0, "unchanged": 0, "errors": 0, "warnings": 0}
    for row in rows:
        existing = existing_by_code.get(row["code"])
        if row["errors"]:
            row["action"] = "INVALID"
        elif not existing:
            row["action"] = "CREATE"
        elif _comparable_payload(existing) == row["normalized"]:
            row["action"] = "UNCHANGED"
        else:
            row["action"] = "UPDATE"
        counts[row["action"].lower()] = counts.get(row["action"].lower(), 0) + 1
        counts["errors"] += len(row["errors"])
        counts["warnings"] += len(row["warnings"])
    report = {
        "can_apply": counts["errors"] == 0 and (counts["create"] + counts["update"]) > 0,
        "counts": counts,
        "rows": rows,
    }
    now = datetime.now(timezone.utc)
    batch = InputCatalogImportBatch(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        actor_id=principal.user_id,
        file_name=(file.filename or "input-catalog.csv")[:255],
        status="VALIDATED" if counts["errors"] == 0 else "INVALID",
        normalized_rows=[row["normalized"] for row in rows if not row["errors"]],
        validation_report=report,
        expires_at=now + timedelta(hours=2),
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    db.commit()
    return _batch_payload(batch)


@router.post("/imports/{batch_id}/apply")
def apply_input_catalog_csv(
    batch_id: uuid.UUID,
    body: InputCsvApplyRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    batch = db.query(InputCatalogImportBatch).filter(
        InputCatalogImportBatch.id == batch_id,
        InputCatalogImportBatch.tenant_id == x_tenant_id,
        InputCatalogImportBatch.is_active == True,
    ).first()
    if not batch:
        raise HTTPException(404, "Import batch not found")
    if batch.status != "VALIDATED":
        raise HTTPException(409, f"Import batch status is {batch.status}")
    if batch.expires_at <= datetime.now(timezone.utc):
        batch.status = "EXPIRED"
        db.commit()
        raise HTTPException(409, "Import batch has expired; validate the CSV again")
    categories = {
        category.code: category
        for category in db.query(InputCategory).filter(InputCategory.is_active == True).all()
    }
    missing_categories = sorted({
        row["category_code"] for row in (batch.normalized_rows or [])
        if row["category_code"] not in categories
    })
    if missing_categories:
        batch.status = "STALE"
        batch.updated_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(409, f"Categories changed since validation: {', '.join(missing_categories)}")
    applied_counts = {"created": 0, "updated": 0, "unchanged": 0}
    now = datetime.now(timezone.utc)
    for row in batch.normalized_rows or []:
        item = db.query(AgriculturalInput).filter(AgriculturalInput.code == row["code"]).first()
        before = input_payload(item) if item else None
        if not item:
            item = AgriculturalInput(
                id=uuid.uuid4(),
                code=row["code"],
                created_at=now,
                updated_at=now,
                is_active=True,
            )
            db.add(item)
        item.category = categories[row["category_code"]]
        item.canonical_name = row["canonical_name"]
        item.brand_name = row["brand_name"]
        item.composition = row["composition"]
        item.unit = row["unit"]
        item.standard_weight = Decimal(row["standard_weight"]) if row["standard_weight"] is not None else None
        item.applicable_crops = row["applicable_crops"]
        item.application_method = row["application_method"]
        item.safety_instructions = row["safety_instructions"]
        item.aliases = row["aliases"]
        item.updated_at = now
        db.flush()
        after = input_payload(item)
        if before == after:
            applied_counts["unchanged"] += 1
            continue
        action = "IMPORT_CREATE_INPUT" if before is None else "IMPORT_UPDATE_INPUT"
        applied_counts["created" if before is None else "updated"] += 1
        _record_input_audit(
            db,
            tenant_id=x_tenant_id,
            item=item,
            actor_id=principal.user_id,
            action=action,
            before=before,
            after=after,
            reason=body.reason,
            metadata={"source": "csv_import", "import_batch_id": str(batch.id), "file_name": batch.file_name},
        )
    batch.status = "APPLIED"
    batch.applied_at = now
    batch.updated_at = now
    report = dict(batch.validation_report or {})
    report["applied_counts"] = applied_counts
    report["apply_reason"] = body.reason
    batch.validation_report = report
    db.commit()
    return _batch_payload(batch)


@router.get("/imports")
def list_input_catalog_imports(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    batches = db.query(InputCatalogImportBatch).filter(
        InputCatalogImportBatch.tenant_id == x_tenant_id,
        InputCatalogImportBatch.is_active == True,
    ).order_by(InputCatalogImportBatch.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "input_catalog_imports.v1",
        "tenant_id": x_tenant_id,
        "count": len(batches),
        "imports": [_batch_payload(batch) for batch in batches],
    }
