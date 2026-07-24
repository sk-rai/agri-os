"""Backend-owned stage cost and P&L summaries.

P&L formula is intentionally fixed:

    profit_or_loss = total_income - total_expenses

Admin configuration controls category mappings, visibility, labels, ordering,
and thresholds. It does not execute arbitrary formulas.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.farmer.models import Parcel
from app.modules.media.models import FieldEventReport
from app.modules.master_data.models import CropLifecycleTemplate
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance
from app.modules.workflow.template_service import (
    find_published_workflow_template,
    workflow_version_to_stage_definitions_for_scope,
)


MONEY = Decimal("0.01")

ALLOWED_INCOME_CATEGORIES = {
    "HARVEST_SALE",
    "CROP_INSURANCE_PAYOUT",
    "GOVERNMENT_INCENTIVE",
    "OTHER_INCOME",
}

ALLOWED_EXPENSE_CATEGORIES = {
    "SEED",
    "FERTILIZER",
    "PESTICIDE",
    "IRRIGATION",
    "LABOR",
    "MACHINERY",
    "TRANSPORT",
    "RENT",
    "OTHER_EXPENSE",
}

ALLOWED_CONTEXT_EVENT_CATEGORIES = {
    "RAIN",
    "PEST",
    "DISEASE",
    "HAILSTORM",
    "LOCUST",
    "FLOOD",
    "DROUGHT_STRESS",
    "THUNDERSTORM_WIND",
    "HEAT_STRESS",
    "COLD_STRESS",
    "IRRIGATION_FAILURE",
    "OTHER",
}

DEFAULT_FINANCE_REPORT_CONFIG = {
    "schema_version": "farmer_finance_report_config.v1",
    "status": "PUBLISHED_DEFAULT",
    "currency": "INR",
    "fixed_formula": "profit_or_loss = total_income - total_expenses",
    "income_categories": [
        "HARVEST_SALE",
        "CROP_INSURANCE_PAYOUT",
        "GOVERNMENT_INCENTIVE",
        "OTHER_INCOME",
    ],
    "expense_categories": [
        "SEED",
        "FERTILIZER",
        "PESTICIDE",
        "IRRIGATION",
        "LABOR",
        "MACHINERY",
        "TRANSPORT",
        "RENT",
        "OTHER_EXPENSE",
    ],
    "context_event_categories": [
        "RAIN",
        "PEST",
        "DISEASE",
        "HAILSTORM",
        "LOCUST",
        "FLOOD",
        "DROUGHT_STRESS",
        "THUNDERSTORM_WIND",
        "HEAT_STRESS",
        "COLD_STRESS",
        "IRRIGATION_FAILURE",
        "OTHER",
    ],
    "activity_expense_mapping": {
        "SEED": "SEED",
        "FERTILIZER": "FERTILIZER",
        "PESTICIDE": "PESTICIDE",
        "IRRIGATION": "IRRIGATION",
        "LABOR": "LABOR",
        "MACHINERY": "MACHINERY",
        "HARVEST": "LABOR",
        "OTHER": "OTHER_EXPENSE",
    },
    "display": {
        "show_planned_cost": True,
        "show_variance": True,
        "show_activity_breakup": True,
        "show_activity_rows": True,
        "show_context_events": True,
        "show_per_acre_values": True,
        "show_income_breakup": True,
        "show_expense_breakup": True,
    },
    "thresholds": {
        "cost_variance_warning_percent": 20,
    },
}


def money(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def money_text(value: Any) -> str:
    return str(money(value))


def decimal_value(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def validate_finance_report_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or DEFAULT_FINANCE_REPORT_CONFIG
    errors = []
    warnings = []

    income = set(config.get("income_categories") or [])
    expenses = set(config.get("expense_categories") or [])
    context = set(config.get("context_event_categories") or [])
    mapping = config.get("activity_expense_mapping") or {}
    display = config.get("display") or {}
    thresholds = config.get("thresholds") or {}

    if not income:
        errors.append("At least one income category is required.")
    if not expenses:
        errors.append("At least one expense category is required.")

    unknown_income = sorted(income - ALLOWED_INCOME_CATEGORIES)
    unknown_expenses = sorted(expenses - ALLOWED_EXPENSE_CATEGORIES)
    unknown_context = sorted(context - ALLOWED_CONTEXT_EVENT_CATEGORIES)
    overlap = sorted(income & expenses)

    if unknown_income:
        errors.append(f"Unknown income categories: {unknown_income}")
    if unknown_expenses:
        errors.append(f"Unknown expense categories: {unknown_expenses}")
    if unknown_context:
        errors.append(f"Unknown context event categories: {unknown_context}")
    if overlap:
        errors.append(f"Categories cannot be both income and expense: {overlap}")

    for activity_type, category in mapping.items():
        if category not in expenses:
            errors.append(f"Activity {activity_type} maps to non-expense category {category}")

    for key, value in display.items():
        if not isinstance(value, bool):
            errors.append(f"Display flag {key} must be boolean")

    variance = thresholds.get("cost_variance_warning_percent")
    if variance is not None:
        try:
            variance_number = Decimal(str(variance))
            if variance_number < 0 or variance_number > 500:
                errors.append("cost_variance_warning_percent must be between 0 and 500")
        except InvalidOperation:
            errors.append("cost_variance_warning_percent must be numeric")
    else:
        warnings.append("No cost variance warning threshold configured.")

    return {
        "schema_version": "farmer_finance_report_config_validation.v1",
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "fixed_formula": "profit_or_loss = total_income - total_expenses",
        "allowed_income_categories": sorted(ALLOWED_INCOME_CATEGORIES),
        "allowed_expense_categories": sorted(ALLOWED_EXPENSE_CATEGORIES),
        "allowed_context_event_categories": sorted(ALLOWED_CONTEXT_EVENT_CATEGORIES),
    }


def _load_cycle(db: Session, tenant_id: str, cycle_id: uuid.UUID) -> CropCycle:
    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.id == cycle_id, CropCycle.tenant_id == tenant_id)
        .first()
    )
    if not cycle:
        raise HTTPException(404, "Crop cycle not found")
    return cycle


def _template_stage_defs(db: Session, cycle: CropCycle) -> list[dict[str, Any]]:
    if cycle.workflow_template_version_id:
        return workflow_version_to_stage_definitions_for_scope(
            db,
            cycle.workflow_template_version_id,
            tenant_id=cycle.tenant_id,
            project_id=cycle.project_id,
            crop_code=cycle.crop_code,
            season_code=cycle.season_code,
        ) or []

    workflow_pair = find_published_workflow_template(
        db,
        crop_code=cycle.crop_code,
        season_code=cycle.season_code,
        tenant_id=cycle.tenant_id,
        lifecycle_template_id=cycle.lifecycle_template_id,
    )
    if workflow_pair:
        _, workflow_version = workflow_pair
        return workflow_version_to_stage_definitions_for_scope(
            db,
            workflow_version.id,
            tenant_id=cycle.tenant_id,
            project_id=cycle.project_id,
            crop_code=cycle.crop_code,
            season_code=cycle.season_code,
        ) or []

    template = (
        db.query(CropLifecycleTemplate)
        .filter(CropLifecycleTemplate.id == cycle.lifecycle_template_id)
        .first()
    )
    return (template.stages if template else []) or []


def _planned_cost_by_stage(db: Session, cycle: CropCycle) -> tuple[dict[str, Decimal], dict[str, list[dict[str, Any]]]]:
    planned_by_stage = defaultdict(lambda: Decimal("0.00"))
    planned_rows = defaultdict(list)

    for stage in _template_stage_defs(db, cycle):
        stage_code = stage.get("code") or stage.get("stage_code")
        for rec in stage.get("recommended_activities", []) or []:
            cost = money(rec.get("typical_cost_per_acre"))
            planned_by_stage[stage_code] += cost
            planned_rows[stage_code].append({
                "activity_type": rec.get("activity_type") or "OTHER",
                "input_code": rec.get("input_code"),
                "input_name": rec.get("input_name"),
                "typical_quantity": rec.get("typical_quantity"),
                "planned_cost_per_acre": money_text(cost),
            })

    return planned_by_stage, planned_rows


def _activity_row(activity: CropActivity, expense_category: str, currency: str) -> dict[str, Any]:
    return {
        "activity_id": str(activity.id),
        "activity_date": activity.activity_date.isoformat() if activity.activity_date else None,
        "activity_type": activity.activity_type,
        "expense_category": expense_category,
        "input_code": activity.input_code,
        "input_name": activity.input_name,
        "quantity": str(activity.quantity) if activity.quantity is not None else None,
        "quantity_unit": activity.quantity_unit,
        "area_applied": str(activity.area_applied) if activity.area_applied is not None else None,
        "area_unit": activity.area_unit,
        "cost_amount": money_text(activity.cost_amount),
        "cost_currency": activity.cost_currency or currency,
        "notes": activity.notes,
    }


def _context_event_row(event: FieldEventReport) -> dict[str, Any]:
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "severity": event.severity,
        "stage_code": event.stage_code,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "status": event.status,
        "description": event.description,
        "estimated_area_affected": event.estimated_area_affected,
        "estimated_loss_percent": event.estimated_loss_percent,
        "source": event.source,
    }


def build_stage_cost_summary(
    db: Session,
    *,
    tenant_id: str,
    cycle_id: uuid.UUID,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or DEFAULT_FINANCE_REPORT_CONFIG
    validation = validate_finance_report_config(config)
    if not validation["valid"]:
        raise HTTPException(409, {"error": "FINANCE_REPORT_CONFIG_INVALID", "validation": validation})

    cycle = _load_cycle(db, tenant_id, cycle_id)
    currency = config.get("currency") or "INR"
    activity_mapping = config.get("activity_expense_mapping") or {}

    stages = (
        db.query(CropStageInstance)
        .filter(CropStageInstance.crop_cycle_id == cycle.id, CropStageInstance.tenant_id == tenant_id)
        .order_by(CropStageInstance.stage_order)
        .all()
    )
    activities = (
        db.query(CropActivity)
        .filter(CropActivity.crop_cycle_id == cycle.id, CropActivity.tenant_id == tenant_id)
        .order_by(CropActivity.activity_date.asc(), CropActivity.created_at.asc())
        .all()
    )
    field_events = (
        db.query(FieldEventReport)
        .filter(FieldEventReport.crop_cycle_id == cycle.id, FieldEventReport.tenant_id == tenant_id)
        .order_by(FieldEventReport.event_date.asc(), FieldEventReport.created_at.asc())
        .all()
    )

    planned_by_stage, planned_rows = _planned_cost_by_stage(db, cycle)

    activities_by_stage = defaultdict(list)
    actual_by_stage = defaultdict(lambda: Decimal("0.00"))
    type_breakup_by_stage = defaultdict(lambda: defaultdict(lambda: Decimal("0.00")))
    input_breakup_by_stage = defaultdict(lambda: defaultdict(lambda: Decimal("0.00")))
    expense_breakup_by_stage = defaultdict(lambda: defaultdict(lambda: Decimal("0.00")))

    unassigned_key = "UNASSIGNED"

    for activity in activities:
        stage_key = activity.stage_instance_id or unassigned_key
        expense_category = activity_mapping.get((activity.activity_type or "OTHER").upper(), "OTHER_EXPENSE")
        cost = money(activity.cost_amount)

        actual_by_stage[stage_key] += cost
        type_breakup_by_stage[stage_key][activity.activity_type or "OTHER"] += cost
        expense_breakup_by_stage[stage_key][expense_category] += cost
        input_label = activity.input_name or activity.input_code or activity.activity_type or "Activity"
        input_breakup_by_stage[stage_key][input_label] += cost
        activities_by_stage[stage_key].append(_activity_row(activity, expense_category, currency))

    context_events_by_stage = defaultdict(list)
    context_event_categories = set(config.get("context_event_categories") or [])
    for event in field_events:
        if event.event_type not in context_event_categories:
            continue
        context_events_by_stage[event.stage_code or unassigned_key].append(_context_event_row(event))

    total_planned = Decimal("0.00")
    total_actual = Decimal("0.00")
    summaries = []

    for stage in stages:
        planned = planned_by_stage[stage.stage_code]
        actual = actual_by_stage[stage.id]
        total_planned += planned
        total_actual += actual

        summaries.append({
            "stage_id": str(stage.id),
            "stage_code": stage.stage_code,
            "stage_name": stage.stage_name,
            "stage_order": stage.stage_order,
            "status": stage.status,
            "planned_expense": money_text(planned),
            "actual_expense": money_text(actual),
            "variance_amount": money_text(actual - planned),
            "activity_count": len(activities_by_stage[stage.id]),
            "planned_recommendations": planned_rows[stage.stage_code],
            "expense_breakup_by_category": [
                {"expense_category": key, "amount": money_text(value)}
                for key, value in sorted(expense_breakup_by_stage[stage.id].items())
            ],
            "expense_breakup_by_activity_type": [
                {"activity_type": key, "amount": money_text(value)}
                for key, value in sorted(type_breakup_by_stage[stage.id].items())
            ],
            "expense_breakup_by_input": [
                {"input_name": key, "amount": money_text(value)}
                for key, value in sorted(input_breakup_by_stage[stage.id].items())
            ],
            "activities": activities_by_stage[stage.id],
            "context_events": context_events_by_stage[stage.stage_code],
        })

    if activities_by_stage[unassigned_key] or context_events_by_stage[unassigned_key]:
        actual = actual_by_stage[unassigned_key]
        total_actual += actual
        summaries.append({
            "stage_id": None,
            "stage_code": "UNASSIGNED",
            "stage_name": "Unassigned activities/events",
            "stage_order": None,
            "status": "UNASSIGNED",
            "planned_expense": "0.00",
            "actual_expense": money_text(actual),
            "variance_amount": money_text(actual),
            "activity_count": len(activities_by_stage[unassigned_key]),
            "planned_recommendations": [],
            "expense_breakup_by_category": [
                {"expense_category": key, "amount": money_text(value)}
                for key, value in sorted(expense_breakup_by_stage[unassigned_key].items())
            ],
            "expense_breakup_by_activity_type": [
                {"activity_type": key, "amount": money_text(value)}
                for key, value in sorted(type_breakup_by_stage[unassigned_key].items())
            ],
            "expense_breakup_by_input": [
                {"input_name": key, "amount": money_text(value)}
                for key, value in sorted(input_breakup_by_stage[unassigned_key].items())
            ],
            "activities": activities_by_stage[unassigned_key],
            "context_events": context_events_by_stage[unassigned_key],
        })

    return {
        "schema_version": "crop_cycle_stage_cost_summary.v1",
        "cycle_id": str(cycle.id),
        "tenant_id": tenant_id,
        "farmer_id": str(cycle.farmer_id),
        "parcel_id": str(cycle.parcel_id),
        "crop_code": cycle.crop_code,
        "season_code": cycle.season_code,
        "currency": currency,
        "report_config": {
            "schema_version": config.get("schema_version"),
            "status": config.get("status"),
            "display": config.get("display"),
            "validation": validation,
        },
        "totals": {
            "planned_expense": money_text(total_planned),
            "actual_expense": money_text(total_actual),
            "variance_amount": money_text(total_actual - total_planned),
            "stage_count": len(summaries),
            "activity_count": len(activities),
            "context_event_count": sum(len(v) for v in context_events_by_stage.values()),
        },
        "stage_summaries": summaries,
    }


def _area_acres(parcel: Parcel | None) -> tuple[Decimal, str | None]:
    if not parcel:
        return Decimal("0"), None
    unit = (parcel.reported_area_unit or "").upper()
    if parcel.reported_area is not None and unit == "ACRE":
        return decimal_value(parcel.reported_area), "PARCEL_REPORTED_ACRE"
    if parcel.computed_area_hectares is not None:
        return decimal_value(parcel.computed_area_hectares) * Decimal("2.4710538147"), "PARCEL_COMPUTED_HECTARES"
    return Decimal("0"), None


def build_profit_loss_summary(
    db: Session,
    *,
    tenant_id: str,
    cycle_id: uuid.UUID,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or DEFAULT_FINANCE_REPORT_CONFIG
    stage_summary = build_stage_cost_summary(db, tenant_id=tenant_id, cycle_id=cycle_id, config=config)
    cycle = _load_cycle(db, tenant_id, cycle_id)
    parcel = db.query(Parcel).filter(Parcel.id == cycle.parcel_id, Parcel.tenant_id == tenant_id).first()

    total_expenses = money(stage_summary["totals"]["actual_expense"])
    total_income = money(cycle.total_revenue)
    profit_or_loss = total_income - total_expenses
    area, area_source = _area_acres(parcel)

    warnings = []
    if total_income == 0:
        warnings.append("No income/revenue has been captured yet; P&L is expense-only until harvest/sale/income data is recorded.")
    if area <= 0:
        warnings.append("Normalized parcel area is unavailable; per-acre P&L values are omitted.")

    income_breakup = []
    if total_income:
        income_breakup.append({
            "income_category": "HARVEST_SALE",
            "amount": money_text(total_income),
            "source": "crop_cycles.total_revenue",
        })

    expense_breakup = defaultdict(lambda: Decimal("0.00"))
    for stage in stage_summary["stage_summaries"]:
        for row in stage["expense_breakup_by_category"]:
            expense_breakup[row["expense_category"]] += money(row["amount"])

    per_acre = None
    if area > 0:
        per_acre = {
            "area_acres": str(area.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
            "area_source": area_source,
            "income_per_acre": money_text(total_income / area),
            "expense_per_acre": money_text(total_expenses / area),
            "profit_or_loss_per_acre": money_text(profit_or_loss / area),
        }

    return {
        "schema_version": "crop_cycle_profit_loss_summary.v1",
        "cycle_id": str(cycle.id),
        "tenant_id": tenant_id,
        "farmer_id": str(cycle.farmer_id),
        "parcel_id": str(cycle.parcel_id),
        "crop_code": cycle.crop_code,
        "season_code": cycle.season_code,
        "currency": config.get("currency") or "INR",
        "fixed_formula": "profit_or_loss = total_income - total_expenses",
        "totals": {
            "total_income": money_text(total_income),
            "total_expenses": money_text(total_expenses),
            "profit_or_loss": money_text(profit_or_loss),
            "planned_expense": stage_summary["totals"]["planned_expense"],
            "expense_variance_amount": stage_summary["totals"]["variance_amount"],
        },
        "income_breakup": income_breakup,
        "expense_breakup": [
            {"expense_category": key, "amount": money_text(value)}
            for key, value in sorted(expense_breakup.items())
        ],
        "per_acre": per_acre,
        "warnings": warnings,
        "report_config": stage_summary["report_config"],
    }
