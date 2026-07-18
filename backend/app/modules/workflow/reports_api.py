"""Read-only workflow reporting APIs for admin dashboards."""
from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import io
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, FarmerProjectEnrollmentImportBatch, Parcel, Project, ProjectAppConfigAuditEvent
from app.modules.media.models import BroadcastAuditEvent, BroadcastCampaign, BroadcastDelivery, FieldEventReport, QueryThread, MediaAsset, MediaAttachment, WeatherProviderConfig, WeatherSnapshot
from app.modules.master_data.models import (
    AgriculturalInput,
    AgriculturalProduct,
    AgriculturalProductPackage,
    CropStageInputRule,
    InputCatalogImportBatch,
    Crop,
    CropCatalogImportBatch,
    CropPropagationImportBatch,
    CropPropagationType,
    CropTaxonomyImportBatch,
    CropTaxonomyNode,
    Manufacturer,
    ProductCatalogImportBatch,
    InputCategory,
    ProjectInputAssignment,
    ProjectProductApproval,
)
from app.modules.workflow.forms import FORM_REGISTRY
from app.modules.workflow.models import (
    CropActivity,
    CropCycle,
    CropStageInstance,
    WorkflowTemplate,
    WorkflowTemplateAuditEvent,
    WorkflowTemplateEnablement,
    WorkflowTemplateVersion,
)
from app.modules.sync.models import AuditChainEntry, SyncConflict, SyncProcessedEvent

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

LOOKUP_CSV_COLUMNS = [
    "entity_type",
    "id",
    "label",
    "project_id",
    "farmer_id",
    "status",
    "village",
    "crop",
    "crop_scope",
    "mobile_number",
    "survey_number",
    "area",
    "ownership_type",
    "geometry_source",
    "crop_cycle_count",
    "activity_count",
    "trace_url",
    "compliance_url",
]

SYNC_HEALTH_CSV_COLUMNS = [
    "event_id",
    "entity_type",
    "entity_id",
    "operation",
    "status",
    "server_version",
    "processed_at",
    "materialized",
    "trace_url",
]

PROJECT_TRACE_CSV_COLUMNS = [
    "project_id",
    "project_name",
    "activity_id",
    "activity_date",
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
    "stage_name",
    "activity_type",
    "input_code",
    "input_name",
    "input_rule_id",
    "product_code",
    "package_sku",
    "recommended_quantity",
    "recommended_quantity_unit",
    "actual_quantity",
    "actual_quantity_unit",
    "quantity",
    "quantity_unit",
    "cost_amount",
    "cost_currency",
    "dosage_variance_reason",
    "logged_by",
    "logging_method",
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


def _profile_completion_for_report(farmer: Farmer, parcel_count: int, soil_profile_count: int = 0) -> dict:
    missing = []
    if not farmer.display_name:
        missing.append("display_name")
    if not farmer.village_id and not farmer.village_name_manual:
        missing.append("village")
    if parcel_count == 0:
        missing.append("parcel")
    return {
        "is_complete_for_home": len(missing) == 0,
        "missing_fields": missing,
        "parcel_count": parcel_count,
        "soil_profile_count": soil_profile_count,
    }


def _launch_decision_for_report(farmer: Farmer, enrollments: list[FarmerProjectEnrollment], completion: dict) -> str:
    active_enrollments = [enrollment for enrollment in enrollments if enrollment.status == "ACTIVE"]
    if farmer.status not in {"ACTIVE", "PENDING"}:
        return "SHOW_REGISTRATION"
    if len(active_enrollments) > 1:
        return "SHOW_PROJECT_PICKER"
    if not completion["is_complete_for_home"]:
        return "SHOW_PROFILE_COMPLETION"
    return "SHOW_HOME"


def _project_enrollment_report_rows(
    *,
    db: Session,
    tenant_id: str,
    project_id: Optional[uuid.UUID],
    farmer_id: Optional[uuid.UUID],
    status: Optional[str],
    enrollment_source: Optional[str],
    q: Optional[str],
    limit: int,
):
    query = (
        db.query(FarmerProjectEnrollment, Farmer, Project)
        .join(Farmer, Farmer.id == FarmerProjectEnrollment.farmer_id)
        .join(Project, Project.id == FarmerProjectEnrollment.project_id)
        .filter(
            FarmerProjectEnrollment.tenant_id == tenant_id,
            Farmer.tenant_id == tenant_id,
            Project.tenant_id == tenant_id,
        )
    )
    if project_id:
        query = query.filter(FarmerProjectEnrollment.project_id == project_id)
    if farmer_id:
        query = query.filter(FarmerProjectEnrollment.farmer_id == farmer_id)
    if status:
        query = query.filter(FarmerProjectEnrollment.status == status.upper())
    if enrollment_source:
        query = query.filter(FarmerProjectEnrollment.enrollment_source.ilike(f"%{enrollment_source.strip()}%"))

    term = (q or "").strip()
    uuid_value = _safe_uuid(term) if term else None
    if term:
        like = f"%{term}%"
        condition = (
            Farmer.display_name.ilike(like)
            | Farmer.mobile_number.ilike(like)
            | Farmer.village_name_manual.ilike(like)
            | Project.name.ilike(like)
            | FarmerProjectEnrollment.enrollment_method.ilike(like)
            | FarmerProjectEnrollment.enrollment_source.ilike(like)
            | FarmerProjectEnrollment.status.ilike(like)
        )
        if uuid_value:
            condition = (
                condition
                | (FarmerProjectEnrollment.id == uuid_value)
                | (FarmerProjectEnrollment.farmer_id == uuid_value)
                | (FarmerProjectEnrollment.project_id == uuid_value)
                | (Farmer.id == uuid_value)
                | (Project.id == uuid_value)
            )
        query = query.filter(condition)

    records = query.order_by(FarmerProjectEnrollment.updated_at.desc(), FarmerProjectEnrollment.created_at.desc()).limit(limit).all()
    farmer_ids = {farmer.id for _, farmer, _ in records}
    parcel_ids = {uuid.UUID(str(parcel_id)) for enrollment, _, _ in records for parcel_id in (enrollment.parcel_ids or []) if parcel_id}

    parcel_counts = {owner_id: 0 for owner_id in farmer_ids}
    if farmer_ids:
        for parcel in db.query(Parcel).filter(
            Parcel.tenant_id == tenant_id,
            Parcel.farmer_id.in_(farmer_ids),
            Parcel.status != "ARCHIVED",
        ).all():
            parcel_counts[parcel.farmer_id] = parcel_counts.get(parcel.farmer_id, 0) + 1

    parcels = {
        parcel.id: parcel
        for parcel in db.query(Parcel).filter(Parcel.tenant_id == tenant_id, Parcel.id.in_(parcel_ids)).all()
    } if parcel_ids else {}

    enrollments_by_farmer = {}
    if farmer_ids:
        all_enrollments = db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == tenant_id,
            FarmerProjectEnrollment.farmer_id.in_(farmer_ids),
            FarmerProjectEnrollment.status != "ARCHIVED",
        ).all()
        for enrollment in all_enrollments:
            enrollments_by_farmer.setdefault(enrollment.farmer_id, []).append(enrollment)

    soil_counts = {owner_id: 0 for owner_id in farmer_ids}
    try:
        from app.modules.farmer.soil_profile import SoilProfile
        if farmer_ids:
            for profile in db.query(SoilProfile).filter(
                SoilProfile.tenant_id == tenant_id,
                SoilProfile.farmer_id.in_(farmer_ids),
            ).all():
                soil_counts[profile.farmer_id] = soil_counts.get(profile.farmer_id, 0) + 1
    except Exception:
        pass

    rows = []
    for enrollment, farmer, project in records:
        linked_parcels = [parcels.get(uuid.UUID(str(parcel_id))) for parcel_id in (enrollment.parcel_ids or []) if parcel_id]
        linked_parcels = [parcel for parcel in linked_parcels if parcel]
        completion = _profile_completion_for_report(farmer, parcel_counts.get(farmer.id, 0), soil_counts.get(farmer.id, 0))
        farmer_enrollments = enrollments_by_farmer.get(farmer.id, [])
        decision = _launch_decision_for_report(farmer, farmer_enrollments, completion)
        active_count = len([item for item in farmer_enrollments if item.status == "ACTIVE"])
        rows.append({
            "id": str(enrollment.id),
            "tenant_id": enrollment.tenant_id,
            "farmer_id": str(farmer.id),
            "farmer_name": farmer.display_name,
            "farmer_mobile": farmer.mobile_number,
            "farmer_status": farmer.status,
            "village": farmer.village_name_manual,
            "project_id": str(project.id),
            "project_name": project.name,
            "project_status": project.status,
            "enrollment_method": enrollment.enrollment_method,
            "enrollment_source": enrollment.enrollment_source,
            "enrollment_batch_id": enrollment.enrollment_batch_id,
            "enrolled_by": str(enrollment.enrolled_by) if enrollment.enrolled_by else None,
            "status": enrollment.status,
            "parcel_ids": enrollment.parcel_ids or [],
            "parcel_labels": [parcel.survey_number or parcel.local_name or str(parcel.id) for parcel in linked_parcels],
            "assigned_user_ids": enrollment.assigned_user_ids or [],
            "metadata": enrollment.metadata_ or {},
            "notes": enrollment.notes,
            "created_at": enrollment.created_at.isoformat() if enrollment.created_at else None,
            "updated_at": enrollment.updated_at.isoformat() if enrollment.updated_at else None,
            "launch_context": {
                "recommended_navigation": decision,
                "project_selection_required": active_count > 1,
                "active_project_count": active_count,
                "profile_completion": completion,
                "bootstrap_endpoint": f"/api/v1/app-config/bootstrap?project_id={project.id}" if active_count == 1 and enrollment.status == "ACTIVE" else "/api/v1/app-config/bootstrap",
                "launch_context_endpoint": f"/api/v1/farmers/{farmer.id}/launch-context",
            },
        })
    return rows


def _project_enrollment_report_payload(tenant_id: str, rows: list[dict], filters: dict) -> dict:
    by_status = defaultdict(int)
    by_source = defaultdict(int)
    navigation = defaultdict(int)
    for row in rows:
        by_status[row["status"] or "UNKNOWN"] += 1
        by_source[row["enrollment_source"] or row["enrollment_method"] or "UNKNOWN"] += 1
        navigation[row["launch_context"]["recommended_navigation"]] += 1
    return {
        "schema_version": "project_enrollment_report.v1",
        "tenant_id": tenant_id,
        "filters": filters,
        "summary": {
            "count": len(rows),
            "active_count": by_status.get("ACTIVE", 0),
            "pending_count": by_status.get("PENDING", 0),
            "archived_count": by_status.get("ARCHIVED", 0),
            "project_picker_count": navigation.get("SHOW_PROJECT_PICKER", 0),
            "profile_completion_count": navigation.get("SHOW_PROFILE_COMPLETION", 0),
            "by_status": dict(sorted(by_status.items())),
            "by_source": dict(sorted(by_source.items())),
            "by_recommended_navigation": dict(sorted(navigation.items())),
        },
        "enrollments": rows,
    }


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


def _media_asset_trace_payload(asset: MediaAsset) -> dict:
    return {
        "id": str(asset.id),
        "media_type": asset.media_type,
        "mime_type": asset.mime_type,
        "upload_status": asset.upload_status,
        "storage_url": asset.storage_url,
        "thumbnail_url": asset.thumbnail_url,
        "sha256_hash": asset.sha256_hash,
        "size_bytes": asset.size_bytes,
        "duration_seconds": asset.duration_seconds,
        "capture_lat": asset.capture_lat,
        "capture_lng": asset.capture_lng,
        "capture_accuracy_meters": asset.capture_accuracy_meters,
        "captured_at": asset.captured_at.isoformat() if asset.captured_at else None,
        "metadata": asset.metadata_ or {},
    }


def _media_attachment_trace_payload(attachment: MediaAttachment, asset: MediaAsset) -> dict:
    return {
        "id": str(attachment.id),
        "media_asset_id": str(attachment.media_asset_id),
        "entity_type": attachment.entity_type,
        "entity_id": str(attachment.entity_id),
        "purpose": attachment.purpose,
        "caption": attachment.caption,
        "display_order": attachment.display_order,
        "is_primary": attachment.is_primary,
        "metadata": attachment.metadata_ or {},
        "asset": _media_asset_trace_payload(asset),
        "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
        "updated_at": attachment.updated_at.isoformat() if attachment.updated_at else None,
    }


def _media_attachments_for_entity(db: Session, tenant_id: str, entity_type: str, entity_id, limit: int = 25) -> list[dict]:
    if not entity_id:
        return []
    rows = (
        db.query(MediaAttachment, MediaAsset)
        .join(MediaAsset, MediaAsset.id == MediaAttachment.media_asset_id)
        .filter(
            MediaAttachment.tenant_id == tenant_id,
            MediaAttachment.entity_type == entity_type,
            MediaAttachment.entity_id == entity_id,
            MediaAttachment.is_active == True,
        )
        .order_by(MediaAttachment.display_order.asc(), MediaAttachment.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_media_attachment_trace_payload(attachment, asset) for attachment, asset in rows]


def _media_attachment_count(db: Session, tenant_id: str, entity_type: str, entity_id) -> int:
    if not entity_id:
        return 0
    return db.query(MediaAttachment).filter(
        MediaAttachment.tenant_id == tenant_id,
        MediaAttachment.entity_type == entity_type,
        MediaAttachment.entity_id == entity_id,
        MediaAttachment.is_active == True,
    ).count()


def _activity_usage_csv(rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ACTIVITY_USAGE_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column) for column in ACTIVITY_USAGE_CSV_COLUMNS})
    buffer.seek(0)
    return buffer.getvalue()


def _rows_csv(rows, columns):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column) for column in columns})
    buffer.seek(0)
    return buffer.getvalue()


def _csv_stream(csv_text: str, filename: str):
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



def _activity_trace_row(activity, cycle, stage, farmer, parcel, media_attachment_count: int = 0):
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
        "media_attachment_count": media_attachment_count,
    }



def _sync_event_entity_type(value):
    return (value or "UNKNOWN").upper()


def _sync_materialization_status(entity_type: str, entity_id, farmers_by_id, parcels_by_id):
    normalized_type = _sync_event_entity_type(entity_type)
    if normalized_type == "FARMER":
        return entity_id in farmers_by_id
    if normalized_type == "PARCEL":
        return entity_id in parcels_by_id
    if normalized_type in {"PARCEL_GEOMETRY", "PARCELGEOMETRY"}:
        parcel = parcels_by_id.get(entity_id)
        return bool(parcel and parcel.geometry_source and parcel.geometry_source != "NONE")
    return None


@router.get("/project-enrollments")
def project_enrollment_report(
    project_id: Optional[uuid.UUID] = Query(None),
    farmer_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    enrollment_source: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    """Read-only admin visibility into farmer/project enrollment membership."""
    if project_id:
        project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
        if not project:
            raise HTTPException(404, "Project not found")
    if farmer_id:
        farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == x_tenant_id).first()
        if not farmer:
            raise HTTPException(404, "Farmer not found")

    normalized_status = status.upper() if status else None
    if normalized_status and normalized_status not in {"PENDING", "ACTIVE", "COMPLETED", "ARCHIVED", "CANCELLED"}:
        raise HTTPException(400, "status must be PENDING, ACTIVE, COMPLETED, ARCHIVED, or CANCELLED")

    filters = {
        "project_id": str(project_id) if project_id else None,
        "farmer_id": str(farmer_id) if farmer_id else None,
        "status": normalized_status,
        "enrollment_source": enrollment_source,
        "q": q or "",
        "limit": limit,
    }
    rows = _project_enrollment_report_rows(
        db=db,
        tenant_id=x_tenant_id,
        project_id=project_id,
        farmer_id=farmer_id,
        status=normalized_status,
        enrollment_source=enrollment_source,
        q=q,
        limit=limit,
    )
    return _project_enrollment_report_payload(x_tenant_id, rows, filters)


@router.get("/sync-health")
def sync_materialization_health_report(
    project_id: Optional[uuid.UUID] = Query(None),
    entity_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    gap_only: bool = Query(False),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    event_query = db.query(SyncProcessedEvent).filter(SyncProcessedEvent.tenant_id == x_tenant_id)
    if entity_type:
        event_query = event_query.filter(SyncProcessedEvent.entity_type.ilike(entity_type))
    if status:
        event_query = event_query.filter(SyncProcessedEvent.status == status.upper())

    events = event_query.order_by(SyncProcessedEvent.processed_at.desc()).all()
    farmer_query = db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id)
    parcel_query = db.query(Parcel).filter(Parcel.tenant_id == x_tenant_id)
    if project_id:
        farmer_query = farmer_query.filter(Farmer.project_id == project_id)
        parcel_query = parcel_query.filter(Parcel.project_id == project_id)
        project_farmer_ids = {row.id for row in farmer_query.all()}
        project_parcel_ids = {row.id for row in parcel_query.all()}
        events = [
            event for event in events
            if (event.entity_type or "").upper() not in {"FARMER", "PARCEL", "PARCEL_GEOMETRY", "PARCELGEOMETRY"}
            or event.entity_id in project_farmer_ids
            or event.entity_id in project_parcel_ids
        ]
        farmers = list(project_farmer_ids)
        parcels = list(project_parcel_ids)
    else:
        farmers = farmer_query.all()
        parcels = parcel_query.all()
        project_farmer_ids = {farmer.id for farmer in farmers}
        project_parcel_ids = {parcel.id for parcel in parcels}

    farmers_by_id = {farmer.id: farmer for farmer in db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id).all()}
    parcels_by_id = {parcel.id: parcel for parcel in db.query(Parcel).filter(Parcel.tenant_id == x_tenant_id).all()}
    status_counts = defaultdict(int)
    entity_counts = defaultdict(int)
    committed_counts = defaultdict(int)
    materialized_counts = defaultdict(int)
    unmaterialized_counts = defaultdict(int)
    recent_rows = []

    filtered_events = []
    for event in events:
        event_entity_type = _sync_event_entity_type(event.entity_type)
        materialized = _sync_materialization_status(event_entity_type, event.entity_id, farmers_by_id, parcels_by_id)
        is_gap = event.status == "COMMITTED" and materialized is False
        if gap_only and not is_gap:
            continue
        filtered_events.append(event)
        status_counts[event.status or "UNKNOWN"] += 1
        entity_counts[event_entity_type] += 1
        if event.status == "COMMITTED":
            committed_counts[event_entity_type] += 1
            if materialized is True:
                materialized_counts[event_entity_type] += 1
            elif materialized is False:
                unmaterialized_counts[event_entity_type] += 1
        if len(recent_rows) < limit:
            recent_rows.append({
                "event_id": str(event.event_id),
                "entity_type": event_entity_type,
                "entity_id": str(event.entity_id) if event.entity_id else None,
                "operation": event.operation,
                "status": event.status,
                "server_version": event.server_version,
                "processed_at": event.processed_at.isoformat() if event.processed_at else None,
                "materialized": materialized,
                "trace_url": (
                    f"/farmer-trace/{event.entity_id}" if event_entity_type == "FARMER" and event.entity_id in farmers_by_id else
                    f"/parcel-trace/{event.entity_id}" if event_entity_type in {"PARCEL", "PARCEL_GEOMETRY", "PARCELGEOMETRY"} and event.entity_id in parcels_by_id else
                    None
                ),
            })

    conflicts = db.query(SyncConflict).filter(SyncConflict.tenant_id == x_tenant_id).all()
    audit_count = db.query(AuditChainEntry).filter(AuditChainEntry.tenant_id == x_tenant_id).count()
    latest_audit = (
        db.query(AuditChainEntry)
        .filter(AuditChainEntry.tenant_id == x_tenant_id)
        .order_by(AuditChainEntry.id.desc())
        .first()
    )
    real_farmers = farmer_query.count()
    real_parcels = parcel_query.count()
    geometry_captured_count = parcel_query.filter(Parcel.geometry_source.isnot(None), Parcel.geometry_source != "NONE").count()
    geometry_missing_count = parcel_query.filter((Parcel.geometry_source.is_(None)) | (Parcel.geometry_source == "NONE")).count()

    return {
        "schema_version": "sync_materialization_health.v1",
        "tenant_id": x_tenant_id,
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "entity_type": entity_type.upper() if entity_type else None,
            "status": status.upper() if status else None,
            "gap_only": gap_only,
            "limit": limit,
        },
        "summary": {
            "event_count": len(filtered_events),
            "committed_count": status_counts.get("COMMITTED", 0),
            "failed_count": status_counts.get("FAILED", 0),
            "conflict_count": len(conflicts),
            "dependency_missing_count": status_counts.get("DEPENDENCY_MISSING", 0),
            "farmer_count": real_farmers,
            "parcel_count": real_parcels,
            "geometry_captured_count": geometry_captured_count,
            "geometry_missing_count": geometry_missing_count,
            "audit_chain_count": audit_count,
            "latest_audit_at": latest_audit.created_at.isoformat() if latest_audit and latest_audit.created_at else None,
        },
        "status_counts": [{"status": key, "event_count": value} for key, value in sorted(status_counts.items())],
        "entity_counts": [{"entity_type": key, "event_count": value} for key, value in sorted(entity_counts.items())],
        "materialization": [
            {
                "entity_type": key,
                "committed_count": committed_counts.get(key, 0),
                "materialized_count": materialized_counts.get(key, 0),
                "unmaterialized_count": unmaterialized_counts.get(key, 0),
            }
            for key in sorted(set(committed_counts) | set(materialized_counts) | set(unmaterialized_counts))
        ],
        "recent_events": recent_rows,
    }



@router.get("/sync-health.csv")
def sync_materialization_health_report_csv(
    project_id: Optional[uuid.UUID] = Query(None),
    entity_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    gap_only: bool = Query(False),
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    payload = sync_materialization_health_report(
        project_id=project_id,
        entity_type=entity_type,
        status=status,
        gap_only=gap_only,
        limit=min(limit, 100),
        db=db,
        x_tenant_id=x_tenant_id,
        principal=principal,
    )
    rows = payload["recent_events"]
    filename = "sync_health_gaps.csv" if gap_only else "sync_health.csv"
    return _csv_stream(_rows_csv(rows, SYNC_HEALTH_CSV_COLUMNS), filename)


def _admin_project_row(project, cycles_by_project):
    project_cycles = cycles_by_project.get(project.id, [])
    return {
        "id": str(project.id),
        "label": project.name,
        "name": project.name,
        "status": project.status,
        "crop_scope": project.crop_scope or [],
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "crop_cycle_count": len(project_cycles),
        "trace_url": f"/project-trace/{project.id}",
        "compliance_url": f"/project-compliance/{project.id}",
    }


def _admin_farmer_row(farmer, cycles_by_farmer, activities_by_farmer):
    label = farmer.display_name or farmer.mobile_number or str(farmer.id)
    return {
        "id": str(farmer.id),
        "label": label,
        "display_name": farmer.display_name,
        "mobile_number": farmer.mobile_number,
        "village_name": farmer.village_name_manual,
        "primary_crop_code": farmer.primary_crop_code,
        "project_id": str(farmer.project_id) if farmer.project_id else None,
        "status": farmer.status,
        "crop_cycle_count": len(cycles_by_farmer.get(farmer.id, [])),
        "activity_count": len(activities_by_farmer.get(farmer.id, [])),
        "trace_url": f"/farmer-trace/{farmer.id}",
    }


def _admin_parcel_row(parcel, farmer, cycles_by_parcel, activities_by_parcel):
    label = parcel.local_name or parcel.survey_number or str(parcel.id)
    return {
        "id": str(parcel.id),
        "label": label,
        "survey_number": parcel.survey_number,
        "local_name": parcel.local_name,
        "farmer_id": str(parcel.farmer_id),
        "farmer_name": farmer.display_name if farmer else None,
        "project_id": str(parcel.project_id) if parcel.project_id else None,
        "reported_area": _decimal_text(parcel.reported_area),
        "reported_area_unit": parcel.reported_area_unit,
        "ownership_type": parcel.ownership_type,
        "annual_rent": _decimal_text(parcel.annual_rent),
        "annual_rent_currency": parcel.annual_rent_currency,
        "share_percentage": parcel.share_percentage,
        "sharecrop_percentage": parcel.sharecrop_percentage,
        "village_name": parcel.village_name_manual,
        "pin_code": parcel.pin_code,
        "location_scope": parcel.location_scope or {},
        "irrigation_source": parcel.irrigation_source,
        "geometry_source": parcel.geometry_source,
        "status": parcel.status,
        "crop_cycle_count": len(cycles_by_parcel.get(parcel.id, [])),
        "activity_count": len(activities_by_parcel.get(parcel.id, [])),
        "trace_url": f"/parcel-trace/{parcel.id}",
    }



def _admin_backlog_counts(db: Session, *, tenant_id: str, project_id: Optional[uuid.UUID]) -> dict:
    workflow_query = (
        db.query(WorkflowTemplateVersion, WorkflowTemplate)
        .join(WorkflowTemplate, WorkflowTemplate.id == WorkflowTemplateVersion.template_id)
        .filter(
            WorkflowTemplate.tenant_id == tenant_id,
            WorkflowTemplateVersion.is_active == True,
            WorkflowTemplateVersion.status == "DRAFT",
        )
    )
    if project_id:
        workflow_query = workflow_query.filter(or_(WorkflowTemplate.project_id == project_id, WorkflowTemplate.project_id == None))
    draft_rows = workflow_query.all()

    validation_blocker_count = 0
    unvalidated_draft_count = 0
    stale_validation_count = 0
    error_validation_count = 0
    for version, _template in draft_rows:
        latest_validation = (
            db.query(WorkflowTemplateAuditEvent)
            .filter(
                WorkflowTemplateAuditEvent.template_version_id == version.id,
                WorkflowTemplateAuditEvent.action == "VALIDATE_DRAFT",
            )
            .order_by(WorkflowTemplateAuditEvent.created_at.desc())
            .first()
        )
        if not latest_validation:
            unvalidated_draft_count += 1
            validation_blocker_count += 1
            continue
        if version.updated_at and latest_validation.created_at and latest_validation.created_at < version.updated_at:
            stale_validation_count += 1
            validation_blocker_count += 1
            continue
        after_payload = latest_validation.after or {}
        counts = after_payload.get("counts") or {}
        if after_payload.get("can_publish") is False or int(counts.get("errors") or 0) > 0:
            error_validation_count += 1
            validation_blocker_count += 1

    input_query = db.query(AgriculturalInput).filter(AgriculturalInput.is_active == True)
    input_review_count = input_query.filter(AgriculturalInput.catalog_status == "REVIEW").count()
    input_draft_count = input_query.filter(AgriculturalInput.catalog_status == "DRAFT").count()
    input_rejected_count = input_query.filter(AgriculturalInput.catalog_status == "REJECTED").count()
    csv_pending_count = db.query(InputCatalogImportBatch).filter(
        InputCatalogImportBatch.tenant_id == tenant_id,
        InputCatalogImportBatch.status == "VALIDATED",
    ).count()
    product_csv_pending_count = db.query(ProductCatalogImportBatch).filter(
        ProductCatalogImportBatch.tenant_id == tenant_id,
        ProductCatalogImportBatch.status == "VALIDATED",
        ProductCatalogImportBatch.is_active == True,
    ).count()
    product_csv_invalid_count = db.query(ProductCatalogImportBatch).filter(
        ProductCatalogImportBatch.tenant_id == tenant_id,
        ProductCatalogImportBatch.status == "INVALID",
        ProductCatalogImportBatch.is_active == True,
    ).count()
    enrollment_import_query = db.query(FarmerProjectEnrollmentImportBatch).filter(
        FarmerProjectEnrollmentImportBatch.tenant_id == tenant_id,
        FarmerProjectEnrollmentImportBatch.is_active == True,
    )
    if project_id:
        enrollment_import_query = enrollment_import_query.filter(FarmerProjectEnrollmentImportBatch.project_id == project_id)
    enrollment_csv_pending_count = enrollment_import_query.filter(FarmerProjectEnrollmentImportBatch.status == "VALIDATED").count()
    enrollment_csv_invalid_count = enrollment_import_query.filter(FarmerProjectEnrollmentImportBatch.status == "INVALID").count()

    broadcast_query = db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == tenant_id, BroadcastCampaign.is_active == True)
    if project_id:
        broadcast_query = broadcast_query.filter(BroadcastCampaign.project_id == project_id)
    broadcast_draft_count = broadcast_query.filter(BroadcastCampaign.status == "DRAFT").count()
    broadcast_published_count = broadcast_query.filter(BroadcastCampaign.status == "PUBLISHED").count()
    broadcast_delivery_query = db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == tenant_id)
    if project_id:
        campaign_ids = [row[0] for row in db.query(BroadcastCampaign.id).filter(BroadcastCampaign.tenant_id == tenant_id, BroadcastCampaign.project_id == project_id).all()]
        broadcast_delivery_query = broadcast_delivery_query.filter(BroadcastDelivery.campaign_id.in_(campaign_ids or [uuid.uuid4()]))
    broadcast_pending_delivery_count = broadcast_delivery_query.filter(BroadcastDelivery.delivery_status == "PENDING").count()

    now_ts = datetime.now(timezone.utc)
    weather_provider_query = db.query(WeatherProviderConfig).filter(
        WeatherProviderConfig.tenant_id == tenant_id,
        WeatherProviderConfig.is_enabled == True,
    )
    weather_provider_enabled_count = weather_provider_query.count()
    weather_provider_due_count = weather_provider_query.filter(
        or_(WeatherProviderConfig.next_refresh_at.is_(None), WeatherProviderConfig.next_refresh_at <= now_ts)
    ).count()
    weather_snapshot_query = db.query(WeatherSnapshot).filter(WeatherSnapshot.tenant_id == tenant_id)
    if project_id:
        weather_snapshot_query = weather_snapshot_query.filter(
            or_(WeatherSnapshot.project_id == project_id, WeatherSnapshot.location_scope == "TENANT")
        )
    weather_fresh_snapshot_count = weather_snapshot_query.filter(
        or_(WeatherSnapshot.expires_at.is_(None), WeatherSnapshot.expires_at > now_ts)
    ).count()

    return {
        "draft_workflow_count": len(draft_rows),
        "workflow_validation_blocker_count": validation_blocker_count,
        "unvalidated_draft_workflow_count": unvalidated_draft_count,
        "stale_validation_count": stale_validation_count,
        "workflow_validation_error_count": error_validation_count,
        "input_review_count": input_review_count,
        "input_draft_count": input_draft_count,
        "input_rejected_count": input_rejected_count,
        "csv_import_pending_count": csv_pending_count,
        "product_csv_import_pending_count": product_csv_pending_count,
        "product_csv_import_invalid_count": product_csv_invalid_count,
        "project_enrollment_csv_import_pending_count": enrollment_csv_pending_count,
        "project_enrollment_csv_import_invalid_count": enrollment_csv_invalid_count,
        "broadcast_draft_count": broadcast_draft_count,
        "broadcast_published_count": broadcast_published_count,
        "broadcast_pending_delivery_count": broadcast_pending_delivery_count,
        "weather_provider_enabled_count": weather_provider_enabled_count,
        "weather_provider_due_count": weather_provider_due_count,
        "weather_fresh_snapshot_count": weather_fresh_snapshot_count,
    }

def _admin_dashboard_payload(*, tenant_id, project_id, date_from, date_to, limit, projects, farmers, parcels, cycles, activities, field_events, admin_backlog):
    cycles_by_project = defaultdict(list)
    cycles_by_farmer = defaultdict(list)
    cycles_by_parcel = defaultdict(list)
    activities_by_farmer = defaultdict(list)
    activities_by_parcel = defaultdict(list)
    crop_distribution = defaultdict(int)
    cycle_status_distribution = defaultdict(int)
    geometry_coverage = defaultdict(int)
    activity_count_by_type = defaultdict(int)
    field_event_count_by_type = defaultdict(int)
    field_event_count_by_severity = defaultdict(int)
    unresolved_field_event_count = 0
    high_priority_field_event_count = 0
    variance_count = 0

    farmers_by_id = {farmer.id: farmer for farmer in farmers}
    for cycle in cycles:
        if cycle.project_id:
            cycles_by_project[cycle.project_id].append(cycle)
        if cycle.farmer_id:
            cycles_by_farmer[cycle.farmer_id].append(cycle)
        if cycle.parcel_id:
            cycles_by_parcel[cycle.parcel_id].append(cycle)
        crop_distribution[cycle.crop_code or "UNKNOWN"] += 1
        cycle_status_distribution[cycle.status or "UNKNOWN"] += 1

    for parcel in parcels:
        geometry_coverage[parcel.geometry_source or "MISSING"] += 1

    for field_event in field_events:
        field_event_count_by_type[field_event.event_type or "UNKNOWN"] += 1
        field_event_count_by_severity[field_event.severity or "UNKNOWN"] += 1
        if field_event.status not in {"RESOLVED", "DISMISSED"}:
            unresolved_field_event_count += 1
        if field_event.status not in {"RESOLVED", "DISMISSED"} and field_event.severity in {"HIGH", "CRITICAL"}:
            high_priority_field_event_count += 1

    for row in activities:
        if row.get("farmer_id"):
            activities_by_farmer[uuid.UUID(row["farmer_id"])].append(row)
        if row.get("parcel_id"):
            activities_by_parcel[uuid.UUID(row["parcel_id"])].append(row)
        activity_count_by_type[row.get("activity_type") or "UNKNOWN"] += 1
        if row.get("recommended_quantity") is not None and row.get("actual_quantity") is not None:
            if Decimal(str(row["recommended_quantity"])) != Decimal(str(row["actual_quantity"])):
                variance_count += 1

    return {
        "schema_version": "admin_dashboard.v1",
        "tenant_id": tenant_id,
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "limit": limit,
        },
        "summary": {
            "project_count": len(projects),
            "farmer_count": len(farmers),
            "parcel_count": len(parcels),
            "crop_cycle_count": len(cycles),
            "active_cycle_count": sum(1 for cycle in cycles if cycle.status == "ACTIVE"),
            "completed_cycle_count": sum(1 for cycle in cycles if cycle.status == "COMPLETED"),
            "activity_count": len(activities),
            "field_event_count": len(field_events),
            "unresolved_field_event_count": unresolved_field_event_count,
            "high_priority_field_event_count": high_priority_field_event_count,
            "total_cost": _decimal_sum([row.get("cost_amount") for row in activities]),
            "variance_count": variance_count,
            "geometry_captured_count": sum(1 for parcel in parcels if parcel.geometry_source and parcel.geometry_source != "NONE"),
            "geometry_missing_count": sum(1 for parcel in parcels if not parcel.geometry_source or parcel.geometry_source == "NONE"),
            "admin_backlog": admin_backlog,
        },
        "crop_distribution": [
            {"crop_code": key, "crop_cycle_count": value}
            for key, value in sorted(crop_distribution.items())
        ],
        "cycle_status_distribution": [
            {"status": key, "crop_cycle_count": value}
            for key, value in sorted(cycle_status_distribution.items())
        ],
        "geometry_coverage": [
            {"geometry_source": key, "parcel_count": value}
            for key, value in sorted(geometry_coverage.items())
        ],
        "activity_count_by_type": [
            {"activity_type": key, "activity_count": value}
            for key, value in sorted(activity_count_by_type.items())
        ],
        "field_event_count_by_type": [
            {"event_type": key, "field_event_count": value}
            for key, value in sorted(field_event_count_by_type.items())
        ],
        "field_event_count_by_severity": [
            {"severity": key, "field_event_count": value}
            for key, value in sorted(field_event_count_by_severity.items())
        ],
        "recent_field_events": [
            {
                "id": str(event.id),
                "project_id": str(event.project_id) if event.project_id else None,
                "farmer_id": str(event.farmer_id),
                "parcel_id": str(event.parcel_id) if event.parcel_id else None,
                "crop_cycle_id": str(event.crop_cycle_id) if event.crop_cycle_id else None,
                "stage_code": event.stage_code,
                "event_type": event.event_type,
                "severity": event.severity,
                "status": event.status,
                "event_date": _iso(event.event_date),
                "reported_at": _iso(event.reported_at),
                "description": event.description,
            }
            for event in field_events[:limit]
        ],
        "projects": [_admin_project_row(project, cycles_by_project) for project in projects[:limit]],
        "farmers": [_admin_farmer_row(farmer, cycles_by_farmer, activities_by_farmer) for farmer in farmers[:limit]],
        "parcels": [
            _admin_parcel_row(parcel, farmers_by_id.get(parcel.farmer_id), cycles_by_parcel, activities_by_parcel)
            for parcel in parcels[:limit]
        ],
        "activities": activities[:limit],
    }




def _readiness_item(code: str, label: str, ready: bool, detail: str, href: str, severity: str = "WARN") -> dict:
    return {
        "code": code,
        "label": label,
        "ready": bool(ready),
        "severity": "OK" if ready else severity,
        "detail": detail,
        "href": href,
    }


@router.get("/system-readiness")
def system_readiness_report(
    project_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    project_query = db.query(Project).filter(Project.tenant_id == x_tenant_id)
    farmer_query = db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id)
    parcel_query = db.query(Parcel).filter(Parcel.tenant_id == x_tenant_id)
    cycle_query = db.query(CropCycle).filter(CropCycle.tenant_id == x_tenant_id)
    activity_query = db.query(CropActivity).filter(CropActivity.tenant_id == x_tenant_id)

    if project_id:
        project = project_query.filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(404, "Project not found")
        project_query = project_query.filter(Project.id == project_id)
        farmer_query = farmer_query.filter(Farmer.project_id == project_id)
        parcel_query = parcel_query.filter(Parcel.project_id == project_id)
        cycle_query = cycle_query.filter(CropCycle.project_id == project_id)
        activity_query = activity_query.join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id).filter(CropCycle.project_id == project_id)

    project_count = project_query.count()
    farmer_count = farmer_query.count()
    parcel_count = parcel_query.count()
    cycle_count = cycle_query.count()
    activity_count = activity_query.count()
    geometry_missing_count = parcel_query.filter((Parcel.geometry_source.is_(None)) | (Parcel.geometry_source == "NONE")).count()
    geometry_captured_count = max(parcel_count - geometry_missing_count, 0)

    published_workflow_count = (
        db.query(WorkflowTemplateVersion)
        .join(WorkflowTemplate, WorkflowTemplate.id == WorkflowTemplateVersion.template_id)
        .filter(
            WorkflowTemplate.tenant_id == x_tenant_id,
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplateVersion.is_active == True,
        )
        .count()
    )
    enablement_query = db.query(WorkflowTemplateEnablement).filter(WorkflowTemplateEnablement.tenant_id == x_tenant_id)
    if project_id:
        enablement_query = enablement_query.filter(WorkflowTemplateEnablement.project_id == project_id)
    workflow_enablement_count = enablement_query.count()
    active_input_count = db.query(AgriculturalInput).filter(AgriculturalInput.is_active == True).count()
    published_input_count = db.query(AgriculturalInput).filter(AgriculturalInput.is_active == True, AgriculturalInput.catalog_status == "PUBLISHED").count()
    manufacturer_count = db.query(Manufacturer).filter(Manufacturer.is_active == True).count()
    active_product_count = db.query(AgriculturalProduct).filter(AgriculturalProduct.is_active == True, AgriculturalProduct.status == "ACTIVE").count()
    active_package_count = db.query(AgriculturalProductPackage).filter(AgriculturalProductPackage.is_active == True, AgriculturalProductPackage.status == "ACTIVE").count()
    product_import_invalid_count = db.query(ProductCatalogImportBatch).filter(ProductCatalogImportBatch.tenant_id == x_tenant_id, ProductCatalogImportBatch.status == "INVALID", ProductCatalogImportBatch.is_active == True).count()
    product_import_pending_count = db.query(ProductCatalogImportBatch).filter(ProductCatalogImportBatch.tenant_id == x_tenant_id, ProductCatalogImportBatch.status == "VALIDATED", ProductCatalogImportBatch.is_active == True).count()
    enrollment_import_query = db.query(FarmerProjectEnrollmentImportBatch).filter(FarmerProjectEnrollmentImportBatch.tenant_id == x_tenant_id, FarmerProjectEnrollmentImportBatch.is_active == True)
    if project_id:
        enrollment_import_query = enrollment_import_query.filter(FarmerProjectEnrollmentImportBatch.project_id == project_id)
    enrollment_import_invalid_count = enrollment_import_query.filter(FarmerProjectEnrollmentImportBatch.status == "INVALID").count()
    enrollment_import_pending_count = enrollment_import_query.filter(FarmerProjectEnrollmentImportBatch.status == "VALIDATED").count()
    enrollment_lifecycle_query = db.query(FarmerProjectEnrollment).filter(FarmerProjectEnrollment.tenant_id == x_tenant_id)
    if project_id:
        enrollment_lifecycle_query = enrollment_lifecycle_query.filter(FarmerProjectEnrollment.project_id == project_id)
    enrollment_active_count = enrollment_lifecycle_query.filter(FarmerProjectEnrollment.status == "ACTIVE").count()
    enrollment_pending_count = enrollment_lifecycle_query.filter(FarmerProjectEnrollment.status == "PENDING").count()
    enrollment_open_count = enrollment_active_count + enrollment_pending_count
    enrollment_total_count = enrollment_lifecycle_query.count()
    crop_taxonomy_count = db.query(CropTaxonomyNode).filter(CropTaxonomyNode.is_active == True).count()
    crop_propagation_count = db.query(CropPropagationType).filter(CropPropagationType.is_active == True).count()
    crop_catalog_count = db.query(Crop).filter(Crop.is_active == True).count()
    crop_import_invalid_count = (
        db.query(CropTaxonomyImportBatch).filter(CropTaxonomyImportBatch.status == "INVALID").count()
        + db.query(CropPropagationImportBatch).filter(CropPropagationImportBatch.status == "INVALID").count()
        + db.query(CropCatalogImportBatch).filter(CropCatalogImportBatch.status == "INVALID").count()
    )
    required_profile_form_ids = {"farmer_registration", "parcel_registration", "soil_profile"}
    profile_form_ids = set(FORM_REGISTRY.keys())
    profile_form_missing = sorted(required_profile_form_ids - profile_form_ids)
    profile_form_schemas = [FORM_REGISTRY[form_id] for form_id in required_profile_form_ids if form_id in FORM_REGISTRY]
    profile_required_field_count = sum(1 for schema in profile_form_schemas for field in schema.fields if field.required)
    profile_gps_field_count = sum(1 for schema in profile_form_schemas for field in schema.fields if field.type.startswith("GPS"))

    broadcast_query = db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == x_tenant_id, BroadcastCampaign.is_active == True)
    if project_id:
        broadcast_query = broadcast_query.filter(BroadcastCampaign.project_id == project_id)
    broadcast_campaign_count = broadcast_query.count()
    broadcast_published_count = broadcast_query.filter(BroadcastCampaign.status == "PUBLISHED").count()
    broadcast_delivery_count = db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == x_tenant_id).count()
    broadcast_audit_count = db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == x_tenant_id).count()

    weather_provider_count = db.query(WeatherProviderConfig).filter(
        WeatherProviderConfig.tenant_id == x_tenant_id,
        WeatherProviderConfig.is_enabled == True,
    ).count()
    weather_snapshot_query = db.query(WeatherSnapshot).filter(WeatherSnapshot.tenant_id == x_tenant_id)
    if project_id:
        weather_snapshot_query = weather_snapshot_query.filter(
            or_(
                WeatherSnapshot.project_id == project_id,
                WeatherSnapshot.location_scope == "TENANT",
            )
        )
    weather_snapshot_count = weather_snapshot_query.count()
    now_ts = datetime.now(timezone.utc)
    weather_fresh_snapshot_count = weather_snapshot_query.filter(
        or_(WeatherSnapshot.expires_at.is_(None), WeatherSnapshot.expires_at > now_ts)
    ).count()

    backlog = _admin_backlog_counts(db, tenant_id=x_tenant_id, project_id=project_id)
    sync_payload = sync_materialization_health_report(
        project_id=project_id,
        entity_type=None,
        status=None,
        gap_only=False,
        limit=1,
        db=db,
        x_tenant_id=x_tenant_id,
        principal=principal,
    )
    sync_summary = sync_payload["summary"]
    materialization_gaps = sum(row["unmaterialized_count"] for row in sync_payload["materialization"])
    sync_issue_count = sync_summary["failed_count"] + sync_summary["conflict_count"] + sync_summary["dependency_missing_count"] + materialization_gaps

    lookup_href = f"/lookup?projectId={project_id}" if project_id else "/lookup"
    activity_href = f"/activity-usage?projectId={project_id}" if project_id else "/activity-usage"
    checks = [
        _readiness_item("PROJECT_SETUP", "Project setup", project_count > 0, f"{project_count} projects available", "/projects"),
        _readiness_item("WORKFLOW_RUNTIME", "Workflow runtime", published_workflow_count > 0 and backlog["workflow_validation_blocker_count"] == 0, f"{published_workflow_count} published workflows, {backlog['workflow_validation_blocker_count']} blockers", "/workflows?filter=validation-blockers"),
        _readiness_item("WORKFLOW_ASSIGNMENTS", "Workflow assignments", (not project_id) or workflow_enablement_count > 0, f"{workflow_enablement_count} project workflow assignment rows", "/project-workflows", "INFO"),
        _readiness_item("CROP_SETUP", "Crop setup", crop_taxonomy_count > 0 and crop_propagation_count > 0 and crop_catalog_count > 0 and crop_import_invalid_count == 0, f"{crop_taxonomy_count} taxonomy nodes, {crop_propagation_count} propagation types, {crop_catalog_count} crops, {crop_import_invalid_count} invalid import batches", "/crop-taxonomy"),
        _readiness_item("PROFILE_FORMS", "Profile forms", not profile_form_missing and profile_gps_field_count >= 2, f"{len(profile_form_schemas)} profile forms, {profile_required_field_count} required fields, {profile_gps_field_count} GPS widgets, missing: {', '.join(profile_form_missing) if profile_form_missing else 'none'}", "/profile-forms"),
        _readiness_item("INPUT_CATALOG", "Input catalog", published_input_count > 0, f"{published_input_count} published inputs, {active_input_count} active inputs", "/inputs"),
        _readiness_item("PRODUCT_CATALOG", "Product catalog", active_product_count > 0 and active_package_count > 0 and product_import_invalid_count == 0, f"{manufacturer_count} manufacturers, {active_product_count} active products/brands, {active_package_count} active packages, {product_import_invalid_count} invalid import batches, {product_import_pending_count} pending apply", "/products", "WARN" if product_import_invalid_count else "INFO"),
        _readiness_item("BROADCASTS", "Broadcasts", broadcast_campaign_count > 0 and (broadcast_published_count > 0 or not project_id), f"{broadcast_campaign_count} campaigns, {broadcast_published_count} published, {broadcast_delivery_count} deliveries, {broadcast_audit_count} audit events", "/broadcasts", "INFO"),
        _readiness_item("WEATHER_SNAPSHOTS", "Weather snapshots", weather_provider_count > 0 and weather_fresh_snapshot_count > 0, f"{weather_provider_count} enabled providers, {weather_snapshot_count} snapshots, {weather_fresh_snapshot_count} fresh/non-expired", "/broadcasts", "INFO"),
        _readiness_item("PROJECT_ENROLLMENT_IMPORTS", "Project enrollment imports", enrollment_import_invalid_count == 0, f"{enrollment_import_invalid_count} invalid import batches, {enrollment_import_pending_count} pending apply", f"/project-enrollments{'?projectId=' + str(project_id) if project_id else ''}", "WARN" if enrollment_import_invalid_count else "INFO"),
        _readiness_item("PROJECT_ENROLLMENT_LIFECYCLE", "Project enrollment lifecycle", (not project_id) or enrollment_open_count == 0, f"{enrollment_open_count} active/pending enrollment rows, {enrollment_total_count} total", f"/project-enrollments{'?projectId=' + str(project_id) if project_id else ''}", "WARN" if project_id else "INFO"),
        _readiness_item("FARMER_SYNC", "Farmer sync", farmer_count > 0, f"{farmer_count} farmers materialized", lookup_href),
        _readiness_item("PARCEL_GEOMETRY", "Parcel geometry", parcel_count > 0 and geometry_missing_count == 0, f"{geometry_captured_count} captured, {geometry_missing_count} missing", f"{lookup_href}{'&' if '?' in lookup_href else '?'}geometryStatus=MISSING"),
        _readiness_item("ACTIVITY_EVIDENCE", "Activity evidence", activity_count > 0, f"{activity_count} logged activities", activity_href),
        _readiness_item("SYNC_HEALTH", "Sync health", sync_issue_count == 0, f"{sync_issue_count} sync/materialization issues", "/sync-health?gapOnly=true" if sync_issue_count else "/sync-health"),
    ]
    ready_count = sum(1 for item in checks if item["ready"])
    return {
        "schema_version": "system_readiness.v1",
        "tenant_id": x_tenant_id,
        "filters": {"project_id": str(project_id) if project_id else None},
        "summary": {
            "ready_count": ready_count,
            "check_count": len(checks),
            "blocking_count": sum(1 for item in checks if not item["ready"] and item["severity"] == "WARN"),
            "info_count": sum(1 for item in checks if not item["ready"] and item["severity"] == "INFO"),
        },
        "checks": checks,
    }


@router.get("/admin-dashboard")
def admin_dashboard_report(
    project_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    project_query = db.query(Project).filter(Project.tenant_id == x_tenant_id)
    farmer_query = db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id)
    parcel_query = db.query(Parcel).filter(Parcel.tenant_id == x_tenant_id)
    cycle_query = db.query(CropCycle).filter(CropCycle.tenant_id == x_tenant_id)

    if project_id:
        project = project_query.filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(404, "Project not found")
        project_query = project_query.filter(Project.id == project_id)
        farmer_query = farmer_query.filter(Farmer.project_id == project_id)
        parcel_query = parcel_query.filter(Parcel.project_id == project_id)
        cycle_query = cycle_query.filter(CropCycle.project_id == project_id)

    field_event_query = db.query(FieldEventReport).filter(FieldEventReport.tenant_id == x_tenant_id, FieldEventReport.is_active == True)
    if project_id:
        field_event_query = field_event_query.filter(FieldEventReport.project_id == project_id)

    activity_query = (
        db.query(CropActivity, CropCycle, CropStageInstance, Farmer, Parcel)
        .join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id)
        .outerjoin(CropStageInstance, CropStageInstance.id == CropActivity.stage_instance_id)
        .outerjoin(Farmer, Farmer.id == CropActivity.farmer_id)
        .outerjoin(Parcel, Parcel.id == CropCycle.parcel_id)
        .filter(CropActivity.tenant_id == x_tenant_id, CropCycle.tenant_id == x_tenant_id)
    )
    if project_id:
        activity_query = activity_query.filter(CropCycle.project_id == project_id)
    if date_from:
        activity_query = activity_query.filter(CropActivity.activity_date >= date_from)
        field_event_query = field_event_query.filter(FieldEventReport.event_date >= date_from)
    if date_to:
        activity_query = activity_query.filter(CropActivity.activity_date <= date_to)
        field_event_query = field_event_query.filter(FieldEventReport.event_date <= date_to)

    projects = project_query.order_by(Project.updated_at.desc(), Project.created_at.desc()).all()
    farmers = farmer_query.order_by(Farmer.updated_at.desc(), Farmer.created_at.desc()).all()
    parcels = parcel_query.order_by(Parcel.updated_at.desc(), Parcel.created_at.desc()).all()
    cycles = cycle_query.order_by(CropCycle.updated_at.desc(), CropCycle.created_at.desc()).all()
    activity_rows_raw = activity_query.order_by(CropActivity.activity_date.desc(), CropActivity.created_at.desc()).all()
    field_events = field_event_query.order_by(FieldEventReport.reported_at.desc(), FieldEventReport.created_at.desc()).all()
    activities = [
        _activity_trace_row(activity, cycle, stage, farmer, parcel)
        for activity, cycle, stage, farmer, parcel in activity_rows_raw
    ]

    admin_backlog = _admin_backlog_counts(db, tenant_id=x_tenant_id, project_id=project_id)

    return _admin_dashboard_payload(
        tenant_id=x_tenant_id,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        projects=projects,
        farmers=farmers,
        parcels=parcels,
        cycles=cycles,
        activities=activities,
        field_events=field_events,
        admin_backlog=admin_backlog,
    )


def _farmer_trace_parcel_row(parcel, cycles_by_parcel, activities_by_parcel, total_cost_by_parcel):
    parcel_cycles = cycles_by_parcel.get(parcel.id, [])
    parcel_activities = activities_by_parcel.get(parcel.id, [])
    return {
        "id": str(parcel.id),
        "project_id": str(parcel.project_id) if parcel.project_id else None,
        "survey_number": parcel.survey_number,
        "local_name": parcel.local_name,
        "display_name": parcel.local_name or parcel.survey_number or str(parcel.id),
        "reported_area": _decimal_text(parcel.reported_area),
        "reported_area_unit": parcel.reported_area_unit,
        "ownership_type": parcel.ownership_type,
        "village_name": parcel.village_name_manual,
        "current_crop_code": parcel.current_crop_code,
        "geometry_source": parcel.geometry_source,
        "centroid_lat": _decimal_text(parcel.centroid_lat),
        "centroid_lng": _decimal_text(parcel.centroid_lng),
        "computed_area_hectares": _decimal_text(parcel.computed_area_hectares),
        "status": parcel.status,
        "crop_cycle_count": len(parcel_cycles),
        "active_cycle_count": sum(1 for cycle in parcel_cycles if cycle.status == "ACTIVE"),
        "completed_cycle_count": sum(1 for cycle in parcel_cycles if cycle.status == "COMPLETED"),
        "activity_count": len(parcel_activities),
        "total_cost": _decimal_sum(total_cost_by_parcel.get(parcel.id, [])),
    }


def _farmer_trace_cycle_row(cycle, activities_by_cycle, total_cost_by_cycle):
    cycle_activities = activities_by_cycle.get(cycle.id, [])
    return {
        "id": str(cycle.id),
        "parcel_id": str(cycle.parcel_id) if cycle.parcel_id else None,
        "project_id": str(cycle.project_id) if cycle.project_id else None,
        "crop_code": cycle.crop_code,
        "season_code": cycle.season_code,
        "status": cycle.status,
        "lifecycle_template_id": str(cycle.lifecycle_template_id) if cycle.lifecycle_template_id else None,
        "workflow_template_version_id": str(cycle.workflow_template_version_id) if cycle.workflow_template_version_id else None,
        "planned_sowing_date": cycle.planned_sowing_date.isoformat() if cycle.planned_sowing_date else None,
        "expected_harvest_date": cycle.expected_harvest_date.isoformat() if cycle.expected_harvest_date else None,
        "actual_harvest_date": cycle.actual_harvest_date.isoformat() if cycle.actual_harvest_date else None,
        "activity_count": len(cycle_activities),
        "total_cost": _decimal_sum(total_cost_by_cycle.get(cycle.id, [])),
    }



def _farmer_enrollment_trace_row(enrollment: FarmerProjectEnrollment, project: Optional[Project]) -> dict:
    metadata = enrollment.metadata_ or {}
    return {
        "id": str(enrollment.id),
        "project_id": str(enrollment.project_id),
        "project_name": project.name if project else None,
        "project_status": project.status if project else None,
        "status": enrollment.status,
        "enrollment_method": enrollment.enrollment_method,
        "enrollment_source": enrollment.enrollment_source,
        "enrollment_batch_id": enrollment.enrollment_batch_id,
        "enrolled_by": str(enrollment.enrolled_by) if enrollment.enrolled_by else None,
        "parcel_ids": [str(value) for value in (enrollment.parcel_ids or [])],
        "assigned_user_ids": [str(value) for value in (enrollment.assigned_user_ids or [])],
        "metadata": metadata,
        "lifecycle_events": metadata.get("lifecycle_events") or [],
        "notes": enrollment.notes,
        "created_at": enrollment.created_at.isoformat() if enrollment.created_at else None,
        "updated_at": enrollment.updated_at.isoformat() if enrollment.updated_at else None,
    }


def _parcel_trace_payload(*, db: Session, parcel, farmer, project, cycles, activities, tenant_id):
    activities_by_cycle = defaultdict(list)
    total_cost_by_cycle = defaultdict(list)
    variance_count = 0
    for row in activities:
        cycle_key = uuid.UUID(row["crop_cycle_id"]) if row.get("crop_cycle_id") else None
        if cycle_key:
            activities_by_cycle[cycle_key].append(row)
            total_cost_by_cycle[cycle_key].append(row.get("cost_amount"))
        if row.get("recommended_quantity") is not None and row.get("actual_quantity") is not None:
            if Decimal(str(row["recommended_quantity"])) != Decimal(str(row["actual_quantity"])):
                variance_count += 1

    return {
        "schema_version": "parcel_trace.v1",
        "tenant_id": tenant_id,
        "parcel": {
            "id": str(parcel.id),
            "farmer_id": str(parcel.farmer_id),
            "project_id": str(parcel.project_id) if parcel.project_id else None,
            "survey_number": parcel.survey_number,
            "local_name": parcel.local_name,
            "display_name": parcel.local_name or parcel.survey_number or str(parcel.id),
            "reported_area": _decimal_text(parcel.reported_area),
            "reported_area_unit": parcel.reported_area_unit,
            "ownership_type": parcel.ownership_type,
            "annual_rent": _decimal_text(parcel.annual_rent),
            "annual_rent_currency": parcel.annual_rent_currency,
            "share_percentage": parcel.share_percentage,
            "sharecrop_percentage": parcel.sharecrop_percentage,
            "village_name": parcel.village_name_manual,
            "pin_code": parcel.pin_code,
            "location_scope": parcel.location_scope or {},
            "irrigation_source": parcel.irrigation_source,
            "soil_type_code": parcel.soil_type_code,
            "current_crop_code": parcel.current_crop_code,
            "geometry_source": parcel.geometry_source,
            "centroid_lat": _decimal_text(parcel.centroid_lat),
            "centroid_lng": _decimal_text(parcel.centroid_lng),
            "computed_area_hectares": _decimal_text(parcel.computed_area_hectares),
            "geometry_accuracy_meters": _decimal_text(parcel.geometry_accuracy_meters),
            "geometry_captured_at": parcel.geometry_captured_at.isoformat() if parcel.geometry_captured_at else None,
            "status": parcel.status,
            "created_at": parcel.created_at.isoformat() if parcel.created_at else None,
            "updated_at": parcel.updated_at.isoformat() if parcel.updated_at else None,
            "media_attachments": _media_attachments_for_entity(db, tenant_id, "PARCEL", parcel.id),
        },
        "farmer": {
            "id": str(farmer.id),
            "project_id": str(farmer.project_id) if farmer.project_id else None,
            "mobile_number": farmer.mobile_number,
            "display_name": farmer.display_name,
            "village_name": farmer.village_name_manual,
            "primary_crop_code": farmer.primary_crop_code,
            "status": farmer.status,
        } if farmer else None,
        "project": {
            "id": str(project.id),
            "name": project.name,
            "status": project.status,
        } if project else None,
        "summary": {
            "crop_cycle_count": len(cycles),
            "active_cycle_count": sum(1 for cycle in cycles if cycle.status == "ACTIVE"),
            "completed_cycle_count": sum(1 for cycle in cycles if cycle.status == "COMPLETED"),
            "activity_count": len(activities),
            "total_cost": _decimal_sum([row.get("cost_amount") for row in activities]),
            "variance_count": variance_count,
        },
        "crop_cycles": [_farmer_trace_cycle_row(cycle, activities_by_cycle, total_cost_by_cycle) for cycle in cycles],
        "activities": activities[:250],
    }


@router.get("/parcels/{parcel_id}/trace")
def parcel_trace_report(
    parcel_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    parcel = db.query(Parcel).filter(Parcel.id == parcel_id, Parcel.tenant_id == x_tenant_id).first()
    if not parcel:
        raise HTTPException(404, "Parcel not found")

    farmer = db.query(Farmer).filter(Farmer.id == parcel.farmer_id, Farmer.tenant_id == x_tenant_id).first()
    project_id = parcel.project_id or (farmer.project_id if farmer else None)
    project = db.query(Project).filter(Project.id == project_id).first() if project_id else None
    cycles = (
        db.query(CropCycle)
        .filter(CropCycle.tenant_id == x_tenant_id, CropCycle.parcel_id == parcel.id)
        .order_by(CropCycle.created_at.asc())
        .all()
    )
    activity_rows_raw = (
        db.query(CropActivity, CropCycle, CropStageInstance, Farmer, Parcel)
        .join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id)
        .outerjoin(CropStageInstance, CropStageInstance.id == CropActivity.stage_instance_id)
        .outerjoin(Farmer, Farmer.id == CropActivity.farmer_id)
        .outerjoin(Parcel, Parcel.id == CropCycle.parcel_id)
        .filter(CropActivity.tenant_id == x_tenant_id, CropCycle.parcel_id == parcel.id)
        .order_by(CropActivity.activity_date.asc(), CropActivity.created_at.asc())
        .all()
    )
    activities = [_activity_trace_row(activity, cycle, stage, row_farmer, row_parcel) for activity, cycle, stage, row_farmer, row_parcel in activity_rows_raw]
    return _parcel_trace_payload(db=db, parcel=parcel, farmer=farmer, project=project, cycles=cycles, activities=activities, tenant_id=x_tenant_id)


@router.get("/farmers/{farmer_id}/trace")
def farmer_trace_report(
    farmer_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    farmer = db.query(Farmer).filter(Farmer.id == farmer_id, Farmer.tenant_id == x_tenant_id).first()
    if not farmer:
        raise HTTPException(404, "Farmer not found")

    project = db.query(Project).filter(Project.id == farmer.project_id).first() if farmer.project_id else None
    enrollments = (
        db.query(FarmerProjectEnrollment)
        .filter(
            FarmerProjectEnrollment.tenant_id == x_tenant_id,
            FarmerProjectEnrollment.farmer_id == farmer.id,
            FarmerProjectEnrollment.status != "ARCHIVED",
        )
        .order_by(FarmerProjectEnrollment.updated_at.desc(), FarmerProjectEnrollment.created_at.desc())
        .all()
    )
    enrollment_project_ids = [enrollment.project_id for enrollment in enrollments]
    enrollment_projects = {
        row.id: row
        for row in db.query(Project).filter(Project.tenant_id == x_tenant_id, Project.id.in_(enrollment_project_ids)).all()
    } if enrollment_project_ids else {}
    parcels = (
        db.query(Parcel)
        .filter(Parcel.tenant_id == x_tenant_id, Parcel.farmer_id == farmer.id)
        .order_by(Parcel.created_at.asc())
        .all()
    )
    cycles = (
        db.query(CropCycle)
        .filter(CropCycle.tenant_id == x_tenant_id, CropCycle.farmer_id == farmer.id)
        .order_by(CropCycle.created_at.asc())
        .all()
    )
    activity_rows_raw = (
        db.query(CropActivity, CropCycle, CropStageInstance, Farmer, Parcel)
        .join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id)
        .outerjoin(CropStageInstance, CropStageInstance.id == CropActivity.stage_instance_id)
        .outerjoin(Farmer, Farmer.id == CropActivity.farmer_id)
        .outerjoin(Parcel, Parcel.id == CropCycle.parcel_id)
        .filter(CropActivity.tenant_id == x_tenant_id, CropCycle.farmer_id == farmer.id)
        .order_by(CropActivity.activity_date.asc(), CropActivity.created_at.asc())
        .all()
    )
    activities = [_activity_trace_row(activity, cycle, stage, row_farmer, parcel) for activity, cycle, stage, row_farmer, parcel in activity_rows_raw]

    cycles_by_parcel = defaultdict(list)
    activities_by_parcel = defaultdict(list)
    activities_by_cycle = defaultdict(list)
    total_cost_by_parcel = defaultdict(list)
    total_cost_by_cycle = defaultdict(list)
    variance_count = 0
    for cycle in cycles:
        cycles_by_parcel[cycle.parcel_id].append(cycle)
    for row in activities:
        parcel_key = uuid.UUID(row["parcel_id"]) if row.get("parcel_id") else None
        cycle_key = uuid.UUID(row["crop_cycle_id"]) if row.get("crop_cycle_id") else None
        if parcel_key:
            activities_by_parcel[parcel_key].append(row)
            total_cost_by_parcel[parcel_key].append(row.get("cost_amount"))
        if cycle_key:
            activities_by_cycle[cycle_key].append(row)
            total_cost_by_cycle[cycle_key].append(row.get("cost_amount"))
        if row.get("recommended_quantity") is not None and row.get("actual_quantity") is not None:
            if Decimal(str(row["recommended_quantity"])) != Decimal(str(row["actual_quantity"])):
                variance_count += 1

    enrollment_rows = [_farmer_enrollment_trace_row(enrollment, enrollment_projects.get(enrollment.project_id)) for enrollment in enrollments]
    enrollment_status_counts = defaultdict(int)
    lifecycle_events = []
    for row in enrollment_rows:
        enrollment_status_counts[row["status"] or "UNKNOWN"] += 1
        for event in row.get("lifecycle_events") or []:
            lifecycle_events.append({**event, "enrollment_id": row["id"], "project_id": row["project_id"], "project_name": row.get("project_name")})
    lifecycle_events.sort(key=lambda item: item.get("at") or "", reverse=True)
    active_enrollment_count = enrollment_status_counts.get("ACTIVE", 0)
    pending_enrollment_count = enrollment_status_counts.get("PENDING", 0)

    return {
        "schema_version": "farmer_trace.v1",
        "tenant_id": x_tenant_id,
        "farmer": {
            "id": str(farmer.id),
            "project_id": str(farmer.project_id) if farmer.project_id else None,
            "user_id": str(farmer.user_id) if farmer.user_id else None,
            "mobile_number": farmer.mobile_number,
            "display_name": farmer.display_name,
            "father_name": farmer.father_name,
            "village_name": farmer.village_name_manual,
            "primary_crop_code": farmer.primary_crop_code,
            "status": farmer.status,
            "created_at": farmer.created_at.isoformat() if farmer.created_at else None,
            "updated_at": farmer.updated_at.isoformat() if farmer.updated_at else None,
            "media_attachments": _media_attachments_for_entity(db, x_tenant_id, "FARMER", farmer.id),
        },
        "project": {
            "id": str(project.id),
            "name": project.name,
            "status": project.status,
        } if project else None,
        "summary": {
            "parcel_count": len(parcels),
            "crop_cycle_count": len(cycles),
            "active_cycle_count": sum(1 for cycle in cycles if cycle.status == "ACTIVE"),
            "completed_cycle_count": sum(1 for cycle in cycles if cycle.status == "COMPLETED"),
            "activity_count": len(activities),
            "total_cost": _decimal_sum([row.get("cost_amount") for row in activities]),
            "variance_count": variance_count,
        },
        "project_enrollments": enrollment_rows,
        "enrollment_lifecycle": {
            "status_counts": dict(sorted(enrollment_status_counts.items())),
            "active_count": active_enrollment_count,
            "pending_count": pending_enrollment_count,
            "active_pending_count": active_enrollment_count + pending_enrollment_count,
            "total_enrollment_count": len(enrollment_rows),
            "has_open_enrollments": (active_enrollment_count + pending_enrollment_count) > 0,
            "can_continue_independently": (active_enrollment_count + pending_enrollment_count) == 0,
            "latest_event": lifecycle_events[0] if lifecycle_events else None,
            "events": lifecycle_events[:25],
            "project_enrollments_url": f"/project-enrollments?farmerId={farmer.id}",
        },
        "parcels": [_farmer_trace_parcel_row(parcel, cycles_by_parcel, activities_by_parcel, total_cost_by_parcel) for parcel in parcels],
        "crop_cycles": [_farmer_trace_cycle_row(cycle, activities_by_cycle, total_cost_by_cycle) for cycle in cycles],
        "activities": activities[:250],
    }






def _project_trace_filter_payload(
    *,
    farmer_id,
    parcel_id,
    crop_code,
    season_code,
    stage_code,
    activity_type,
    input_code,
    product_code,
    cycle_status,
    has_variance,
    date_from,
    date_to,
    limit,
):
    return {
        "farmer_id": str(farmer_id) if farmer_id else None,
        "parcel_id": str(parcel_id) if parcel_id else None,
        "crop_code": crop_code.upper() if crop_code else None,
        "season_code": season_code.upper() if season_code else None,
        "stage_code": stage_code.upper() if stage_code else None,
        "activity_type": activity_type.upper() if activity_type else None,
        "input_code": input_code.upper() if input_code else None,
        "product_code": product_code.upper() if product_code else None,
        "cycle_status": cycle_status.upper() if cycle_status else None,
        "has_variance": has_variance,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "limit": limit,
    }


def _apply_project_cycle_filters(query, *, farmer_id, parcel_id, crop_code, season_code, cycle_status):
    if farmer_id:
        query = query.filter(CropCycle.farmer_id == farmer_id)
    if parcel_id:
        query = query.filter(CropCycle.parcel_id == parcel_id)
    if crop_code:
        query = query.filter(CropCycle.crop_code == crop_code.upper())
    if season_code:
        query = query.filter(CropCycle.season_code == season_code.upper())
    if cycle_status:
        query = query.filter(CropCycle.status == cycle_status.upper())
    return query


def _project_enrollment_lifecycle_trace(db: Session, *, tenant_id: str, project_id: uuid.UUID) -> dict:
    enrollments = (
        db.query(FarmerProjectEnrollment)
        .filter(
            FarmerProjectEnrollment.tenant_id == tenant_id,
            FarmerProjectEnrollment.project_id == project_id,
        )
        .all()
    )
    by_status = defaultdict(int)
    for enrollment in enrollments:
        by_status[enrollment.status or "UNKNOWN"] += 1

    lifecycle_events = (
        db.query(ProjectAppConfigAuditEvent)
        .filter(
            ProjectAppConfigAuditEvent.tenant_id == tenant_id,
            ProjectAppConfigAuditEvent.project_id == project_id,
            ProjectAppConfigAuditEvent.action.in_([
                "UPDATE_PROJECT_ENROLLMENT_STATUS",
                "BULK_UPDATE_PROJECT_ENROLLMENT_STATUS",
                "BULK_UPDATE_PROJECT_ENROLLMENT_STATUS_SUMMARY",
            ]),
        )
        .order_by(ProjectAppConfigAuditEvent.created_at.desc())
        .limit(10)
        .all()
    )
    active_pending_count = by_status.get("ACTIVE", 0) + by_status.get("PENDING", 0)
    return {
        "schema_version": "project_enrollment_lifecycle_trace.v1",
        "status_counts": [
            {"status": status, "count": by_status.get(status, 0)}
            for status in ["ACTIVE", "PENDING", "COMPLETED", "CANCELLED", "ARCHIVED"]
            if by_status.get(status, 0) or status in {"ACTIVE", "PENDING"}
        ],
        "active_pending_count": active_pending_count,
        "has_open_enrollments": active_pending_count > 0,
        "total_enrollment_count": len(enrollments),
        "latest_event": None if not lifecycle_events else {
            "id": str(lifecycle_events[0].id),
            "action": lifecycle_events[0].action,
            "actor_id": str(lifecycle_events[0].actor_id),
            "reason": lifecycle_events[0].reason,
            "created_at": lifecycle_events[0].created_at.isoformat() if lifecycle_events[0].created_at else None,
            "after": lifecycle_events[0].after_config or {},
        },
        "events": [
            {
                "id": str(event.id),
                "action": event.action,
                "actor_id": str(event.actor_id),
                "reason": event.reason,
                "created_at": event.created_at.isoformat() if event.created_at else None,
                "before": event.before_config or {},
                "after": event.after_config or {},
                "patch": event.config_patch or {},
            }
            for event in lifecycle_events
        ],
        "project_enrollments_url": f"/project-enrollments?projectId={project_id}",
    }


def _project_trace_activity_query(
    db: Session,
    *,
    tenant_id: str,
    project_id: uuid.UUID,
    farmer_id: Optional[uuid.UUID],
    parcel_id: Optional[uuid.UUID],
    crop_code: Optional[str],
    season_code: Optional[str],
    stage_code: Optional[str],
    activity_type: Optional[str],
    input_code: Optional[str],
    product_code: Optional[str],
    cycle_status: Optional[str],
    has_variance: Optional[bool],
    date_from: Optional[date],
    date_to: Optional[date],
):
    query = (
        db.query(CropActivity, CropCycle, CropStageInstance, Farmer, Parcel)
        .join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id)
        .outerjoin(CropStageInstance, CropStageInstance.id == CropActivity.stage_instance_id)
        .outerjoin(Farmer, Farmer.id == CropActivity.farmer_id)
        .outerjoin(Parcel, Parcel.id == CropCycle.parcel_id)
        .filter(CropActivity.tenant_id == tenant_id, CropCycle.project_id == project_id)
    )
    query = _apply_project_cycle_filters(query, farmer_id=farmer_id, parcel_id=parcel_id, crop_code=crop_code, season_code=season_code, cycle_status=cycle_status)
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
    if has_variance is True:
        query = query.filter(CropActivity.recommended_quantity.isnot(None), CropActivity.actual_quantity.isnot(None), CropActivity.recommended_quantity != CropActivity.actual_quantity)
    elif has_variance is False:
        query = query.filter((CropActivity.recommended_quantity.is_(None)) | (CropActivity.actual_quantity.is_(None)) | (CropActivity.recommended_quantity == CropActivity.actual_quantity))
    return query


@router.get("/projects/{project_id}/trace/filter-options")
def project_trace_filter_options(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    farmers = (
        db.query(Farmer)
        .filter(Farmer.tenant_id == x_tenant_id, Farmer.project_id == project.id)
        .order_by(Farmer.display_name.asc(), Farmer.mobile_number.asc())
        .all()
    )
    parcels = (
        db.query(Parcel)
        .filter(Parcel.tenant_id == x_tenant_id, Parcel.project_id == project.id)
        .order_by(Parcel.survey_number.asc(), Parcel.local_name.asc())
        .all()
    )
    cycle_rows = (
        db.query(CropCycle)
        .filter(CropCycle.tenant_id == x_tenant_id, CropCycle.project_id == project.id)
        .all()
    )
    activity_rows_raw = (
        db.query(CropActivity, CropCycle, CropStageInstance)
        .join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id)
        .outerjoin(CropStageInstance, CropStageInstance.id == CropActivity.stage_instance_id)
        .filter(CropActivity.tenant_id == x_tenant_id, CropCycle.project_id == project.id)
        .all()
    )

    stages = {}
    activity_types = set()
    inputs = {}
    products = {}
    for activity, cycle, stage in activity_rows_raw:
        if stage and stage.stage_code:
            stages[stage.stage_code] = stage.stage_name or stage.stage_code
        if activity.activity_type:
            activity_types.add(activity.activity_type)
        if activity.input_code:
            inputs[activity.input_code] = activity.input_name or activity.input_code
        if activity.product_code:
            products[activity.product_code] = activity.product_code

    return {
        "schema_version": "project_trace_filter_options.v1",
        "tenant_id": x_tenant_id,
        "project_id": str(project.id),
        "farmers": [
            {
                "id": str(farmer.id),
                "label": farmer.display_name or farmer.mobile_number or str(farmer.id),
            }
            for farmer in farmers
        ],
        "parcels": [
            {
                "id": str(parcel.id),
                "label": parcel.local_name or parcel.survey_number or str(parcel.id),
                "farmer_id": str(parcel.farmer_id),
            }
            for parcel in parcels
        ],
        "crops": sorted({cycle.crop_code for cycle in cycle_rows if cycle.crop_code}),
        "seasons": sorted({cycle.season_code for cycle in cycle_rows if cycle.season_code}),
        "cycle_statuses": sorted({cycle.status for cycle in cycle_rows if cycle.status}),
        "stages": [{"code": key, "label": value} for key, value in sorted(stages.items())],
        "activity_types": sorted(activity_types),
        "inputs": [{"code": key, "label": value} for key, value in sorted(inputs.items())],
        "products": [{"code": key, "label": value} for key, value in sorted(products.items())],
    }


@router.get("/projects/{project_id}/trace")
def project_trace_report(
    project_id: uuid.UUID,
    farmer_id: Optional[uuid.UUID] = Query(None),
    parcel_id: Optional[uuid.UUID] = Query(None),
    crop_code: Optional[str] = Query(None),
    season_code: Optional[str] = Query(None),
    stage_code: Optional[str] = Query(None),
    activity_type: Optional[str] = Query(None),
    input_code: Optional[str] = Query(None),
    product_code: Optional[str] = Query(None),
    cycle_status: Optional[str] = Query(None),
    has_variance: Optional[bool] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    farmers = (
        db.query(Farmer)
        .filter(Farmer.tenant_id == x_tenant_id, Farmer.project_id == project.id)
        .order_by(Farmer.updated_at.desc())
        .all()
    )
    parcels = (
        db.query(Parcel)
        .filter(Parcel.tenant_id == x_tenant_id, Parcel.project_id == project.id)
        .order_by(Parcel.updated_at.desc())
        .all()
    )
    cycle_query = db.query(CropCycle).filter(CropCycle.tenant_id == x_tenant_id, CropCycle.project_id == project.id)
    cycle_query = _apply_project_cycle_filters(cycle_query, farmer_id=farmer_id, parcel_id=parcel_id, crop_code=crop_code, season_code=season_code, cycle_status=cycle_status)
    cycles = cycle_query.order_by(CropCycle.updated_at.desc()).all()
    activity_rows_raw = (
        _project_trace_activity_query(
            db,
            tenant_id=x_tenant_id,
            project_id=project.id,
            farmer_id=farmer_id,
            parcel_id=parcel_id,
            crop_code=crop_code,
            season_code=season_code,
            stage_code=stage_code,
            activity_type=activity_type,
            input_code=input_code,
            product_code=product_code,
            cycle_status=cycle_status,
            has_variance=has_variance,
            date_from=date_from,
            date_to=date_to,
        )
        .order_by(CropActivity.activity_date.desc(), CropActivity.created_at.desc())
        .all()
    )
    activities = [_activity_trace_row(activity, cycle, stage, farmer, parcel) for activity, cycle, stage, farmer, parcel in activity_rows_raw]
    enrollment_lifecycle = _project_enrollment_lifecycle_trace(db, tenant_id=x_tenant_id, project_id=project.id)

    parcels_by_farmer = defaultdict(int)
    cycles_by_farmer = defaultdict(int)
    activities_by_farmer = defaultdict(int)
    activities_by_cycle = defaultdict(list)
    total_cost_by_cycle = defaultdict(list)
    crop_distribution = defaultdict(int)
    cycle_status_distribution = defaultdict(int)
    geometry_coverage = defaultdict(int)
    activity_count_by_type = defaultdict(int)
    activity_count_by_crop_stage = defaultdict(int)
    variance_count = 0

    for parcel in parcels:
        parcels_by_farmer[parcel.farmer_id] += 1
        geometry_coverage[parcel.geometry_source or "NONE"] += 1
    for cycle in cycles:
        cycles_by_farmer[cycle.farmer_id] += 1
        crop_distribution[cycle.crop_code or "UNKNOWN"] += 1
        cycle_status_distribution[cycle.status or "UNKNOWN"] += 1
    for row in activities:
        farmer_key = uuid.UUID(row["farmer_id"]) if row.get("farmer_id") else None
        cycle_key = uuid.UUID(row["crop_cycle_id"]) if row.get("crop_cycle_id") else None
        if farmer_key:
            activities_by_farmer[farmer_key] += 1
        if cycle_key:
            activities_by_cycle[cycle_key].append(row)
            total_cost_by_cycle[cycle_key].append(row.get("cost_amount"))
        activity_count_by_type[row.get("activity_type") or "UNKNOWN"] += 1
        activity_count_by_crop_stage[(row.get("crop_code") or "UNKNOWN", row.get("stage_code") or "UNSTAGED")] += 1
        if row.get("recommended_quantity") is not None and row.get("actual_quantity") is not None:
            if Decimal(str(row["recommended_quantity"])) != Decimal(str(row["actual_quantity"])):
                variance_count += 1

    return {
        "schema_version": "project_trace.v1",
        "tenant_id": x_tenant_id,
        "filters": _project_trace_filter_payload(
            farmer_id=farmer_id,
            parcel_id=parcel_id,
            crop_code=crop_code,
            season_code=season_code,
            stage_code=stage_code,
            activity_type=activity_type,
            input_code=input_code,
            product_code=product_code,
            cycle_status=cycle_status,
            has_variance=has_variance,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        ),
        "project": {
            "id": str(project.id),
            "name": project.name,
            "status": project.status,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "crop_scope": project.crop_scope or [],
        },
        "summary": {
            "farmer_count": len(farmers),
            "parcel_count": len(parcels),
            "crop_cycle_count": len(cycles),
            "active_cycle_count": sum(1 for cycle in cycles if cycle.status == "ACTIVE"),
            "completed_cycle_count": sum(1 for cycle in cycles if cycle.status == "COMPLETED"),
            "activity_count": len(activities),
            "total_cost": _decimal_sum([row.get("cost_amount") for row in activities]),
            "variance_count": variance_count,
            "geometry_captured_count": sum(1 for parcel in parcels if parcel.geometry_source and parcel.geometry_source != "NONE"),
            "geometry_missing_count": sum(1 for parcel in parcels if not parcel.geometry_source or parcel.geometry_source == "NONE"),
        },
        "crop_distribution": [
            {"crop_code": key, "crop_cycle_count": value}
            for key, value in sorted(crop_distribution.items())
        ],
        "cycle_status_distribution": [
            {"status": key, "crop_cycle_count": value}
            for key, value in sorted(cycle_status_distribution.items())
        ],
        "geometry_coverage": [
            {"geometry_source": key, "parcel_count": value}
            for key, value in sorted(geometry_coverage.items())
        ],
        "activity_count_by_type": [
            {"activity_type": key, "activity_count": value}
            for key, value in sorted(activity_count_by_type.items())
        ],
        "activity_count_by_crop_stage": [
            {"crop_code": key[0], "stage_code": key[1], "activity_count": value}
            for key, value in sorted(activity_count_by_crop_stage.items())
        ],
        "enrollment_lifecycle": enrollment_lifecycle,
        "farmers": [
            {
                "id": str(farmer.id),
                "label": farmer.display_name or farmer.mobile_number or str(farmer.id),
                "display_name": farmer.display_name,
                "mobile_number": farmer.mobile_number,
                "village_name": farmer.village_name_manual,
                "primary_crop_code": farmer.primary_crop_code,
                "status": farmer.status,
                "parcel_count": parcels_by_farmer.get(farmer.id, 0),
                "crop_cycle_count": cycles_by_farmer.get(farmer.id, 0),
                "activity_count": activities_by_farmer.get(farmer.id, 0),
                "trace_url": f"/farmer-trace/{farmer.id}",
            }
            for farmer in farmers[:limit]
        ],
        "parcels": [
            {
                "id": str(parcel.id),
                "label": parcel.local_name or parcel.survey_number or str(parcel.id),
                "survey_number": parcel.survey_number,
                "local_name": parcel.local_name,
                "farmer_id": str(parcel.farmer_id),
                "reported_area": _decimal_text(parcel.reported_area),
                "reported_area_unit": parcel.reported_area_unit,
                "ownership_type": parcel.ownership_type,
                "annual_rent": _decimal_text(parcel.annual_rent),
                "annual_rent_currency": parcel.annual_rent_currency,
                "share_percentage": parcel.share_percentage,
                "sharecrop_percentage": parcel.sharecrop_percentage,
                "village_name": parcel.village_name_manual,
                "pin_code": parcel.pin_code,
                "location_scope": parcel.location_scope or {},
                "irrigation_source": parcel.irrigation_source,
                "geometry_source": parcel.geometry_source,
                "status": parcel.status,
                "trace_url": f"/parcel-trace/{parcel.id}",
            }
            for parcel in parcels[:limit]
        ],
        "crop_cycles": [_farmer_trace_cycle_row(cycle, activities_by_cycle, total_cost_by_cycle) for cycle in cycles[:limit]],
        "activities": activities[:limit],
    }


@router.get("/projects/{project_id}/trace.csv")
def project_trace_report_csv(
    project_id: uuid.UUID,
    farmer_id: Optional[uuid.UUID] = Query(None),
    parcel_id: Optional[uuid.UUID] = Query(None),
    crop_code: Optional[str] = Query(None),
    season_code: Optional[str] = Query(None),
    stage_code: Optional[str] = Query(None),
    activity_type: Optional[str] = Query(None),
    input_code: Optional[str] = Query(None),
    product_code: Optional[str] = Query(None),
    cycle_status: Optional[str] = Query(None),
    has_variance: Optional[bool] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(5000, ge=1, le=10000),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    activity_rows_raw = (
        _project_trace_activity_query(
            db,
            tenant_id=x_tenant_id,
            project_id=project.id,
            farmer_id=farmer_id,
            parcel_id=parcel_id,
            crop_code=crop_code,
            season_code=season_code,
            stage_code=stage_code,
            activity_type=activity_type,
            input_code=input_code,
            product_code=product_code,
            cycle_status=cycle_status,
            has_variance=has_variance,
            date_from=date_from,
            date_to=date_to,
        )
        .order_by(CropActivity.activity_date.desc(), CropActivity.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = []
    for activity, cycle, stage, farmer, parcel in activity_rows_raw:
        row = _activity_trace_row(activity, cycle, stage, farmer, parcel)
        row["project_name"] = project.name
        rows.append(row)
    return _csv_stream(_rows_csv(rows, PROJECT_TRACE_CSV_COLUMNS), f"project_trace_{project.id}.csv")

@router.get("/projects/{project_id}/input-compliance")
def project_input_compliance_report(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == x_tenant_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    activity_rows_raw = (
        db.query(CropActivity, CropCycle, CropStageInstance, Farmer, Parcel)
        .join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id)
        .outerjoin(CropStageInstance, CropStageInstance.id == CropActivity.stage_instance_id)
        .outerjoin(Farmer, Farmer.id == CropActivity.farmer_id)
        .outerjoin(Parcel, Parcel.id == CropCycle.parcel_id)
        .filter(CropActivity.tenant_id == x_tenant_id, CropCycle.project_id == project.id)
        .order_by(CropActivity.activity_date.asc(), CropActivity.created_at.asc())
        .all()
    )
    activities = [_activity_trace_row(activity, cycle, stage, farmer, parcel) for activity, cycle, stage, farmer, parcel in activity_rows_raw]

    approvals = (
        db.query(ProjectProductApproval, AgriculturalProduct)
        .join(AgriculturalProduct, AgriculturalProduct.id == ProjectProductApproval.product_id)
        .filter(ProjectProductApproval.tenant_id == x_tenant_id, ProjectProductApproval.project_id == project.id)
        .all()
    )
    approved_product_codes = {product.code for approval, product in approvals if approval.enabled}
    preferred_product_codes = {product.code for approval, product in approvals if approval.enabled and approval.preferred}

    quantity_by_input = defaultdict(Decimal)
    quantity_by_product = defaultdict(Decimal)
    quantity_by_crop_stage = defaultdict(Decimal)
    activity_count_by_crop_stage = defaultdict(int)
    variance_reasons = defaultdict(int)
    total_cost_values = []
    linked_count = 0
    custom_count = 0
    product_approved_count = 0
    product_unapproved_count = 0
    product_preferred_count = 0
    product_missing_count = 0
    variance_count = 0

    for row in activities:
        total_cost_values.append(row.get("cost_amount"))
        if row.get("input_rule_id"):
            linked_count += 1
        else:
            custom_count += 1

        product_code = row.get("product_code")
        if product_code:
            if product_code in approved_product_codes:
                product_approved_count += 1
            else:
                product_unapproved_count += 1
            if product_code in preferred_product_codes:
                product_preferred_count += 1
        elif row.get("input_code"):
            product_missing_count += 1

        if row.get("recommended_quantity") is not None and row.get("actual_quantity") is not None:
            if Decimal(str(row["recommended_quantity"])) != Decimal(str(row["actual_quantity"])):
                variance_count += 1
                variance_reasons[row.get("dosage_variance_reason") or "UNSPECIFIED"] += 1

        quantity_value = row.get("actual_quantity") or row.get("quantity")
        unit = row.get("actual_quantity_unit") or row.get("quantity_unit") or "UNKNOWN"
        if quantity_value is not None:
            if row.get("input_code"):
                quantity_by_input[(row["input_code"], unit)] += Decimal(str(quantity_value))
            if row.get("product_code"):
                quantity_by_product[(row["product_code"], row.get("package_sku") or "", unit)] += Decimal(str(quantity_value))
            crop_stage_key = (row.get("crop_code") or "UNKNOWN", row.get("stage_code") or "UNSTAGED", unit)
            quantity_by_crop_stage[crop_stage_key] += Decimal(str(quantity_value))
        activity_count_by_crop_stage[(row.get("crop_code") or "UNKNOWN", row.get("stage_code") or "UNSTAGED")] += 1

    activity_count = len(activities)
    linked_rate = str((Decimal(linked_count) / Decimal(activity_count) * Decimal("100")).quantize(Decimal("0.01"))) if activity_count else "0.00"
    variance_rate = str((Decimal(variance_count) / Decimal(activity_count) * Decimal("100")).quantize(Decimal("0.01"))) if activity_count else "0.00"
    approval_rate = str((Decimal(product_approved_count) / Decimal(product_approved_count + product_unapproved_count) * Decimal("100")).quantize(Decimal("0.01"))) if (product_approved_count + product_unapproved_count) else "0.00"

    return {
        "schema_version": "project_input_compliance.v1",
        "tenant_id": x_tenant_id,
        "project": {
            "id": str(project.id),
            "name": project.name,
            "status": project.status,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "crop_scope": project.crop_scope or [],
        },
        "summary": {
            "activity_count": activity_count,
            "total_cost": _decimal_sum(total_cost_values),
            "recommendation_linked_count": linked_count,
            "custom_activity_count": custom_count,
            "recommendation_linked_rate_percent": linked_rate,
            "variance_count": variance_count,
            "variance_rate_percent": variance_rate,
            "product_approved_count": product_approved_count,
            "product_unapproved_count": product_unapproved_count,
            "product_preferred_count": product_preferred_count,
            "product_missing_count": product_missing_count,
            "product_approval_rate_percent": approval_rate,
        },
        "quantity_by_input": [
            {"input_code": key[0], "unit": key[1], "quantity": str(value)}
            for key, value in sorted(quantity_by_input.items())
        ],
        "quantity_by_product": [
            {"product_code": key[0], "package_sku": key[1] or None, "unit": key[2], "quantity": str(value)}
            for key, value in sorted(quantity_by_product.items())
        ],
        "quantity_by_crop_stage": [
            {"crop_code": key[0], "stage_code": key[1], "unit": key[2], "quantity": str(value)}
            for key, value in sorted(quantity_by_crop_stage.items())
        ],
        "activity_count_by_crop_stage": [
            {"crop_code": key[0], "stage_code": key[1], "activity_count": value}
            for key, value in sorted(activity_count_by_crop_stage.items())
        ],
        "top_variance_reasons": [
            {"reason": key, "count": value}
            for key, value in sorted(variance_reasons.items(), key=lambda item: (-item[1], item[0]))[:10]
        ],
        "activities": activities[:250],
    }

@router.get("/products/{product_code}/trace")
def product_trace_report(
    product_code: str,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    product = db.query(AgriculturalProduct).filter(AgriculturalProduct.code == product_code).first()
    if not product:
        raise HTTPException(404, "Product not found")

    agri_input = db.query(AgriculturalInput).filter(AgriculturalInput.id == product.canonical_input_id).first()
    category = db.query(InputCategory).filter(InputCategory.id == agri_input.category_id).first() if agri_input else None
    manufacturer = db.query(Manufacturer).filter(Manufacturer.id == product.manufacturer_id).first()
    packages = (
        db.query(AgriculturalProductPackage)
        .filter(AgriculturalProductPackage.product_id == product.id)
        .order_by(AgriculturalProductPackage.sku.asc())
        .all()
    )
    approvals = (
        db.query(ProjectProductApproval, Project)
        .outerjoin(Project, Project.id == ProjectProductApproval.project_id)
        .filter(ProjectProductApproval.tenant_id == x_tenant_id, ProjectProductApproval.product_id == product.id)
        .order_by(ProjectProductApproval.display_order.asc())
        .all()
    )

    candidate_rules = (
        db.query(CropStageInputRule, Project)
        .outerjoin(Project, Project.id == CropStageInputRule.project_id)
        .filter(CropStageInputRule.tenant_id == x_tenant_id, CropStageInputRule.input_id == product.canonical_input_id)
        .order_by(CropStageInputRule.crop_code.asc(), CropStageInputRule.stage_code.asc(), CropStageInputRule.priority.asc())
        .all()
    )
    rule_rows = []
    for rule, project in candidate_rules:
        allowed_codes = rule.allowed_product_codes or []
        if allowed_codes and product.code not in allowed_codes:
            continue
        rule_rows.append({
            "id": str(rule.id),
            "project_id": str(rule.project_id) if rule.project_id else None,
            "project_name": project.name if project else None,
            "crop_code": rule.crop_code,
            "season_code": rule.season_code,
            "stage_code": rule.stage_code,
            "activity_type": rule.activity_type,
            "input_code": rule.input_code,
            "enabled": rule.enabled,
            "priority": rule.priority,
            "dosage_quantity": _decimal_text(rule.dosage_quantity),
            "dosage_unit": rule.dosage_unit,
            "dosage_area_unit": rule.dosage_area_unit,
            "allowed_product_codes": allowed_codes,
        })

    activity_rows_raw = (
        db.query(CropActivity, CropCycle, CropStageInstance, Farmer, Parcel)
        .join(CropCycle, CropCycle.id == CropActivity.crop_cycle_id)
        .outerjoin(CropStageInstance, CropStageInstance.id == CropActivity.stage_instance_id)
        .outerjoin(Farmer, Farmer.id == CropActivity.farmer_id)
        .outerjoin(Parcel, Parcel.id == CropCycle.parcel_id)
        .filter(CropActivity.tenant_id == x_tenant_id, CropActivity.product_code == product.code)
        .order_by(CropActivity.activity_date.asc(), CropActivity.created_at.asc())
        .all()
    )
    activities = [_activity_trace_row(activity, cycle, stage, farmer, parcel) for activity, cycle, stage, farmer, parcel in activity_rows_raw]

    quantity_by_package = defaultdict(Decimal)
    quantity_by_crop = defaultdict(Decimal)
    quantity_by_stage = defaultdict(Decimal)
    quantity_by_project = defaultdict(Decimal)
    package_activity_count = defaultdict(int)
    for row in activities:
        quantity_value = row.get("actual_quantity") or row.get("quantity")
        unit = row.get("actual_quantity_unit") or row.get("quantity_unit") or "UNKNOWN"
        if quantity_value is not None:
            if row.get("package_sku"):
                quantity_by_package[(row["package_sku"], unit)] += Decimal(str(quantity_value))
            if row.get("crop_code"):
                quantity_by_crop[(row["crop_code"], unit)] += Decimal(str(quantity_value))
            if row.get("stage_code"):
                quantity_by_stage[(row["stage_code"], unit)] += Decimal(str(quantity_value))
            project_key = row.get("project_id") or "NO_PROJECT"
            quantity_by_project[(project_key, unit)] += Decimal(str(quantity_value))
        if row.get("package_sku"):
            package_activity_count[row["package_sku"]] += 1

    return {
        "schema_version": "product_trace.v1",
        "tenant_id": x_tenant_id,
        "product": {
            "id": str(product.id),
            "code": product.code,
            "canonical_input_id": str(product.canonical_input_id),
            "manufacturer_id": str(product.manufacturer_id),
            "brand_name": product.brand_name,
            "composition": product.composition,
            "registration_number": product.registration_number,
            "registration_authority": product.registration_authority,
            "registration_expiry_date": product.registration_expiry_date.isoformat() if product.registration_expiry_date else None,
            "country": product.country,
            "status": product.status,
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
        },
        "manufacturer": {
            "id": str(manufacturer.id),
            "code": manufacturer.code,
            "canonical_name": manufacturer.canonical_name,
            "short_name": manufacturer.short_name,
            "country": manufacturer.country,
        } if manufacturer else None,
        "input": {
            "id": str(agri_input.id),
            "code": agri_input.code,
            "canonical_name": agri_input.canonical_name,
            "category_code": category.code if category else None,
            "category_name": category.canonical_name if category else None,
            "composition": agri_input.composition,
            "unit": agri_input.unit,
            "catalog_status": agri_input.catalog_status,
        } if agri_input else None,
        "packages": [
            {
                "id": str(package.id),
                "sku": package.sku,
                "quantity": _decimal_text(package.quantity),
                "unit": package.unit,
                "pack_label": package.pack_label,
                "barcode": package.barcode,
                "status": package.status,
                "activity_count": package_activity_count.get(package.sku, 0),
            }
            for package in packages
        ],
        "project_approvals": [
            {
                "id": str(approval.id),
                "project_id": str(approval.project_id),
                "project_name": project.name if project else None,
                "enabled": approval.enabled,
                "preferred": approval.preferred,
                "display_order": approval.display_order,
                "reason": approval.reason,
            }
            for approval, project in approvals
        ],
        "input_rules": rule_rows,
        "summary": {
            "activity_count": len(activities),
            "total_cost": _decimal_sum([row.get("cost_amount") for row in activities]),
            "variance_count": sum(1 for row in activities if row.get("recommended_quantity") is not None and row.get("actual_quantity") is not None and Decimal(str(row["recommended_quantity"])) != Decimal(str(row["actual_quantity"]))),
            "quantity_by_package": [{"package_sku": key[0], "unit": key[1], "quantity": str(value)} for key, value in sorted(quantity_by_package.items())],
            "quantity_by_crop": [{"crop_code": key[0], "unit": key[1], "quantity": str(value)} for key, value in sorted(quantity_by_crop.items())],
            "quantity_by_stage": [{"stage_code": key[0], "unit": key[1], "quantity": str(value)} for key, value in sorted(quantity_by_stage.items())],
            "quantity_by_project": [{"project_id": key[0], "unit": key[1], "quantity": str(value)} for key, value in sorted(quantity_by_project.items())],
        },
        "activities": activities,
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
    activity_rows = [
        _activity_trace_row(
            activity,
            cycle,
            stage_by_id.get(activity.stage_instance_id),
            farmer,
            parcel,
            _media_attachment_count(db, x_tenant_id, "CROP_ACTIVITY", activity.id),
        )
        for activity in activities
    ]
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
            "media_attachments": _media_attachments_for_entity(db, x_tenant_id, "CROP_CYCLE", cycle.id),
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
        "media_attachments": {
            "crop_cycle": _media_attachments_for_entity(db, x_tenant_id, "CROP_CYCLE", cycle.id),
            "farmer": _media_attachments_for_entity(db, x_tenant_id, "FARMER", cycle.farmer_id),
            "parcel": _media_attachments_for_entity(db, x_tenant_id, "PARCEL", cycle.parcel_id),
        },
    }


def _safe_uuid(value: Optional[str]):
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@router.get("/lookup")
def admin_lookup_report(
    q: Optional[str] = Query(None, description="Search projects, farmers, and parcels by name, mobile, survey number, or ID"),
    project_id: Optional[uuid.UUID] = Query(None),
    geometry_status: Optional[str] = Query(None, description="Parcel geometry status: CAPTURED or MISSING"),
    geometry_source: Optional[str] = Query(None, description="Parcel geometry source such as PIN_DROP, GPS_WALK, or NONE"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    term = (q or "").strip()
    geometry_status_value = geometry_status.upper() if geometry_status else None
    geometry_source_value = geometry_source.upper() if geometry_source else None
    like = f"%{term}%" if term else None
    uuid_value = _safe_uuid(term)

    project_query = db.query(Project).filter(Project.tenant_id == x_tenant_id)
    farmer_query = db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id)
    parcel_query = db.query(Parcel).filter(Parcel.tenant_id == x_tenant_id)
    if project_id:
        project_query = project_query.filter(Project.id == project_id)
        farmer_query = farmer_query.filter(Farmer.project_id == project_id)
        parcel_query = parcel_query.filter(Parcel.project_id == project_id)
    # SQLAlchemy boolean OR is kept inline to avoid expanding imports in this legacy report module.
    if term:
        project_condition = Project.name.ilike(like) | Project.status.ilike(like)
        farmer_condition = Farmer.display_name.ilike(like) | Farmer.mobile_number.ilike(like) | Farmer.village_name_manual.ilike(like) | Farmer.primary_crop_code.ilike(like)
        parcel_condition = Parcel.survey_number.ilike(like) | Parcel.local_name.ilike(like) | Parcel.village_name_manual.ilike(like) | Parcel.ownership_type.ilike(like)
        if uuid_value:
            project_condition = project_condition | (Project.id == uuid_value)
            farmer_condition = farmer_condition | (Farmer.id == uuid_value)
            parcel_condition = parcel_condition | (Parcel.id == uuid_value) | (Parcel.farmer_id == uuid_value)
        project_query = db.query(Project).filter(Project.tenant_id == x_tenant_id, project_condition)
        farmer_query = db.query(Farmer).filter(Farmer.tenant_id == x_tenant_id, farmer_condition)
        parcel_query = db.query(Parcel).filter(Parcel.tenant_id == x_tenant_id, parcel_condition)
        if project_id:
            project_query = project_query.filter(Project.id == project_id)
            farmer_query = farmer_query.filter(Farmer.project_id == project_id)
            parcel_query = parcel_query.filter(Parcel.project_id == project_id)

    if geometry_status_value == "MISSING":
        parcel_query = parcel_query.filter((Parcel.geometry_source.is_(None)) | (Parcel.geometry_source == "NONE"))
    elif geometry_status_value == "CAPTURED":
        parcel_query = parcel_query.filter(Parcel.geometry_source.isnot(None), Parcel.geometry_source != "NONE")
    elif geometry_status_value:
        raise HTTPException(400, "geometry_status must be CAPTURED or MISSING")

    if geometry_source_value:
        if geometry_source_value in {"MISSING", "NONE"}:
            parcel_query = parcel_query.filter((Parcel.geometry_source.is_(None)) | (Parcel.geometry_source == "NONE"))
        else:
            parcel_query = parcel_query.filter(Parcel.geometry_source == geometry_source_value)

    projects = project_query.order_by(Project.updated_at.desc()).limit(limit).all()
    farmers = farmer_query.order_by(Farmer.updated_at.desc()).limit(limit).all()
    parcels = parcel_query.order_by(Parcel.updated_at.desc()).limit(limit).all()

    project_ids = [project.id for project in projects]
    farmer_ids = [farmer.id for farmer in farmers]
    parcel_ids = [parcel.id for parcel in parcels]
    farmers_by_id = {farmer.id: farmer for farmer in db.query(Farmer).filter(Farmer.id.in_([parcel.farmer_id for parcel in parcels])).all()} if parcels else {}
    cycle_count_by_project = defaultdict(int)
    cycle_count_by_farmer = defaultdict(int)
    cycle_count_by_parcel = defaultdict(int)
    activity_count_by_farmer = defaultdict(int)
    activity_count_by_parcel = defaultdict(int)

    if project_ids:
        for cycle in db.query(CropCycle).filter(CropCycle.tenant_id == x_tenant_id, CropCycle.project_id.in_(project_ids)).all():
            cycle_count_by_project[cycle.project_id] += 1
    if farmer_ids:
        for cycle in db.query(CropCycle).filter(CropCycle.tenant_id == x_tenant_id, CropCycle.farmer_id.in_(farmer_ids)).all():
            cycle_count_by_farmer[cycle.farmer_id] += 1
        for activity in db.query(CropActivity).filter(CropActivity.tenant_id == x_tenant_id, CropActivity.farmer_id.in_(farmer_ids)).all():
            activity_count_by_farmer[activity.farmer_id] += 1
    if parcel_ids:
        for cycle in db.query(CropCycle).filter(CropCycle.tenant_id == x_tenant_id, CropCycle.parcel_id.in_(parcel_ids)).all():
            cycle_count_by_parcel[cycle.parcel_id] += 1
        parcel_cycle_ids = [cycle.id for cycle in db.query(CropCycle.id).filter(CropCycle.tenant_id == x_tenant_id, CropCycle.parcel_id.in_(parcel_ids)).all()]
        if parcel_cycle_ids:
            cycles_by_id = {cycle.id: cycle for cycle in db.query(CropCycle).filter(CropCycle.id.in_(parcel_cycle_ids)).all()}
            for activity in db.query(CropActivity).filter(CropActivity.tenant_id == x_tenant_id, CropActivity.crop_cycle_id.in_(parcel_cycle_ids)).all():
                cycle = cycles_by_id.get(activity.crop_cycle_id)
                if cycle:
                    activity_count_by_parcel[cycle.parcel_id] += 1

    return {
        "schema_version": "admin_lookup.v1",
        "tenant_id": x_tenant_id,
        "query": term,
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "geometry_status": geometry_status_value,
            "geometry_source": geometry_source_value,
        },
        "limit": limit,
        "projects": [
            {
                "id": str(project.id),
                "label": project.name,
                "name": project.name,
                "status": project.status,
                "crop_scope": project.crop_scope or [],
                "start_date": project.start_date.isoformat() if project.start_date else None,
                "end_date": project.end_date.isoformat() if project.end_date else None,
                "crop_cycle_count": cycle_count_by_project.get(project.id, 0),
                "trace_url": f"/project-trace/{project.id}",
                "compliance_url": f"/project-compliance/{project.id}",
            }
            for project in projects
        ],
        "farmers": [
            {
                "id": str(farmer.id),
                "label": farmer.display_name or farmer.mobile_number or str(farmer.id),
                "display_name": farmer.display_name,
                "mobile_number": farmer.mobile_number,
                "village_name": farmer.village_name_manual,
                "primary_crop_code": farmer.primary_crop_code,
                "project_id": str(farmer.project_id) if farmer.project_id else None,
                "status": farmer.status,
                "crop_cycle_count": cycle_count_by_farmer.get(farmer.id, 0),
                "activity_count": activity_count_by_farmer.get(farmer.id, 0),
                "trace_url": f"/farmer-trace/{farmer.id}",
            }
            for farmer in farmers
        ],
        "parcels": [
            {
                "id": str(parcel.id),
                "label": parcel.local_name or parcel.survey_number or str(parcel.id),
                "survey_number": parcel.survey_number,
                "local_name": parcel.local_name,
                "farmer_id": str(parcel.farmer_id),
                "farmer_name": farmers_by_id.get(parcel.farmer_id).display_name if farmers_by_id.get(parcel.farmer_id) else None,
                "project_id": str(parcel.project_id) if parcel.project_id else None,
                "reported_area": _decimal_text(parcel.reported_area),
                "reported_area_unit": parcel.reported_area_unit,
                "ownership_type": parcel.ownership_type,
                "annual_rent": _decimal_text(parcel.annual_rent),
                "annual_rent_currency": parcel.annual_rent_currency,
                "share_percentage": parcel.share_percentage,
                "sharecrop_percentage": parcel.sharecrop_percentage,
                "village_name": parcel.village_name_manual,
                "pin_code": parcel.pin_code,
                "location_scope": parcel.location_scope or {},
                "irrigation_source": parcel.irrigation_source,
                "geometry_source": parcel.geometry_source,
                "status": parcel.status,
                "crop_cycle_count": cycle_count_by_parcel.get(parcel.id, 0),
                "activity_count": activity_count_by_parcel.get(parcel.id, 0),
                "trace_url": f"/parcel-trace/{parcel.id}",
            }
            for parcel in parcels
        ],
    }



@router.get("/lookup.csv")
def admin_lookup_report_csv(
    q: Optional[str] = Query(None, description="Search projects, farmers, and parcels by name, mobile, survey number, or ID"),
    project_id: Optional[uuid.UUID] = Query(None),
    geometry_status: Optional[str] = Query(None),
    geometry_source: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header("default", alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.VIEW)),
):
    payload = admin_lookup_report(q=q, project_id=project_id, geometry_status=geometry_status, geometry_source=geometry_source, limit=limit, db=db, x_tenant_id=x_tenant_id, principal=principal)
    rows = []
    for project in payload["projects"]:
        rows.append({
            "entity_type": "PROJECT",
            "id": project.get("id"),
            "label": project.get("label"),
            "project_id": project.get("id"),
            "status": project.get("status"),
            "crop_scope": ",".join(project.get("crop_scope") or []),
            "crop_cycle_count": project.get("crop_cycle_count"),
            "trace_url": project.get("trace_url"),
            "compliance_url": project.get("compliance_url"),
        })
    for farmer in payload["farmers"]:
        rows.append({
            "entity_type": "FARMER",
            "id": farmer.get("id"),
            "label": farmer.get("label"),
            "project_id": farmer.get("project_id"),
            "farmer_id": farmer.get("id"),
            "status": farmer.get("status"),
            "village": farmer.get("village_name"),
            "crop": farmer.get("primary_crop_code"),
            "mobile_number": farmer.get("mobile_number"),
            "crop_cycle_count": farmer.get("crop_cycle_count"),
            "activity_count": farmer.get("activity_count"),
            "trace_url": farmer.get("trace_url"),
        })
    for parcel in payload["parcels"]:
        rows.append({
            "entity_type": "PARCEL",
            "id": parcel.get("id"),
            "label": parcel.get("label"),
            "project_id": parcel.get("project_id"),
            "farmer_id": parcel.get("farmer_id"),
            "status": parcel.get("status"),
            "village": parcel.get("village_name"),
            "survey_number": parcel.get("survey_number"),
            "area": " ".join(str(value) for value in [parcel.get("reported_area"), parcel.get("reported_area_unit")] if value),
            "ownership_type": parcel.get("ownership_type"),
            "geometry_source": parcel.get("geometry_source"),
            "crop_cycle_count": parcel.get("crop_cycle_count"),
            "activity_count": parcel.get("activity_count"),
            "trace_url": parcel.get("trace_url"),
        })
    has_filters = bool((q or "").strip() or project_id or geometry_status or geometry_source)
    filename = "admin_lookup.csv" if not has_filters else "admin_lookup_search.csv"
    return _csv_stream(_rows_csv(rows, LOOKUP_CSV_COLUMNS), filename)

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
