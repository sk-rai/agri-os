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
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance, WorkflowFinanceReportConfig
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



def _date_dimensions(value) -> dict[str, Any]:
    if not value:
        return {"date": None, "year": None, "month": None, "quarter": None}
    quarter = ((value.month - 1) // 3) + 1
    return {
        "date": value.isoformat(),
        "year": value.year,
        "month": f"{value.year:04d}-{value.month:02d}",
        "quarter": f"{value.year:04d}-Q{quarter}",
    }


def _cycle_dimensions(cycle: CropCycle) -> dict[str, Any]:
    sowing = cycle.actual_sowing_date or cycle.planned_sowing_date
    harvest = cycle.actual_harvest_date or cycle.expected_harvest_date
    return {
        "crop_code": cycle.crop_code,
        "season_code": cycle.season_code,
        "project_id": str(cycle.project_id) if cycle.project_id else None,
        "planned_sowing": _date_dimensions(cycle.planned_sowing_date),
        "actual_sowing": _date_dimensions(cycle.actual_sowing_date),
        "effective_sowing": _date_dimensions(sowing),
        "expected_harvest": _date_dimensions(cycle.expected_harvest_date),
        "actual_harvest": _date_dimensions(cycle.actual_harvest_date),
        "effective_harvest": _date_dimensions(harvest),
        "season_year": sowing.year if sowing else None,
    }


def _config_scope_filter(query, *, tenant_id: str, project_id, crop_code: str | None, season_code: str | None):
    project_filter = (
        WorkflowFinanceReportConfig.project_id.is_(None)
        if project_id is None
        else ((WorkflowFinanceReportConfig.project_id == project_id) | (WorkflowFinanceReportConfig.project_id.is_(None)))
    )
    crop_filter = (
        WorkflowFinanceReportConfig.crop_code.is_(None)
        if not crop_code
        else ((WorkflowFinanceReportConfig.crop_code == crop_code) | (WorkflowFinanceReportConfig.crop_code.is_(None)))
    )
    season_filter = (
        WorkflowFinanceReportConfig.season_code.is_(None)
        if not season_code
        else ((WorkflowFinanceReportConfig.season_code == season_code) | (WorkflowFinanceReportConfig.season_code.is_(None)))
    )

    return query.filter(
        WorkflowFinanceReportConfig.tenant_id == tenant_id,
        WorkflowFinanceReportConfig.is_active == True,
        WorkflowFinanceReportConfig.status == "PUBLISHED",
        project_filter,
        crop_filter,
        season_filter,
    )


def _scope_rank(row: WorkflowFinanceReportConfig, *, project_id, crop_code: str | None, season_code: str | None) -> int:
    rank = 0
    if project_id and row.project_id == project_id:
        rank += 4
    if crop_code and row.crop_code == crop_code:
        rank += 2
    if season_code and row.season_code == season_code:
        rank += 1
    return rank


def load_finance_report_config_for_cycle(db: Session, cycle: CropCycle) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = _config_scope_filter(
        db.query(WorkflowFinanceReportConfig),
        tenant_id=cycle.tenant_id,
        project_id=cycle.project_id,
        crop_code=cycle.crop_code,
        season_code=cycle.season_code,
    ).all()

    if not rows:
        return DEFAULT_FINANCE_REPORT_CONFIG, {
            "source": "DEFAULT_CONFIG",
            "config_id": None,
            "config_version": None,
            "scope": {"tenant_id": cycle.tenant_id, "project_id": None, "crop_code": None, "season_code": None},
        }

    selected = sorted(
        rows,
        key=lambda row: (_scope_rank(row, project_id=cycle.project_id, crop_code=cycle.crop_code, season_code=cycle.season_code), row.config_version),
        reverse=True,
    )[0]

    return selected.config, {
        "source": "PUBLISHED_CONFIG",
        "config_id": str(selected.id),
        "config_version": selected.config_version,
        "scope": {
            "tenant_id": selected.tenant_id,
            "project_id": str(selected.project_id) if selected.project_id else None,
            "crop_code": selected.crop_code,
            "season_code": selected.season_code,
        },
    }


def load_finance_report_config_for_scope(
    db: Session,
    *,
    tenant_id: str,
    project_id=None,
    crop_code: str | None = None,
    season_code: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = _config_scope_filter(
        db.query(WorkflowFinanceReportConfig),
        tenant_id=tenant_id,
        project_id=project_id,
        crop_code=crop_code,
        season_code=season_code,
    ).all()

    if not rows:
        return DEFAULT_FINANCE_REPORT_CONFIG, {
            "source": "DEFAULT_CONFIG",
            "config_id": None,
            "config_version": None,
            "scope": {"tenant_id": tenant_id, "project_id": None, "crop_code": None, "season_code": None},
        }

    selected = sorted(
        rows,
        key=lambda row: (_scope_rank(row, project_id=project_id, crop_code=crop_code, season_code=season_code), row.config_version),
        reverse=True,
    )[0]

    return selected.config, {
        "source": "PUBLISHED_CONFIG",
        "config_id": str(selected.id),
        "config_version": selected.config_version,
        "scope": {
            "tenant_id": selected.tenant_id,
            "project_id": str(selected.project_id) if selected.project_id else None,
            "crop_code": selected.crop_code,
            "season_code": selected.season_code,
        },
    }



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


def _activity_row(activity: CropActivity, expense_category: str, currency: str, cycle: CropCycle, stage_code: str | None = None) -> dict[str, Any]:
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
        "analytics_dimensions": {
            "crop_code": cycle.crop_code,
            "season_code": cycle.season_code,
            "season_year": _cycle_dimensions(cycle).get("season_year"),
            "stage_code": stage_code,
            "activity_date": _date_dimensions(activity.activity_date),
        },
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

def _dimension_value(cycle: CropCycle, dimensions: dict[str, Any], key: str) -> Any:
    if key == "project_id":
        return str(cycle.project_id) if cycle.project_id else None
    if key == "farmer_id":
        return str(cycle.farmer_id)
    if key == "parcel_id":
        return str(cycle.parcel_id)
    return dimensions.get(key)


def build_finance_analytics_summary(
    db: Session,
    *,
    tenant_id: str,
    project_id=None,
    farmer_id=None,
    parcel_id=None,
    crop_code: str | None = None,
    season_code: str | None = None,
    season_year: int | None = None,
    activity_date_from=None,
    activity_date_to=None,
    period: str = "month",
    limit: int = 500,
) -> dict[str, Any]:
    """Aggregate farmer finance across crop, season, stage, and time dimensions."""
    period = (period or "month").lower()
    if period not in {"month", "quarter", "year"}:
        raise HTTPException(422, "period must be one of month, quarter, year")

    cycle_query = db.query(CropCycle).filter(
        CropCycle.tenant_id == tenant_id,
        CropCycle.is_active == True,
    )
    if project_id:
        cycle_query = cycle_query.filter(CropCycle.project_id == project_id)
    if farmer_id:
        cycle_query = cycle_query.filter(CropCycle.farmer_id == farmer_id)
    if parcel_id:
        cycle_query = cycle_query.filter(CropCycle.parcel_id == parcel_id)
    if crop_code:
        cycle_query = cycle_query.filter(CropCycle.crop_code == crop_code.upper())
    if season_code:
        cycle_query = cycle_query.filter(CropCycle.season_code == season_code.upper())

    cycles = cycle_query.order_by(CropCycle.planned_sowing_date.asc(), CropCycle.created_at.asc()).limit(limit).all()
    if season_year is not None:
        cycles = [cycle for cycle in cycles if _cycle_dimensions(cycle).get("season_year") == season_year]

    cycle_ids = [cycle.id for cycle in cycles]
    stages = (
        db.query(CropStageInstance)
        .filter(CropStageInstance.tenant_id == tenant_id, CropStageInstance.crop_cycle_id.in_(cycle_ids))
        .all()
        if cycle_ids
        else []
    )
    stage_by_id = {stage.id: stage for stage in stages}

    activity_query = db.query(CropActivity).filter(
        CropActivity.tenant_id == tenant_id,
        CropActivity.crop_cycle_id.in_(cycle_ids),
        CropActivity.is_active == True,
    )
    if activity_date_from:
        activity_query = activity_query.filter(CropActivity.activity_date >= activity_date_from)
    if activity_date_to:
        activity_query = activity_query.filter(CropActivity.activity_date <= activity_date_to)
    activities = activity_query.order_by(CropActivity.activity_date.asc()).all() if cycle_ids else []

    cycles_by_id = {cycle.id: cycle for cycle in cycles}
    totals = {
        "cycle_count": len(cycles),
        "activity_count": len(activities),
        "total_income": Decimal("0.00"),
        "total_expenses": Decimal("0.00"),
    }
    cycle_groups = defaultdict(lambda: {"cycle_count": 0, "total_income": Decimal("0.00"), "total_expenses": Decimal("0.00")})
    stage_groups = defaultdict(lambda: {"activity_count": 0, "actual_expense": Decimal("0.00")})
    period_groups = defaultdict(lambda: {"activity_count": 0, "actual_expense": Decimal("0.00")})
    expense_category_groups = defaultdict(lambda: {"activity_count": 0, "actual_expense": Decimal("0.00")})
    config_cache: dict[uuid.UUID, tuple[dict[str, Any], dict[str, Any]]] = {}

    for cycle in cycles:
        dimensions = _cycle_dimensions(cycle)
        total_income = money(cycle.total_revenue)
        totals["total_income"] += total_income
        key = (
            _dimension_value(cycle, dimensions, "crop_code"),
            _dimension_value(cycle, dimensions, "season_code"),
            _dimension_value(cycle, dimensions, "season_year"),
            _dimension_value(cycle, dimensions, "project_id"),
        )
        cycle_groups[key]["cycle_count"] += 1
        cycle_groups[key]["total_income"] += total_income

    for activity in activities:
        cycle = cycles_by_id.get(activity.crop_cycle_id)
        if not cycle:
            continue
        config, _ = config_cache.setdefault(cycle.id, load_finance_report_config_for_cycle(db, cycle))
        activity_mapping = config.get("activity_expense_mapping") or {}
        expense_category = activity_mapping.get((activity.activity_type or "OTHER").upper(), "OTHER_EXPENSE")
        cost = money(activity.cost_amount)
        totals["total_expenses"] += cost

        dimensions = _cycle_dimensions(cycle)
        cycle_key = (
            _dimension_value(cycle, dimensions, "crop_code"),
            _dimension_value(cycle, dimensions, "season_code"),
            _dimension_value(cycle, dimensions, "season_year"),
            _dimension_value(cycle, dimensions, "project_id"),
        )
        cycle_groups[cycle_key]["total_expenses"] += cost

        stage = stage_by_id.get(activity.stage_instance_id)
        stage_key = (cycle.crop_code, cycle.season_code, dimensions.get("season_year"), stage.stage_code if stage else "UNASSIGNED")
        stage_groups[stage_key]["activity_count"] += 1
        stage_groups[stage_key]["actual_expense"] += cost

        period_dimensions = _date_dimensions(activity.activity_date)
        period_key = period_dimensions.get(period)
        period_groups[(period_key, cycle.crop_code, cycle.season_code)]["activity_count"] += 1
        period_groups[(period_key, cycle.crop_code, cycle.season_code)]["actual_expense"] += cost

        expense_category_groups[(expense_category, cycle.crop_code, cycle.season_code)]["activity_count"] += 1
        expense_category_groups[(expense_category, cycle.crop_code, cycle.season_code)]["actual_expense"] += cost

    def cycle_row(item):
        (crop, season, year, project), values = item
        profit = values["total_income"] - values["total_expenses"]
        return {
            "crop_code": crop,
            "season_code": season,
            "season_year": year,
            "project_id": project,
            "cycle_count": values["cycle_count"],
            "total_income": money_text(values["total_income"]),
            "total_expenses": money_text(values["total_expenses"]),
            "profit_or_loss": money_text(profit),
        }

    return {
        "schema_version": "finance_analytics_summary.v1",
        "tenant_id": tenant_id,
        "currency": "INR",
        "fixed_formula": "profit_or_loss = total_income - total_expenses",
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "farmer_id": str(farmer_id) if farmer_id else None,
            "parcel_id": str(parcel_id) if parcel_id else None,
            "crop_code": crop_code.upper() if crop_code else None,
            "season_code": season_code.upper() if season_code else None,
            "season_year": season_year,
            "activity_date_from": activity_date_from.isoformat() if activity_date_from else None,
            "activity_date_to": activity_date_to.isoformat() if activity_date_to else None,
            "period": period,
            "limit": limit,
        },
        "totals": {
            "cycle_count": totals["cycle_count"],
            "activity_count": totals["activity_count"],
            "total_income": money_text(totals["total_income"]),
            "total_expenses": money_text(totals["total_expenses"]),
            "profit_or_loss": money_text(totals["total_income"] - totals["total_expenses"]),
        },
        "cycle_summary_groups": [cycle_row(item) for item in sorted(cycle_groups.items())],
        "stage_cost_groups": [
            {
                "crop_code": crop,
                "season_code": season,
                "season_year": year,
                "stage_code": stage,
                "activity_count": values["activity_count"],
                "actual_expense": money_text(values["actual_expense"]),
            }
            for (crop, season, year, stage), values in sorted(stage_groups.items())
        ],
        "activity_period_groups": [
            {
                "period": period_key,
                "crop_code": crop,
                "season_code": season,
                "activity_count": values["activity_count"],
                "actual_expense": money_text(values["actual_expense"]),
            }
            for (period_key, crop, season), values in sorted(period_groups.items())
        ],
        "expense_category_groups": [
            {
                "expense_category": category,
                "crop_code": crop,
                "season_code": season,
                "activity_count": values["activity_count"],
                "actual_expense": money_text(values["actual_expense"]),
            }
            for (category, crop, season), values in sorted(expense_category_groups.items())
        ],
        "notes": [
            "Income is cycle-level revenue; stage and activity-period groups show expenses only unless revenue allocation is added later.",
            "This endpoint is a read-model contract over operational tables and can later be backed by materialized aggregates.",
        ],
    }


def _dimension_value(cycle: CropCycle, dimensions: dict[str, Any], key: str) -> Any:
    if key == "project_id":
        return str(cycle.project_id) if cycle.project_id else None
    if key == "farmer_id":
        return str(cycle.farmer_id)
    if key == "parcel_id":
        return str(cycle.parcel_id)
    return dimensions.get(key)


def build_finance_analytics_summary(
    db: Session,
    *,
    tenant_id: str,
    project_id=None,
    farmer_id=None,
    parcel_id=None,
    crop_code: str | None = None,
    season_code: str | None = None,
    season_year: int | None = None,
    activity_date_from=None,
    activity_date_to=None,
    period: str = "month",
    limit: int = 500,
) -> dict[str, Any]:
    """Aggregate farmer finance across crop, season, stage, and time dimensions."""
    period = (period or "month").lower()
    if period not in {"month", "quarter", "year"}:
        raise HTTPException(422, "period must be one of month, quarter, year")

    cycle_query = db.query(CropCycle).filter(
        CropCycle.tenant_id == tenant_id,
        CropCycle.is_active == True,
    )
    if project_id:
        cycle_query = cycle_query.filter(CropCycle.project_id == project_id)
    if farmer_id:
        cycle_query = cycle_query.filter(CropCycle.farmer_id == farmer_id)
    if parcel_id:
        cycle_query = cycle_query.filter(CropCycle.parcel_id == parcel_id)
    if crop_code:
        cycle_query = cycle_query.filter(CropCycle.crop_code == crop_code.upper())
    if season_code:
        cycle_query = cycle_query.filter(CropCycle.season_code == season_code.upper())

    cycles = cycle_query.order_by(CropCycle.planned_sowing_date.asc(), CropCycle.created_at.asc()).limit(limit).all()
    if season_year is not None:
        cycles = [cycle for cycle in cycles if _cycle_dimensions(cycle).get("season_year") == season_year]

    cycle_ids = [cycle.id for cycle in cycles]
    stages = (
        db.query(CropStageInstance)
        .filter(CropStageInstance.tenant_id == tenant_id, CropStageInstance.crop_cycle_id.in_(cycle_ids))
        .all()
        if cycle_ids
        else []
    )
    stage_by_id = {stage.id: stage for stage in stages}

    activity_query = db.query(CropActivity).filter(
        CropActivity.tenant_id == tenant_id,
        CropActivity.crop_cycle_id.in_(cycle_ids),
        CropActivity.is_active == True,
    )
    if activity_date_from:
        activity_query = activity_query.filter(CropActivity.activity_date >= activity_date_from)
    if activity_date_to:
        activity_query = activity_query.filter(CropActivity.activity_date <= activity_date_to)
    activities = activity_query.order_by(CropActivity.activity_date.asc()).all() if cycle_ids else []

    cycles_by_id = {cycle.id: cycle for cycle in cycles}
    totals = {
        "cycle_count": len(cycles),
        "activity_count": len(activities),
        "total_income": Decimal("0.00"),
        "total_expenses": Decimal("0.00"),
    }
    cycle_groups = defaultdict(lambda: {"cycle_count": 0, "total_income": Decimal("0.00"), "total_expenses": Decimal("0.00")})
    stage_groups = defaultdict(lambda: {"activity_count": 0, "actual_expense": Decimal("0.00")})
    period_groups = defaultdict(lambda: {"activity_count": 0, "actual_expense": Decimal("0.00")})
    expense_category_groups = defaultdict(lambda: {"activity_count": 0, "actual_expense": Decimal("0.00")})
    config_cache: dict[uuid.UUID, tuple[dict[str, Any], dict[str, Any]]] = {}

    for cycle in cycles:
        dimensions = _cycle_dimensions(cycle)
        total_income = money(cycle.total_revenue)
        totals["total_income"] += total_income
        key = (
            _dimension_value(cycle, dimensions, "crop_code"),
            _dimension_value(cycle, dimensions, "season_code"),
            _dimension_value(cycle, dimensions, "season_year"),
            _dimension_value(cycle, dimensions, "project_id"),
        )
        cycle_groups[key]["cycle_count"] += 1
        cycle_groups[key]["total_income"] += total_income

    for activity in activities:
        cycle = cycles_by_id.get(activity.crop_cycle_id)
        if not cycle:
            continue
        config, _ = config_cache.setdefault(cycle.id, load_finance_report_config_for_cycle(db, cycle))
        activity_mapping = config.get("activity_expense_mapping") or {}
        expense_category = activity_mapping.get((activity.activity_type or "OTHER").upper(), "OTHER_EXPENSE")
        cost = money(activity.cost_amount)
        totals["total_expenses"] += cost

        dimensions = _cycle_dimensions(cycle)
        cycle_key = (
            _dimension_value(cycle, dimensions, "crop_code"),
            _dimension_value(cycle, dimensions, "season_code"),
            _dimension_value(cycle, dimensions, "season_year"),
            _dimension_value(cycle, dimensions, "project_id"),
        )
        cycle_groups[cycle_key]["total_expenses"] += cost

        stage = stage_by_id.get(activity.stage_instance_id)
        stage_key = (cycle.crop_code, cycle.season_code, dimensions.get("season_year"), stage.stage_code if stage else "UNASSIGNED")
        stage_groups[stage_key]["activity_count"] += 1
        stage_groups[stage_key]["actual_expense"] += cost

        period_dimensions = _date_dimensions(activity.activity_date)
        period_key = period_dimensions.get(period)
        period_groups[(period_key, cycle.crop_code, cycle.season_code)]["activity_count"] += 1
        period_groups[(period_key, cycle.crop_code, cycle.season_code)]["actual_expense"] += cost

        expense_category_groups[(expense_category, cycle.crop_code, cycle.season_code)]["activity_count"] += 1
        expense_category_groups[(expense_category, cycle.crop_code, cycle.season_code)]["actual_expense"] += cost

    def cycle_row(item):
        (crop, season, year, project), values = item
        profit = values["total_income"] - values["total_expenses"]
        return {
            "crop_code": crop,
            "season_code": season,
            "season_year": year,
            "project_id": project,
            "cycle_count": values["cycle_count"],
            "total_income": money_text(values["total_income"]),
            "total_expenses": money_text(values["total_expenses"]),
            "profit_or_loss": money_text(profit),
        }

    return {
        "schema_version": "finance_analytics_summary.v1",
        "tenant_id": tenant_id,
        "currency": "INR",
        "fixed_formula": "profit_or_loss = total_income - total_expenses",
        "filters": {
            "project_id": str(project_id) if project_id else None,
            "farmer_id": str(farmer_id) if farmer_id else None,
            "parcel_id": str(parcel_id) if parcel_id else None,
            "crop_code": crop_code.upper() if crop_code else None,
            "season_code": season_code.upper() if season_code else None,
            "season_year": season_year,
            "activity_date_from": activity_date_from.isoformat() if activity_date_from else None,
            "activity_date_to": activity_date_to.isoformat() if activity_date_to else None,
            "period": period,
            "limit": limit,
        },
        "totals": {
            "cycle_count": totals["cycle_count"],
            "activity_count": totals["activity_count"],
            "total_income": money_text(totals["total_income"]),
            "total_expenses": money_text(totals["total_expenses"]),
            "profit_or_loss": money_text(totals["total_income"] - totals["total_expenses"]),
        },
        "cycle_summary_groups": [cycle_row(item) for item in sorted(cycle_groups.items())],
        "stage_cost_groups": [
            {
                "crop_code": crop,
                "season_code": season,
                "season_year": year,
                "stage_code": stage,
                "activity_count": values["activity_count"],
                "actual_expense": money_text(values["actual_expense"]),
            }
            for (crop, season, year, stage), values in sorted(stage_groups.items())
        ],
        "activity_period_groups": [
            {
                "period": period_key,
                "crop_code": crop,
                "season_code": season,
                "activity_count": values["activity_count"],
                "actual_expense": money_text(values["actual_expense"]),
            }
            for (period_key, crop, season), values in sorted(period_groups.items())
        ],
        "expense_category_groups": [
            {
                "expense_category": category,
                "crop_code": crop,
                "season_code": season,
                "activity_count": values["activity_count"],
                "actual_expense": money_text(values["actual_expense"]),
            }
            for (category, crop, season), values in sorted(expense_category_groups.items())
        ],
        "notes": [
            "Income is cycle-level revenue; stage and activity-period groups show expenses only unless revenue allocation is added later.",
            "This endpoint is a read-model contract over operational tables and can later be backed by materialized aggregates.",
        ],
    }
def build_stage_cost_summary(
    db: Session,
    *,
    tenant_id: str,
    cycle_id: uuid.UUID,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config_source = None
    if config is None:
        cycle_for_config = _load_cycle(db, tenant_id, cycle_id)
        config, config_source = load_finance_report_config_for_cycle(db, cycle_for_config)
    validation = validate_finance_report_config(config)
    if not validation["valid"]:
        raise HTTPException(409, {"error": "FINANCE_REPORT_CONFIG_INVALID", "validation": validation})

    cycle = cycle_for_config if 'cycle_for_config' in locals() else _load_cycle(db, tenant_id, cycle_id)
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

    stage_code_by_id = {stage.id: stage.stage_code for stage in stages}

    for activity in activities:
        stage_key = activity.stage_instance_id or unassigned_key
        expense_category = activity_mapping.get((activity.activity_type or "OTHER").upper(), "OTHER_EXPENSE")
        cost = money(activity.cost_amount)

        actual_by_stage[stage_key] += cost
        type_breakup_by_stage[stage_key][activity.activity_type or "OTHER"] += cost
        expense_breakup_by_stage[stage_key][expense_category] += cost
        input_label = activity.input_name or activity.input_code or activity.activity_type or "Activity"
        input_breakup_by_stage[stage_key][input_label] += cost
        activities_by_stage[stage_key].append(_activity_row(activity, expense_category, currency, cycle, stage_code_by_id.get(activity.stage_instance_id)))

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
            "analytics_dimensions": {
                "crop_code": cycle.crop_code,
                "season_code": cycle.season_code,
                "season_year": _cycle_dimensions(cycle).get("season_year"),
                "stage_code": stage.stage_code,
                "planned_start": _date_dimensions(stage.planned_start_date),
                "actual_start": _date_dimensions(stage.actual_start_date),
                "actual_end": _date_dimensions(stage.actual_end_date),
            },
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
            "source": config_source or {"source": "REQUEST_CONFIG"},
        },
        "analytics_dimensions": _cycle_dimensions(cycle),
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
    if config is None:
        cycle_for_config = _load_cycle(db, tenant_id, cycle_id)
        config, _ = load_finance_report_config_for_cycle(db, cycle_for_config)
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
        "analytics_dimensions": _cycle_dimensions(cycle),
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
