"""Manufacturer, branded product, package, and project approval APIs."""
import csv
from datetime import date, datetime, timedelta, timezone
import io
from decimal import Decimal, InvalidOperation
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, optional_admin_viewer, require_admin_permission
from app.core.database import get_db
from app.modules.farmer.models import Project
from app.modules.master_data.models import (
    AgriculturalInput, AgriculturalProduct, AgriculturalProductPackage, Manufacturer,
    ProductCatalogAuditEvent, ProductCatalogImportBatch, ProjectProductApproval,
)

router = APIRouter(prefix="/api/v1/product-catalog", tags=["product-catalog"])


PRODUCT_CSV_MAX_FILE_BYTES = 2 * 1024 * 1024
PRODUCT_CSV_MAX_ROWS = 2000
PRODUCT_CSV_REQUIRED_COLUMNS = {"manufacturer_code", "manufacturer_name", "product_code", "canonical_input_code", "brand_name", "package_sku", "package_quantity", "package_unit", "package_label"}

PRODUCT_CSV_COLUMNS = [
    "manufacturer_code",
    "manufacturer_name",
    "manufacturer_short_name",
    "manufacturer_country",
    "product_code",
    "canonical_input_code",
    "brand_name",
    "composition",
    "registration_number",
    "registration_authority",
    "registration_expiry_date",
    "product_country",
    "product_status",
    "package_sku",
    "package_quantity",
    "package_unit",
    "package_label",
    "package_barcode",
]


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def _code(value: Optional[str]) -> str:
    return _clean(value).upper().replace(" ", "_")


def _nullable(value: Optional[str]) -> Optional[str]:
    value = _clean(value)
    return value or None


def _csv_download(rows: list[dict], fieldnames: list[str], file_name: str) -> Response:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content="﻿" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


class ManufacturerCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    canonical_name: str = Field(..., min_length=2, max_length=200)
    short_name: Optional[str] = Field(None, max_length=50)
    country: str = Field("India", min_length=2, max_length=50)
    aliases: list[dict[str, str]] = []
    reason: str = Field(..., min_length=3, max_length=500)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value): return value.strip().upper().replace(" ", "_")


class ManufacturerUpdate(BaseModel):
    canonical_name: Optional[str] = Field(None, min_length=2, max_length=200)
    short_name: Optional[str] = Field(None, max_length=50)
    country: Optional[str] = Field(None, min_length=2, max_length=50)
    aliases: Optional[list[dict[str, str]]] = None
    reason: str = Field(..., min_length=3, max_length=500)


class PackageCreate(BaseModel):
    sku: str = Field(..., min_length=2, max_length=100)
    quantity: Decimal = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=20)
    pack_label: str = Field(..., min_length=1, max_length=100)
    barcode: Optional[str] = Field(None, max_length=100)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value): return value.strip().upper().replace(" ", "_")


class PackageAdd(PackageCreate):
    reason: str = Field(..., min_length=3, max_length=500)


class ProductCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=80)
    canonical_input_code: str
    manufacturer_code: str
    brand_name: str = Field(..., min_length=2, max_length=200)
    composition: Optional[str] = Field(None, max_length=300)
    registration_number: Optional[str] = Field(None, max_length=100)
    registration_authority: Optional[str] = Field(None, max_length=150)
    registration_expiry_date: Optional[date] = None
    country: str = Field("India", min_length=2, max_length=50)
    packages: list[PackageCreate] = Field(default_factory=list, min_length=1)
    reason: str = Field(..., min_length=3, max_length=500)

    @field_validator("code", "canonical_input_code", "manufacturer_code")
    @classmethod
    def normalize_codes(cls, value): return value.strip().upper().replace(" ", "_")


class ProductUpdate(BaseModel):
    brand_name: Optional[str] = Field(None, min_length=2, max_length=200)
    composition: Optional[str] = Field(None, max_length=300)
    registration_number: Optional[str] = Field(None, max_length=100)
    registration_authority: Optional[str] = Field(None, max_length=150)
    registration_expiry_date: Optional[date] = None
    country: Optional[str] = Field(None, min_length=2, max_length=50)
    status: Optional[str] = None
    reason: str = Field(..., min_length=3, max_length=500)


class ApprovalUpdate(BaseModel):
    enabled: bool
    preferred: bool = False
    display_order: int = Field(1000, ge=0)
    reason: str = Field(..., min_length=3, max_length=500)


class ProductCsvApplyRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


def manufacturer_payload(row):
    return {"id": str(row.id), "code": row.code, "canonical_name": row.canonical_name, "short_name": row.short_name, "country": row.country, "aliases": row.aliases or [], "is_active": row.is_active}


def package_payload(row):
    return {"id": str(row.id), "sku": row.sku, "quantity": str(row.quantity), "unit": row.unit, "pack_label": row.pack_label, "barcode": row.barcode, "status": row.status, "is_active": row.is_active}


def product_payload(row, approval=None):
    return {
        "id": str(row.id), "code": row.code, "canonical_input_code": row.canonical_input.code,
        "canonical_input_name": row.canonical_input.canonical_name, "manufacturer_code": row.manufacturer.code,
        "manufacturer_name": row.manufacturer.canonical_name, "brand_name": row.brand_name,
        "composition": row.composition, "registration_number": row.registration_number,
        "registration_authority": row.registration_authority,
        "registration_expiry_date": row.registration_expiry_date.isoformat() if row.registration_expiry_date else None,
        "country": row.country, "status": row.status, "is_active": row.is_active,
        "packages": [package_payload(p) for p in sorted(row.packages, key=lambda p: p.pack_label) if p.is_active],
        "project_approval": None if not approval else {"enabled": approval.enabled, "preferred": approval.preferred, "display_order": approval.display_order, "reason": approval.reason},
    }


def record_audit(db, tenant, principal, entity_type, entity_id, entity_code, action, before, after, reason):
    db.add(ProductCatalogAuditEvent(id=uuid.uuid4(), tenant_id=tenant, entity_type=entity_type, entity_id=entity_id,
        entity_code=entity_code, actor_id=principal.user_id, action=action, before_payload=before, after_payload=after,
        reason=reason, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))


def _product_import_batch_payload(batch: ProductCatalogImportBatch) -> dict:
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


def _product_csv_row(product: AgriculturalProduct, package: Optional[AgriculturalProductPackage] = None) -> dict:
    return {
        "manufacturer_code": product.manufacturer.code,
        "manufacturer_name": product.manufacturer.canonical_name,
        "manufacturer_short_name": product.manufacturer.short_name,
        "manufacturer_country": product.manufacturer.country,
        "product_code": product.code,
        "canonical_input_code": product.canonical_input.code,
        "brand_name": product.brand_name,
        "composition": product.composition,
        "registration_number": product.registration_number,
        "registration_authority": product.registration_authority,
        "registration_expiry_date": product.registration_expiry_date.isoformat() if product.registration_expiry_date else "",
        "product_country": product.country,
        "product_status": product.status,
        "package_sku": package.sku if package else "",
        "package_quantity": str(package.quantity) if package else "",
        "package_unit": package.unit if package else "",
        "package_label": package.pack_label if package else "",
        "package_barcode": package.barcode if package else "",
    }


@router.get("/csv/template")
def download_product_csv_template(principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW))):
    row = {
        "manufacturer_code": "ACME_AGRO",
        "manufacturer_name": "Acme Agro Industries",
        "manufacturer_short_name": "ACME",
        "manufacturer_country": "India",
        "product_code": "ACME_UREA_GOLD",
        "canonical_input_code": "UREA_46_N",
        "brand_name": "Acme Urea Gold",
        "composition": "46% Nitrogen",
        "registration_number": "REG-EXAMPLE-001",
        "registration_authority": "State Agriculture Department",
        "registration_expiry_date": "2028-12-31",
        "product_country": "India",
        "product_status": "ACTIVE",
        "package_sku": "ACME_UREA_GOLD_45KG",
        "package_quantity": "45",
        "package_unit": "kg",
        "package_label": "45 kg bag",
        "package_barcode": "",
    }
    return _csv_download([row], PRODUCT_CSV_COLUMNS, "agri-os-product-catalog-template.csv")


@router.get("/csv/export")
def export_product_csv(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    query = db.query(AgriculturalProduct).join(AgriculturalInput, AgriculturalInput.id == AgriculturalProduct.canonical_input_id).join(Manufacturer, Manufacturer.id == AgriculturalProduct.manufacturer_id)
    if not include_inactive:
        query = query.filter(AgriculturalProduct.is_active == True, AgriculturalProduct.status == "ACTIVE", AgriculturalInput.catalog_status == "PUBLISHED", Manufacturer.is_active == True)
    products = query.order_by(Manufacturer.code, AgriculturalProduct.code).all()
    rows: list[dict] = []
    for product in products:
        packages = [package for package in sorted(product.packages, key=lambda item: item.sku) if include_inactive or package.is_active]
        if packages:
            rows.extend(_product_csv_row(product, package) for package in packages)
        else:
            rows.append(_product_csv_row(product, None))
    return _csv_download(rows, PRODUCT_CSV_COLUMNS, "agri-os-product-catalog.csv")


def _normalize_product_csv_row(raw: dict[str, str], row_number: int, known_inputs: set[str], known_manufacturers: set[str], existing_products: dict[str, AgriculturalProduct], existing_skus: set[str]) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    manufacturer_code = _code(raw.get("manufacturer_code"))
    manufacturer_name = _clean(raw.get("manufacturer_name"))
    product_code = _code(raw.get("product_code"))
    canonical_input_code = _code(raw.get("canonical_input_code"))
    brand_name = _clean(raw.get("brand_name"))
    package_sku = _code(raw.get("package_sku"))
    package_quantity_raw = _clean(raw.get("package_quantity"))
    package_unit = _clean(raw.get("package_unit"))
    package_label = _clean(raw.get("package_label"))
    product_status = (_clean(raw.get("product_status")) or "ACTIVE").upper()
    registration_expiry_date = _nullable(raw.get("registration_expiry_date"))
    package_quantity = None

    if not manufacturer_code:
        errors.append({"field": "manufacturer_code", "code": "REQUIRED", "message": "manufacturer_code is required"})
    if manufacturer_code and manufacturer_code not in known_manufacturers:
        warnings.append({"field": "manufacturer_code", "code": "MANUFACTURER_WILL_BE_CREATED", "message": f"Manufacturer {manufacturer_code} will be created during apply"})
    if not manufacturer_name:
        errors.append({"field": "manufacturer_name", "code": "REQUIRED", "message": "manufacturer_name is required"})
    if not product_code:
        errors.append({"field": "product_code", "code": "REQUIRED", "message": "product_code is required"})
    if not canonical_input_code or canonical_input_code not in known_inputs:
        errors.append({"field": "canonical_input_code", "code": "UNKNOWN_INPUT", "message": f"Published canonical input not found: {canonical_input_code or '-'}"})
    if not brand_name:
        errors.append({"field": "brand_name", "code": "REQUIRED", "message": "brand_name is required"})
    if product_status not in {"ACTIVE", "DISCONTINUED"}:
        errors.append({"field": "product_status", "code": "INVALID_STATUS", "message": "product_status must be ACTIVE or DISCONTINUED"})
    if registration_expiry_date:
        try:
            date.fromisoformat(registration_expiry_date)
        except ValueError:
            errors.append({"field": "registration_expiry_date", "code": "INVALID_DATE", "message": "Use YYYY-MM-DD"})
    if not package_sku:
        errors.append({"field": "package_sku", "code": "REQUIRED", "message": "package_sku is required"})
    if package_sku in existing_skus and product_code not in existing_products:
        errors.append({"field": "package_sku", "code": "SKU_ALREADY_EXISTS", "message": f"Package SKU already exists: {package_sku}"})
    try:
        package_quantity = Decimal(package_quantity_raw)
        if package_quantity <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        errors.append({"field": "package_quantity", "code": "INVALID_NUMBER", "message": "package_quantity must be positive"})
    if not package_unit:
        errors.append({"field": "package_unit", "code": "REQUIRED", "message": "package_unit is required"})
    if not package_label:
        errors.append({"field": "package_label", "code": "REQUIRED", "message": "package_label is required"})

    normalized = {
        "manufacturer_code": manufacturer_code,
        "manufacturer_name": manufacturer_name,
        "manufacturer_short_name": _nullable(raw.get("manufacturer_short_name")),
        "manufacturer_country": _clean(raw.get("manufacturer_country")) or "India",
        "product_code": product_code,
        "canonical_input_code": canonical_input_code,
        "brand_name": brand_name,
        "composition": _nullable(raw.get("composition")),
        "registration_number": _nullable(raw.get("registration_number")),
        "registration_authority": _nullable(raw.get("registration_authority")),
        "registration_expiry_date": registration_expiry_date,
        "product_country": _clean(raw.get("product_country")) or "India",
        "product_status": product_status,
        "package_sku": package_sku,
        "package_quantity": str(package_quantity) if package_quantity is not None else None,
        "package_unit": package_unit,
        "package_label": package_label,
        "package_barcode": _nullable(raw.get("package_barcode")),
    }
    action = "INVALID" if errors else ("UPDATE" if product_code in existing_products else "CREATE")
    return {"row_number": row_number, "product_code": product_code, "package_sku": package_sku, "action": action, "errors": errors, "warnings": warnings, "normalized": normalized}


async def _read_product_csv_upload(file: UploadFile) -> str:
    content = await file.read(PRODUCT_CSV_MAX_FILE_BYTES + 1)
    if len(content) > PRODUCT_CSV_MAX_FILE_BYTES:
        raise HTTPException(413, "CSV file exceeds 2 MB")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 encoded")


@router.post("/csv/validate")
async def validate_product_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    text = await _read_product_csv_upload(file)
    reader = csv.DictReader(io.StringIO(text))
    headers = set(reader.fieldnames or [])
    missing = sorted(PRODUCT_CSV_REQUIRED_COLUMNS - headers)
    if missing:
        raise HTTPException(400, {"error": "MISSING_COLUMNS", "columns": missing})
    raw_rows = list(reader)
    if not raw_rows:
        raise HTTPException(400, "CSV contains no data rows")
    if len(raw_rows) > PRODUCT_CSV_MAX_ROWS:
        raise HTTPException(413, "CSV exceeds 2000 rows")

    known_inputs = {row.code for row in db.query(AgriculturalInput).filter(AgriculturalInput.is_active == True, AgriculturalInput.catalog_status == "PUBLISHED").all()}
    known_manufacturers = {row.code for row in db.query(Manufacturer).filter(Manufacturer.is_active == True).all()}
    existing_products = {row.code: row for row in db.query(AgriculturalProduct).all()}
    existing_skus = {row.sku for row in db.query(AgriculturalProductPackage).all()}
    rows = [_normalize_product_csv_row(raw, index, known_inputs, known_manufacturers, existing_products, existing_skus) for index, raw in enumerate(raw_rows, start=2)]

    sku_seen: set[str] = set()
    for row in rows:
        package_sku = row["package_sku"]
        if package_sku in sku_seen:
            row["errors"].append({"field": "package_sku", "code": "DUPLICATE_SKU_IN_FILE", "message": f"Package SKU also appears earlier in this file: {package_sku}"})
        sku_seen.add(package_sku)
        if row["errors"]:
            row["action"] = "INVALID"

    summary = {"total": len(rows), "create": 0, "update": 0, "unchanged": 0, "invalid": 0, "warnings": 0, "errors": 0}
    for row in rows:
        summary["warnings"] += len(row["warnings"])
        summary["errors"] += len(row["errors"])
        if row["action"] == "CREATE":
            summary["create"] += 1
        elif row["action"] == "UPDATE":
            summary["update"] += 1
        elif row["action"] == "INVALID":
            summary["invalid"] += 1
        else:
            summary["unchanged"] += 1
    can_apply = summary["errors"] == 0
    report = {
        "schema_version": "product_catalog_csv_validation.v1",
        "mode": "VALIDATE_ONLY",
        "file_name": file.filename,
        "can_apply": can_apply,
        "summary": summary,
        "rows": rows,
        "message": "Validation passed. Product CSV can be applied." if can_apply else "Validation failed. Fix errors and upload again.",
    }
    now = datetime.now(timezone.utc)
    batch = ProductCatalogImportBatch(
        id=uuid.uuid4(),
        tenant_id=x_tenant_id,
        actor_id=principal.user_id,
        file_name=(file.filename or "product-catalog.csv")[:255],
        status="VALIDATED" if can_apply else "INVALID",
        normalized_rows=[row["normalized"] for row in rows if not row["errors"]],
        validation_report=report,
        expires_at=now + timedelta(hours=2),
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    db.commit()
    return _product_import_batch_payload(batch)

@router.post("/csv/imports/{batch_id}/apply")
def apply_product_csv_import(
    batch_id: uuid.UUID,
    body: ProductCsvApplyRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT)),
):
    batch = db.query(ProductCatalogImportBatch).filter(
        ProductCatalogImportBatch.id == batch_id,
        ProductCatalogImportBatch.tenant_id == x_tenant_id,
        ProductCatalogImportBatch.is_active == True,
    ).first()
    if not batch:
        raise HTTPException(404, "Import batch not found")
    if batch.status != "VALIDATED":
        raise HTTPException(409, f"Import batch status is {batch.status}")
    now = datetime.now(timezone.utc)
    if batch.expires_at <= now:
        batch.status = "EXPIRED"
        batch.updated_at = now
        db.commit()
        raise HTTPException(409, "Import batch has expired; validate the CSV again")

    rows = batch.normalized_rows or []
    input_codes = {row["canonical_input_code"] for row in rows}
    inputs = {
        item.code: item
        for item in db.query(AgriculturalInput).filter(
            AgriculturalInput.code.in_(input_codes),
            AgriculturalInput.catalog_status == "PUBLISHED",
            AgriculturalInput.is_active == True,
        ).all()
    }
    missing_inputs = sorted(input_codes - set(inputs))
    if missing_inputs:
        batch.status = "STALE"
        batch.updated_at = now
        db.commit()
        raise HTTPException(409, f"Published canonical inputs changed since validation: {', '.join(missing_inputs)}")

    product_codes = {row["product_code"] for row in rows}
    products = {item.code: item for item in db.query(AgriculturalProduct).filter(AgriculturalProduct.code.in_(product_codes)).all()}
    skus = {row["package_sku"] for row in rows}
    packages = {item.sku: item for item in db.query(AgriculturalProductPackage).filter(AgriculturalProductPackage.sku.in_(skus)).all()}
    for row in rows:
        package = packages.get(row["package_sku"])
        product = products.get(row["product_code"])
        if package and (not product or package.product_id != product.id):
            batch.status = "STALE"
            batch.updated_at = now
            db.commit()
            raise HTTPException(409, f"Package SKU now belongs to another product: {row['package_sku']}")
        if row.get("package_barcode"):
            barcode_owner = db.query(AgriculturalProductPackage).filter(
                AgriculturalProductPackage.barcode == row["package_barcode"],
                AgriculturalProductPackage.sku != row["package_sku"],
            ).first()
            if barcode_owner:
                batch.status = "STALE"
                batch.updated_at = now
                db.commit()
                raise HTTPException(409, f"Package barcode now belongs to another SKU: {row['package_barcode']}")
        if row.get("registration_number"):
            registration_owner = db.query(AgriculturalProduct).filter(
                AgriculturalProduct.registration_number == row["registration_number"],
                AgriculturalProduct.code != row["product_code"],
            ).first()
            if registration_owner:
                batch.status = "STALE"
                batch.updated_at = now
                db.commit()
                raise HTTPException(409, f"Registration number now belongs to another product: {row['registration_number']}")

    counts = {
        "manufacturers_created": 0,
        "manufacturers_updated": 0,
        "manufacturers_unchanged": 0,
        "products_created": 0,
        "products_updated": 0,
        "products_unchanged": 0,
        "packages_created": 0,
        "packages_updated": 0,
        "packages_unchanged": 0,
    }
    manufacturers = {item.code: item for item in db.query(Manufacturer).filter(Manufacturer.code.in_({row["manufacturer_code"] for row in rows})).all()}
    for row in rows:
        manufacturer = manufacturers.get(row["manufacturer_code"])
        before_manufacturer = manufacturer_payload(manufacturer) if manufacturer else None
        if not manufacturer:
            manufacturer = Manufacturer(id=uuid.uuid4(), code=row["manufacturer_code"], aliases=[], created_at=now, updated_at=now, is_active=True)
            db.add(manufacturer)
            manufacturers[row["manufacturer_code"]] = manufacturer
        manufacturer.canonical_name = row["manufacturer_name"]
        manufacturer.short_name = row.get("manufacturer_short_name")
        manufacturer.country = row.get("manufacturer_country") or "India"
        manufacturer.updated_at = now
        db.flush()
        after_manufacturer = manufacturer_payload(manufacturer)
        if before_manufacturer == after_manufacturer:
            counts["manufacturers_unchanged"] += 1
        else:
            counts["manufacturers_created" if before_manufacturer is None else "manufacturers_updated"] += 1
            record_audit(db, x_tenant_id, principal, "MANUFACTURER", manufacturer.id, manufacturer.code, "IMPORT_CREATE_MANUFACTURER" if before_manufacturer is None else "IMPORT_UPDATE_MANUFACTURER", before_manufacturer, after_manufacturer, body.reason)

        product = products.get(row["product_code"])
        before_product = product_payload(product) if product else None
        if not product:
            product = AgriculturalProduct(id=uuid.uuid4(), code=row["product_code"], created_at=now, updated_at=now, is_active=True)
            db.add(product)
            products[row["product_code"]] = product
        product.canonical_input = inputs[row["canonical_input_code"]]
        product.canonical_input_id = inputs[row["canonical_input_code"]].id
        product.manufacturer = manufacturer
        product.manufacturer_id = manufacturer.id
        product.brand_name = row["brand_name"]
        product.composition = row.get("composition")
        product.registration_number = row.get("registration_number")
        product.registration_authority = row.get("registration_authority")
        product.registration_expiry_date = date.fromisoformat(row["registration_expiry_date"]) if row.get("registration_expiry_date") else None
        product.country = row.get("product_country") or "India"
        product.status = row.get("product_status") or "ACTIVE"
        product.updated_at = now
        db.flush()
        after_product = product_payload(product)
        if before_product == after_product:
            counts["products_unchanged"] += 1
        else:
            counts["products_created" if before_product is None else "products_updated"] += 1
            record_audit(db, x_tenant_id, principal, "PRODUCT", product.id, product.code, "IMPORT_CREATE_PRODUCT" if before_product is None else "IMPORT_UPDATE_PRODUCT", before_product, after_product, body.reason)

        package = packages.get(row["package_sku"])
        before_package = package_payload(package) if package else None
        if not package:
            package = AgriculturalProductPackage(id=uuid.uuid4(), product_id=product.id, sku=row["package_sku"], created_at=now, updated_at=now, is_active=True)
            db.add(package)
            packages[row["package_sku"]] = package
        package.product_id = product.id
        package.quantity = Decimal(row["package_quantity"])
        package.unit = row["package_unit"]
        package.pack_label = row["package_label"]
        package.barcode = row.get("package_barcode")
        package.status = "ACTIVE"
        package.updated_at = now
        db.flush()
        after_package = package_payload(package)
        if before_package == after_package:
            counts["packages_unchanged"] += 1
        else:
            counts["packages_created" if before_package is None else "packages_updated"] += 1
            record_audit(db, x_tenant_id, principal, "PACKAGE", package.id, package.sku, "IMPORT_CREATE_PACKAGE" if before_package is None else "IMPORT_UPDATE_PACKAGE", before_package, after_package, body.reason)

    batch.status = "APPLIED"
    batch.applied_at = now
    batch.updated_at = now
    report = dict(batch.validation_report or {})
    report["applied_counts"] = counts
    report["apply_reason"] = body.reason
    report["message"] = "Product CSV import applied."
    batch.validation_report = report
    db.commit()
    return _product_import_batch_payload(batch)

@router.get("/csv/imports")
def product_csv_import_history(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    query = db.query(ProductCatalogImportBatch).filter(ProductCatalogImportBatch.tenant_id == x_tenant_id, ProductCatalogImportBatch.is_active == True)
    if status:
        query = query.filter(ProductCatalogImportBatch.status == status.upper())
    rows = query.order_by(ProductCatalogImportBatch.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "product_catalog_imports.v1",
        "tenant_id": x_tenant_id,
        "status": status.upper() if status else None,
        "count": len(rows),
        "imports": [_product_import_batch_payload(row) for row in rows],
    }


@router.get("/manufacturers")
def list_manufacturers(db: Session = Depends(get_db), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW))):
    rows = db.query(Manufacturer).filter(Manufacturer.is_active == True).order_by(Manufacturer.canonical_name).all()
    return {"schema_version": "product_catalog.v1", "count": len(rows), "manufacturers": [manufacturer_payload(x) for x in rows]}


@router.post("/manufacturers")
def create_manufacturer(body: ManufacturerCreate, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT))):
    if db.query(Manufacturer).filter(Manufacturer.code == body.code).first(): raise HTTPException(409, "Manufacturer code already exists")
    row = Manufacturer(id=uuid.uuid4(), code=body.code, canonical_name=body.canonical_name.strip(), short_name=body.short_name,
        country=body.country, aliases=body.aliases, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db.add(row); db.flush(); after = manufacturer_payload(row)
    record_audit(db, x_tenant_id, principal, "MANUFACTURER", row.id, row.code, "CREATE_MANUFACTURER", None, after, body.reason)
    db.commit(); return after


@router.put("/manufacturers/{manufacturer_code}")
def update_manufacturer(manufacturer_code: str, body: ManufacturerUpdate, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT))):
    row = db.query(Manufacturer).filter(Manufacturer.code == manufacturer_code.upper(), Manufacturer.is_active == True).first()
    if not row: raise HTTPException(404, "Manufacturer not found")
    before = manufacturer_payload(row)
    for key, value in body.model_dump(exclude_unset=True, exclude={"reason"}).items(): setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc); after = manufacturer_payload(row)
    record_audit(db, x_tenant_id, principal, "MANUFACTURER", row.id, row.code, "UPDATE_MANUFACTURER", before, after, body.reason)
    db.commit(); return after


@router.post("/products")
def create_product(body: ProductCreate, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT))):
    if db.query(AgriculturalProduct).filter(AgriculturalProduct.code == body.code).first(): raise HTTPException(409, "Product code already exists")
    canonical = db.query(AgriculturalInput).filter(AgriculturalInput.code == body.canonical_input_code, AgriculturalInput.catalog_status == "PUBLISHED", AgriculturalInput.is_active == True).first()
    manufacturer = db.query(Manufacturer).filter(Manufacturer.code == body.manufacturer_code, Manufacturer.is_active == True).first()
    if not canonical: raise HTTPException(404, "Published canonical input not found")
    if not manufacturer: raise HTTPException(404, "Manufacturer not found")
    if body.registration_number and db.query(AgriculturalProduct).filter(AgriculturalProduct.registration_number == body.registration_number).first(): raise HTTPException(409, "Registration number already exists")
    skus = [p.sku for p in body.packages]
    if len(skus) != len(set(skus)) or db.query(AgriculturalProductPackage).filter(AgriculturalProductPackage.sku.in_(skus)).first(): raise HTTPException(409, "Package SKU must be unique")
    now = datetime.now(timezone.utc)
    row = AgriculturalProduct(id=uuid.uuid4(), code=body.code, canonical_input_id=canonical.id, manufacturer_id=manufacturer.id,
        brand_name=body.brand_name.strip(), composition=body.composition, registration_number=body.registration_number,
        registration_authority=body.registration_authority, registration_expiry_date=body.registration_expiry_date,
        country=body.country, status="ACTIVE", created_at=now, updated_at=now)
    db.add(row); db.flush()
    for package in body.packages: db.add(AgriculturalProductPackage(id=uuid.uuid4(), product_id=row.id, sku=package.sku, quantity=package.quantity, unit=package.unit, pack_label=package.pack_label, barcode=package.barcode, status="ACTIVE", created_at=now, updated_at=now))
    db.flush(); db.refresh(row); after = product_payload(row)
    record_audit(db, x_tenant_id, principal, "PRODUCT", row.id, row.code, "CREATE_PRODUCT", None, after, body.reason)
    db.commit(); return after


@router.post("/products/{product_code}/packages")
def add_product_package(product_code: str, body: PackageAdd, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT))):
    product = db.query(AgriculturalProduct).filter(AgriculturalProduct.code == product_code.upper()).first()
    if not product: raise HTTPException(404, "Product not found")
    if db.query(AgriculturalProductPackage).filter((AgriculturalProductPackage.sku == body.sku) | (AgriculturalProductPackage.barcode == body.barcode if body.barcode else False)).first(): raise HTTPException(409, "Package SKU or barcode already exists")
    now = datetime.now(timezone.utc)
    package = AgriculturalProductPackage(id=uuid.uuid4(), product_id=product.id, sku=body.sku, quantity=body.quantity, unit=body.unit, pack_label=body.pack_label, barcode=body.barcode, status="ACTIVE", created_at=now, updated_at=now)
    db.add(package); db.flush(); after = package_payload(package)
    record_audit(db, x_tenant_id, principal, "PACKAGE", package.id, package.sku, "ADD_PRODUCT_PACKAGE", None, after, body.reason)
    db.commit(); return after


@router.put("/products/{product_code}")
def update_product(product_code: str, body: ProductUpdate, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.EDIT))):
    row = db.query(AgriculturalProduct).filter(AgriculturalProduct.code == product_code.upper()).first()
    if not row: raise HTTPException(404, "Product not found")
    before = product_payload(row); data = body.model_dump(exclude_unset=True, exclude={"reason"})
    if "status" in data and data["status"] not in {"ACTIVE", "DISCONTINUED"}: raise HTTPException(400, "status must be ACTIVE or DISCONTINUED")
    for key, value in data.items(): setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc); after = product_payload(row)
    record_audit(db, x_tenant_id, principal, "PRODUCT", row.id, row.code, "UPDATE_PRODUCT", before, after, body.reason)
    db.commit(); return after


@router.get("/products")
def list_products(input_code: Optional[str] = Query(None), manufacturer_code: Optional[str] = Query(None), project_id: Optional[uuid.UUID] = Query(None), include_inactive: bool = Query(False), db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), admin_principal: Optional[AdminPrincipal] = Depends(optional_admin_viewer)):
    if include_inactive and admin_principal is None:
        raise HTTPException(403, "Admin VIEW permission is required to include inactive products")
    query = db.query(AgriculturalProduct).join(
        AgriculturalInput, AgriculturalInput.id == AgriculturalProduct.canonical_input_id
    ).join(Manufacturer, Manufacturer.id == AgriculturalProduct.manufacturer_id)
    if not include_inactive: query = query.filter(AgriculturalProduct.is_active == True, AgriculturalProduct.status == "ACTIVE", AgriculturalInput.catalog_status == "PUBLISHED")
    if input_code: query = query.filter(AgriculturalInput.code == input_code.upper())
    if manufacturer_code: query = query.filter(Manufacturer.code == manufacturer_code.upper())
    rows = query.order_by(AgriculturalProduct.brand_name).all(); approvals = {}
    if project_id:
        project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id, Project.is_active == True).first()
        if not project: raise HTTPException(404, "Project not found")
        approval_rows = db.query(ProjectProductApproval).filter(ProjectProductApproval.project_id == project_id, ProjectProductApproval.tenant_id == x_tenant_id, ProjectProductApproval.is_active == True).all()
        approvals = {x.product_id: x for x in approval_rows}
        if approval_rows: rows = [row for row in rows if row.id in approvals and approvals[row.id].enabled]
        rows.sort(key=lambda row: (not (approvals.get(row.id) and approvals[row.id].preferred), approvals.get(row.id).display_order if approvals.get(row.id) else 1000, row.brand_name))
    return {"schema_version": "product_catalog.v1", "project_id": str(project_id) if project_id else None, "approval_policy": "EXPLICIT" if approvals else "ALL_ACTIVE", "count": len(rows), "products": [product_payload(row, approvals.get(row.id)) for row in rows]}


@router.put("/projects/{project_id}/products/{product_code}")
def approve_product(project_id: uuid.UUID, product_code: str, body: ApprovalUpdate, db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.PROJECT_EDIT, project_scoped=True))):
    product = db.query(AgriculturalProduct).filter(AgriculturalProduct.code == product_code.upper(), AgriculturalProduct.status == "ACTIVE", AgriculturalProduct.is_active == True).first()
    if not product: raise HTTPException(404, "Active product not found")
    approval = db.query(ProjectProductApproval).filter(ProjectProductApproval.tenant_id == x_tenant_id, ProjectProductApproval.project_id == project_id, ProjectProductApproval.product_id == product.id).first()
    before = None if not approval else {"enabled": approval.enabled, "preferred": approval.preferred, "display_order": approval.display_order, "reason": approval.reason}
    if not approval:
        approval = ProjectProductApproval(id=uuid.uuid4(), tenant_id=x_tenant_id, project_id=project_id, product_id=product.id, created_at=datetime.now(timezone.utc)); db.add(approval)
    approval.enabled, approval.preferred, approval.display_order, approval.reason = body.enabled, body.preferred, body.display_order, body.reason
    approval.updated_at = datetime.now(timezone.utc); approval.is_active = True
    after = {"enabled": approval.enabled, "preferred": approval.preferred, "display_order": approval.display_order, "reason": approval.reason}
    record_audit(db, x_tenant_id, principal, "PROJECT_PRODUCT_APPROVAL", approval.id, product.code, "UPSERT_PRODUCT_APPROVAL", before, after, body.reason)
    db.commit(); return {"product": product_payload(product, approval)}


@router.get("/audit")
def list_audit(entity_type: Optional[str] = Query(None), entity_code: Optional[str] = Query(None), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), x_tenant_id: str = Header("default", alias="X-Tenant-ID"), principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW))):
    query = db.query(ProductCatalogAuditEvent).filter(ProductCatalogAuditEvent.tenant_id == x_tenant_id)
    if entity_type: query = query.filter(ProductCatalogAuditEvent.entity_type == entity_type.upper())
    if entity_code: query = query.filter(ProductCatalogAuditEvent.entity_code == entity_code.upper())
    rows = query.order_by(ProductCatalogAuditEvent.created_at.desc()).limit(limit).all()
    return {"count": len(rows), "events": [{"id": str(x.id), "entity_type": x.entity_type, "entity_code": x.entity_code, "action": x.action, "actor_id": str(x.actor_id) if x.actor_id else None, "before": x.before_payload, "after": x.after_payload, "reason": x.reason, "created_at": x.created_at.isoformat()} for x in rows]}