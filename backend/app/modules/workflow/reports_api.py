"""Read-only workflow reporting APIs for admin dashboards."""
from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date
from decimal import Decimal
import io
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.farmer.models import Farmer, Parcel, Project
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


ACTIVITY_USAGE_CSV_COLUMNS = [
    "activity_id",
    "activity_date",
    "tenant_id",
    "project_id",
    "farmer_id",
    "farmer_name",
    "parcel_id",
    "parcel_label",
    "crop_cycle_id",
    "crop_code",
    "season_code",
    "stage_code",
    "activity_type",
    "input_code",
    "input_name",
    "input_rule_id",
    "product_id",
    "product_code",
    "package_id",
    "package_sku",
    "recommended_quantity",
    "recommended_quantity_unit",
    "actual_quantity",
    "actual_quantity_unit",
    "dosage_variance_reason",
    "quantity",
    "quantity_unit",
    "area_applied",
    "area_unit",
    "cost_amount",
    "cost_currency",
    "notes",
]


def _decimal_text(value):
    return str(value) if value is not None else None


def _decimal_sum(values):
    total = Decimal("0")
    found = False
    for value in values:
        if value is not None:
            total += Decimal(str(value))
            found = True
    return str(total) if found else "0"


def _activity_usage_rows(
    *,
    db: Session,
    tenant_id: str,
    project_id: Optional[uuid.UUID],
    farmer_id: Optional[uuid.UUID],
    parcel_id: Optional[uuid.UUID],
    crop_code: Optional[str],
    season_code: Optional[str],
    stage_code: Optional[str],
    activity_type: Optional[str],
    input_code: Optional[str],
    product_code: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    limit: int,
):
    query = (
        db.query(CropActivity, CropCycle, CropStageInstance, Farmer, Parcel)
        .join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id)
        .outerjoin(CropStageInstance, CropStageInstance.id == CropActivity.stage_instance_id)
        .outerjoin(Farmer, Farmer.id == CropActivity.farmer_id)
        .outerjoin(Parcel, Parcel.id == CropCycle.parcel_id)
        .filter(CropActivity.tenant_id == tenant_id, CropCycle.tenant_id == tenant_id)
    )
    if project_id:
        query = query.filter(CropCycle.project_id == project_id)
    if farmer_id:
        query = query.filter(CropCycle.farmer_id == farmer_id)
    if parcel_id:
        query = query.filter(CropCycle.parcel_id == parcel_id)
    if crop_code:
        query = query.filter(CropCycle.crop_code == crop_code.upper())
    if season_code:
        query = query.filter(CropCycle.season_code == season_code.upper())
    if stage_code:
        query = query.filter(CropStageInstance.stage_code == stage_code.upper())
    if activity_type:
        query = query.filter(CropActivity.activity_type == activity_type.upper())
    if input_code:
        query = query.filter(CropActivity.input_code == input_code.upper())
    if product_code:
        query = query.filter(CropActivity.product_code == product_code.upper())
    if date_from:
        query = query.filter(CropActivity.activity_date >= date_from)
    if date_to:
        query = query.filter(CropActivity.activity_date <= date_to)

    rows = query.order_by(CropActivity.activity_date.desc(), CropActivity.created_at.desc()).limit(limit).all()
    report_rows = []
    for activity, cycle, stage, farmer, parcel in rows:
        report_rows.append({
            "activity_id": str(activity.id),
            "activity_date": activity.activity_date.isoformat() if activity.activity_date else None,
            "tenant_id": activity.tenant_id,
            "project_id": str(cycle.project_id) if cycle.project_id else None,
            "farmer_id": str(cycle.farmer_id) if cycle.farmer_id else None,
            "farmer_name": farmer.display_name if farmer else None,
            "parcel_id": str(cycle.parcel_id) if cycle.parcel_id else None,
            "parcel_label": parcel.survey_number if parcel else None,
            "crop_cycle_id": str(cycle.id),
            "crop_code": cycle.crop_code,
            "season_code": cycle.season_code,
            "stage_code": stage.stage_code if stage else None,
            "activity_type": activity.activity_type,
            "input_code": activity.input_code,
            "input_name": activity.input_name,
            "input_rule_id": str(activity.input_rule_id) if activity.input_rule_id else None,
            "product_id": str(activity.product_id) if activity.product_id else None,
            "product_code": activity.product_code,
            "package_id": str(activity.package_id) if activity.package_id else None,
            "package_sku": activity.package_sku,
            "recommended_quantity": _decimal_text(activity.recommended_quantity),
            "recommended_quantity_unit": activity.recommended_quantity_unit,
            "actual_quantity": _decimal_text(activity.actual_quantity),
            "actual_quantity_unit": activity.actual_quantity_unit,
            "dosage_variance_reason": activity.dosage_variance_reason,
            "quantity": _decimal_text(activity.quantity),
            "quantity_unit": activity.quantity_unit,
            "area_applied": _decimal_text(activity.area_applied),
            "area_unit": activity.area_unit,
            "cost_amount": _decimal_text(activity.cost_amount),
            "cost_currency": activity.cost_currency,
            "notes": activity.notes,
        })
    return report_rows


def _activity_usage_payload(
    *,
    tenant_id: str,
    rows,
    project_id: Optional[uuid.UUID],
    farmer_id: Optional[uuid.UUID],
    parcel_id: Optional[uuid.UUID],
    crop_code: Optional[str],
    season_code: Optional[str],
    stage_code: Optional[str],
    activity_type: Optional[str],
    input_code: Optional[str],
    product_code: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    limit: int,
):
    quantity_by_input = defaultdict(Decimal)
    quantity_by_product = defaultdict(Decimal)
    variance_count = 0
    for row in rows:
        quantity_value = row.get("actual_quantity") or row.get("quantity")
        unit = row.get("actual_quantity_unit") or row.get("quantity_unit") or "UNKNOWN"
        if quantity_value is not None:
            if row.get("input_code"):
                quantity_by_input[(row["input_code"], unit)] += Decimal(str(quantity_value))
            if row.get("product_code"):
                quantity_by_product[(row["product_code"], row.get("package_sku") or "", unit)] += Decimal(str(quantity_value))
        if row.get("recommended_quantity") is not None and row.get("actual_quantity") is not None:
            if Decimal(str(row["recommended_quantity"])) != Decimal(str(row["actual_quantity"])):
                variance_count += 1

    return {
        "schema_version": "activity_usage_report.v1",
        "tenant_id": tenant_id,
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "farmer_id": str(farmer_id) if farmer_id else None,
            "parcel_id": str(parcel_id) if parcel_id else None,
            "crop_code": crop_code.upper() if crop_code else None,
            "season_code": season_code.upper() if season_code else None,
            "stage_code": stage_code.upper() if stage_code else None,
            "activity_type": activity_type.upper() if activity_type else None,
            "input_code": input_code.upper() if input_code else None,
            "product_code": product_code.upper() if product_code else None,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "limit": limit,
        },
        "summary": {
            "activity_count": len(rows),
            "total_cost": _decimal_sum([row.get("cost_amount") for row in rows]),
            "variance_count": variance_count,
            "quantity_by_input": [
                {"input_code": key[0], "unit": key[1], "quantity": str(value)}
                for key, value in sorted(quantity_by_input.items())
            ],
            "quantity_by_product": [
                {"product_code": key[0], "package_sku": key[1] or None, "unit": key[2], "quantity": str(value)}
                for key, value in sorted(quantity_by_product.items())
            ],
        },
        "count": len(rows),
        "activities": rows,
    }


def _activity_usage_csv(rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ACTIVITY_USAGE_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column) for column in ACTIVITY_USAGE_CSV_COLUMNS})
    buffer.seek(0)
    return buffer.getvalue()


@router.get("/activity-usage/filter-options")
def activity_usage_filter_options(
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    base = (
        db.query(CropActivity, CropCycle, CropStageInstance, Farmer, Parcel, Project)
        .join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id)
        .outerjoin(CropStageInstance, CropStageInstance.id == CropActivity.stage_instance_id)
        .outerjoin(Farmer, Farmer.id == CropActivity.farmer_id)
        .outerjoin(Parcel, Parcel.id == CropCycle.parcel_id)
        .outerjoin(Project, Project.id == CropCycle.project_id)
        .filter(CropActivity.tenant_id == x_tenant_id, CropCycle.tenant_id == x_tenant_id)
        .all()
    )
    projects = {}
    farmers = {}
    parcels = {}
    crops = set()
    seasons = set()
    stages = {}
    activity_types = set()
    inputs = {}
    products = {}
    for activity, cycle, stage, farmer, parcel, project in base:
        if project:
            projects[str(project.id)] = project.name
        if farmer:
            farmers[str(farmer.id)] = farmer.display_name or farmer.mobile_number or str(farmer.id)
        if parcel:
            parcels[str(parcel.id)] = parcel.survey_number or str(parcel.id)
        if cycle.crop_code:
            crops.add(cycle.crop_code)
        if cycle.season_code:
            seasons.add(cycle.season_code)
        if stage and stage.stage_code:
            stages[stage.stage_code] = stage.stage_name or stage.stage_code
        if activity.activity_type:
            activity_types.add(activity.activity_type)
        if activity.input_code:
            inputs[activity.input_code] = activity.input_name or activity.input_code
        if activity.product_code:
            products[activity.product_code] = activity.product_code
    return {
        "schema_version": "activity_usage_filter_options.v1",
        "tenant_id": x_tenant_id,
        "projects": [{"id": key, "label": value} for key, value in sorted(projects.items(), key=lambda item: item[1])],
        "farmers": [{"id": key, "label": value} for key, value in sorted(farmers.items(), key=lambda item: item[1])],
        "parcels": [{"id": key, "label": value} for key, value in sorted(parcels.items(), key=lambda item: item[1])],
        "crops": sorted(crops),
        "seasons": sorted(seasons),
        "stages": [{"code": key, "label": value} for key, value in sorted(stages.items())],
        "activity_types": sorted(activity_types),
        "inputs": [{"code": key, "label": value} for key, value in sorted(inputs.items())],
        "products": [{"code": key, "label": value} for key, value in sorted(products.items())],
    }

@router.get("/activity-usage")
def activity_usage_report(
    project_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    parcel_id: Optional[uuid.UUID] = Query(None),
    crop_code: Optional[str] = Query(None),
    season_code: Optional[str] = Query(None),
    stage_code: Optional[str] = Query(None),
    activity_type: Optional[str] = Query(None),
    input_code: Optional[str] = Query(None),
    product_code: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(250, ge=1, le=1000),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    rows = _activity_usage_rows(
        db=db,
        tenant_id=x_tenant_id,
        project_id=project_id,
        farmer_id=farmer_id,
        parcel_id=parcel_id,
        crop_code=crop_code,
        season_code=season_code,
        stage_code=stage_code,
        activity_type=activity_type,
        input_code=input_code,
        product_code=product_code,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    return _activity_usage_payload(
        tenant_id=x_tenant_id,
        rows=rows,
        project_id=project_id,
        farmer_id=farmer_id,
        parcel_id=parcel_id,
        crop_code=crop_code,
        season_code=season_code,
        stage_code=stage_code,
        activity_type=activity_type,
        input_code=input_code,
        product_code=product_code,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get("/activity-usage.csv")
def activity_usage_report_csv(
    project_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    parcel_id: Optional[uuid.UUID] = Query(None),
    crop_code: Optional[str] = Query(None),
    season_code: Optional[str] = Query(None),
    stage_code: Optional[str] = Query(None),
    activity_type: Optional[str] = Query(None),
    input_code: Optional[str] = Query(None),
    product_code: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    rows = _activity_usage_rows(
        db=db,
        tenant_id=x_tenant_id,
        project_id=project_id,
        farmer_id=farmer_id,
        parcel_id=parcel_id,
        crop_code=crop_code,
        season_code=season_code,
        stage_code=stage_code,
        activity_type=activity_type,
        input_code=input_code,
        product_code=product_code,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    csv_text = _activity_usage_csv(rows)
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="activity_usage.csv"'},
    )