"""Manufacturer, branded product, package, and project approval APIs."""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, optional_admin_viewer, require_admin_permission
from app.core.database import get_db
from app.modules.farmer.models import Project
from app.modules.master_data.models import (
    AgriculturalInput, AgriculturalProduct, AgriculturalProductPackage, Manufacturer,
    ProductCatalogAuditEvent, ProjectProductApproval,
)

router = APIRouter(prefix="/api/v1/product-catalog", tags=["product-catalog"])


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