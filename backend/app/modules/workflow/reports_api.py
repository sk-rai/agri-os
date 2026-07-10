"""Read-only workflow reporting APIs for admin dashboards."""
from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date
from decimal import Decimal
import io
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.farmer.models import Farmer, Parcel, Project
from app.modules.master_data.models import (
    AgriculturalInput,
    AgriculturalProduct,
    CropStageInputRule,
    InputCategory,
    ProjectInputAssignment,
    ProjectProductApproval,
)
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
    "crop_cycle_status",
    "workflow_template_version_id",
    "crop_code",
    "season_code",
    "stage_code",
    "stage_instance_id",
    "stage_name",
    "stage_order",
    "stage_status",
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
    "gps_lat",
    "gps_lng",
    "logged_by",
    "logging_method",
    "created_at",
    "updated_at",
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
            "crop_cycle_status": cycle.status,
            "workflow_template_version_id": str(cycle.workflow_template_version_id) if cycle.workflow_template_version_id else None,
            "crop_code": cycle.crop_code,
            "season_code": cycle.season_code,
            "stage_code": stage.stage_code if stage else None,
            "stage_instance_id": str(stage.id) if stage else None,
            "stage_name": stage.stage_name if stage else None,
            "stage_order": stage.stage_order if stage else None,
            "stage_status": stage.status if stage else None,
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
            "gps_lat": _decimal_text(activity.gps_lat),
            "gps_lng": _decimal_text(activity.gps_lng),
            "logged_by": str(activity.logged_by) if activity.logged_by else None,
            "logging_method": activity.logging_method,
            "created_at": activity.created_at.isoformat() if activity.created_at else None,
            "updated_at": activity.updated_at.isoformat() if activity.updated_at else None,
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



def _activity_trace_row(activity, cycle, stage, farmer, parcel):
    return {
        "activity_id": str(activity.id),
        "activity_date": activity.activity_date.isoformat() if activity.activity_date else None,
        "tenant_id": activity.tenant_id,
        "project_id": str(cycle.project_id) if cycle.project_id else None,
        "farmer_id": str(cycle.farmer_id) if cycle.farmer_id else None,
        "farmer_name": farmer.display_name if farmer else None,
        "parcel_id": str(cycle.parcel_id) if cycle.parcel_id else None,
        "parcel_label": parcel.survey_number if parcel else None,
        "crop_cycle_id": str(cycle.id),
        "crop_cycle_status": cycle.status,
        "workflow_template_version_id": str(cycle.workflow_template_version_id) if cycle.workflow_template_version_id else None,
        "crop_code": cycle.crop_code,
        "season_code": cycle.season_code,
        "stage_code": stage.stage_code if stage else None,
        "stage_instance_id": str(stage.id) if stage else None,
        "stage_name": stage.stage_name if stage else None,
        "stage_order": stage.stage_order if stage else None,
        "stage_status": stage.status if stage else None,
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
        "gps_lat": _decimal_text(activity.gps_lat),
        "gps_lng": _decimal_text(activity.gps_lng),
        "logged_by": str(activity.logged_by) if activity.logged_by else None,
        "logging_method": activity.logging_method,
        "created_at": activity.created_at.isoformat() if activity.created_at else None,
        "updated_at": activity.updated_at.isoformat() if activity.updated_at else None,
        "notes": activity.notes,
    }



@router.get("/input-rules/{rule_id}/trace")
def input_rule_trace_report(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    rule = db.query(CropStageInputRule).filter(CropStageInputRule.id == rule_id, CropStageInputRule.tenant_id == x_tenant_id).first()
    if not rule:
        raise HTTPException(404, "Input rule not found")

    agri_input = db.query(AgriculturalInput).filter(AgriculturalInput.id == rule.input_id).first()
    category = db.query(InputCategory).filter(InputCategory.id == agri_input.category_id).first() if agri_input else None
    project = db.query(Project).filter(Project.id == rule.project_id).first() if rule.project_id else None
    assignment = (
        db.query(ProjectInputAssignment)
        .filter(
            ProjectInputAssignment.tenant_id == x_tenant_id,
            ProjectInputAssignment.project_id == rule.project_id,
            ProjectInputAssignment.input_code == rule.input_code,
        )
        .first()
        if rule.project_id
        else None
    )

    product_query = db.query(AgriculturalProduct).filter(AgriculturalProduct.canonical_input_id == rule.input_id)
    if rule.allowed_product_codes:
        product_query = product_query.filter(AgriculturalProduct.code.in_(rule.allowed_product_codes))
    products = product_query.order_by(AgriculturalProduct.code.asc()).all()
    approvals_by_product = {}
    if rule.project_id and products:
        approvals = (
            db.query(ProjectProductApproval)
            .filter(
                ProjectProductApproval.tenant_id == x_tenant_id,
                ProjectProductApproval.project_id == rule.project_id,
                ProjectProductApproval.product_id.in_([product.id for product in products]),
            )
            .all()
        )
        approvals_by_product = {approval.product_id: approval for approval in approvals}

    activity_rows_raw = (
        db.query(CropActivity, CropCycle, CropStageInstance, Farmer, Parcel)
        .join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id)
        .outerjoin(CropStageInstance, CropStageInstance.id == CropActivity.stage_instance_id)
        .outerjoin(Farmer, Farmer.id == CropActivity.farmer_id)
        .outerjoin(Parcel, Parcel.id == CropCycle.parcel_id)
        .filter(CropActivity.tenant_id == x_tenant_id, CropActivity.input_rule_id == rule.id)
        .order_by(CropActivity.activity_date.asc(), CropActivity.created_at.asc())
        .all()
    )
    activities = [_activity_trace_row(activity, cycle, stage, farmer, parcel) for activity, cycle, stage, farmer, parcel in activity_rows_raw]
    quantity_by_product = defaultdict(Decimal)
    for row in activities:
        quantity_value = row.get("actual_quantity") or row.get("quantity")
        if row.get("product_code") and quantity_value is not None:
            unit = row.get("actual_quantity_unit") or row.get("quantity_unit") or "UNKNOWN"
            quantity_by_product[(row["product_code"], unit)] += Decimal(str(quantity_value))

    return {
        "schema_version": "input_rule_trace.v1",
        "tenant_id": x_tenant_id,
        "rule": {
            "id": str(rule.id),
            "project_id": str(rule.project_id) if rule.project_id else None,
            "crop_code": rule.crop_code,
            "season_code": rule.season_code,
            "stage_code": rule.stage_code,
            "activity_type": rule.activity_type,
            "input_id": str(rule.input_id),
            "input_code": rule.input_code,
            "enabled": rule.enabled,
            "priority": rule.priority,
            "dosage_quantity": _decimal_text(rule.dosage_quantity),
            "dosage_unit": rule.dosage_unit,
            "dosage_area_unit": rule.dosage_area_unit,
            "min_quantity": _decimal_text(rule.min_quantity),
            "max_quantity": _decimal_text(rule.max_quantity),
            "application_method": rule.application_method,
            "timing_note": rule.timing_note,
            "safety_note": rule.safety_note,
            "allowed_product_codes": rule.allowed_product_codes or [],
            "reason": rule.reason,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        },
        "project": {"id": str(project.id), "name": project.name, "status": project.status} if project else None,
        "input": {
            "id": str(agri_input.id),
            "code": agri_input.code,
            "canonical_name": agri_input.canonical_name,
            "category_code": category.code if category else None,
            "category_name": category.canonical_name if category else None,
            "composition": agri_input.composition,
            "unit": agri_input.unit,
            "catalog_status": agri_input.catalog_status,
            "applicable_crops": agri_input.applicable_crops or [],
        } if agri_input else None,
        "project_assignment": {
            "id": str(assignment.id),
            "enabled": assignment.enabled,
            "display_order": assignment.display_order,
            "reason": assignment.reason,
            "effective_from": assignment.effective_from.isoformat() if assignment.effective_from else None,
            "effective_to": assignment.effective_to.isoformat() if assignment.effective_to else None,
        } if assignment else None,
        "products": [
            {
                "id": str(product.id),
                "code": product.code,
                "brand_name": product.brand_name,
                "composition": product.composition,
                "registration_number": product.registration_number,
                "status": product.status,
                "approval": (
                    {
                        "enabled": approvals_by_product[product.id].enabled,
                        "preferred": approvals_by_product[product.id].preferred,
                        "display_order": approvals_by_product[product.id].display_order,
                        "reason": approvals_by_product[product.id].reason,
                    }
                    if product.id in approvals_by_product
                    else None
                ),
            }
            for product in products
        ],
        "summary": {
            "activity_count": len(activities),
            "total_cost": _decimal_sum([row.get("cost_amount") for row in activities]),
            "variance_count": sum(1 for row in activities if row.get("recommended_quantity") is not None and row.get("actual_quantity") is not None and Decimal(str(row["recommended_quantity"])) != Decimal(str(row["actual_quantity"]))),
            "quantity_by_product": [
                {"product_code": key[0], "unit": key[1], "quantity": str(value)}
                for key, value in sorted(quantity_by_product.items())
            ],
        },
        "activities": activities,
    }

@router.get("/crop-cycles/{cycle_id}/trace")
def crop_cycle_trace_report(
    cycle_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    cycle = db.query(CropCycle).filter(CropCycle.id == cycle_id, CropCycle.tenant_id == x_tenant_id).first()
    if not cycle:
        raise HTTPException(404, "Crop cycle not found")

    farmer = db.query(Farmer).filter(Farmer.id == cycle.farmer_id).first()
    parcel = db.query(Parcel).filter(Parcel.id == cycle.parcel_id).first()
    project = db.query(Project).filter(Project.id == cycle.project_id).first() if cycle.project_id else None
    stages = (
        db.query(CropStageInstance)
        .filter(CropStageInstance.crop_cycle_id == cycle.id, CropStageInstance.tenant_id == x_tenant_id)
        .order_by(CropStageInstance.stage_order.asc())
        .all()
    )
    stage_by_id = {stage.id: stage for stage in stages}
    activities = (
        db.query(CropActivity)
        .filter(CropActivity.crop_cycle_id == cycle.id, CropActivity.tenant_id == x_tenant_id)
        .order_by(CropActivity.activity_date.asc(), CropActivity.created_at.asc())
        .all()
    )
    activity_rows = [_activity_trace_row(activity, cycle, stage_by_id.get(activity.stage_instance_id), farmer, parcel) for activity in activities]
    activity_count_by_stage = defaultdict(int)
    cost_by_stage = defaultdict(Decimal)
    for row in activity_rows:
        key = row.get("stage_code") or "UNSTAGED"
        activity_count_by_stage[key] += 1
        if row.get("cost_amount") is not None:
            cost_by_stage[key] += Decimal(str(row["cost_amount"]))

    stage_rows = []
    for stage in stages:
        stage_rows.append({
            "stage_instance_id": str(stage.id),
            "stage_code": stage.stage_code,
            "stage_name": stage.stage_name,
            "stage_order": stage.stage_order,
            "status": stage.status,
            "expected_duration_days": stage.expected_duration_days,
            "planned_start_date": stage.planned_start_date.isoformat() if stage.planned_start_date else None,
            "actual_start_date": stage.actual_start_date.isoformat() if stage.actual_start_date else None,
            "actual_end_date": stage.actual_end_date.isoformat() if stage.actual_end_date else None,
            "started_by": str(stage.started_by) if stage.started_by else None,
            "completed_by": str(stage.completed_by) if stage.completed_by else None,
            "skip_reason": stage.skip_reason,
            "activity_count": activity_count_by_stage.get(stage.stage_code, 0),
            "total_cost": str(cost_by_stage.get(stage.stage_code, Decimal("0"))),
        })

    return {
        "schema_version": "crop_cycle_trace.v1",
        "tenant_id": x_tenant_id,
        "cycle": {
            "id": str(cycle.id),
            "project_id": str(cycle.project_id) if cycle.project_id else None,
            "farmer_id": str(cycle.farmer_id),
            "parcel_id": str(cycle.parcel_id),
            "crop_code": cycle.crop_code,
            "variety_code": cycle.variety_code,
            "season_code": cycle.season_code,
            "status": cycle.status,
            "lifecycle_template_id": str(cycle.lifecycle_template_id) if cycle.lifecycle_template_id else None,
            "workflow_template_version_id": str(cycle.workflow_template_version_id) if cycle.workflow_template_version_id else None,
            "planned_sowing_date": cycle.planned_sowing_date.isoformat() if cycle.planned_sowing_date else None,
            "actual_sowing_date": cycle.actual_sowing_date.isoformat() if cycle.actual_sowing_date else None,
            "expected_harvest_date": cycle.expected_harvest_date.isoformat() if cycle.expected_harvest_date else None,
            "actual_harvest_date": cycle.actual_harvest_date.isoformat() if cycle.actual_harvest_date else None,
            "reported_yield_kg": _decimal_text(cycle.reported_yield_kg),
            "reported_yield_unit": cycle.reported_yield_unit,
            "total_input_cost": _decimal_text(cycle.total_input_cost),
            "total_revenue": _decimal_text(cycle.total_revenue),
            "notes": cycle.notes,
            "created_at": cycle.created_at.isoformat() if cycle.created_at else None,
            "updated_at": cycle.updated_at.isoformat() if cycle.updated_at else None,
        },
        "project": {"id": str(project.id), "name": project.name, "status": project.status} if project else None,
        "farmer": {
            "id": str(farmer.id),
            "display_name": farmer.display_name,
            "mobile_number": farmer.mobile_number,
            "village_name": farmer.village_name_manual,
            "status": farmer.status,
        } if farmer else None,
        "parcel": {
            "id": str(parcel.id),
            "survey_number": parcel.survey_number,
            "local_name": parcel.local_name,
            "reported_area": _decimal_text(parcel.reported_area),
            "reported_area_unit": parcel.reported_area_unit,
            "ownership_type": parcel.ownership_type,
            "geometry_source": parcel.geometry_source,
            "centroid_lat": _decimal_text(parcel.centroid_lat),
            "centroid_lng": _decimal_text(parcel.centroid_lng),
            "status": parcel.status,
        } if parcel else None,
        "summary": {
            "stage_count": len(stage_rows),
            "activity_count": len(activity_rows),
            "total_cost": _decimal_sum([row.get("cost_amount") for row in activity_rows]),
            "variance_count": sum(1 for row in activity_rows if row.get("recommended_quantity") is not None and row.get("actual_quantity") is not None and Decimal(str(row["recommended_quantity"])) != Decimal(str(row["actual_quantity"]))),
        },
        "stages": stage_rows,
        "activities": activity_rows,
    }

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
