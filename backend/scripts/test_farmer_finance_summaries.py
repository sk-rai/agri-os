"""Regression for backend-owned stage cost and P&L summaries."""

import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Tenant
from app.modules.master_data.models import Crop, CropCategory, CropLifecycleTemplate
from app.modules.media.models import FieldEventReport
from app.modules.workflow.finance_summary import validate_finance_report_config
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance


client = TestClient(app)


def now():
    return datetime.now(timezone.utc)


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main():
    print("=" * 72)
    print("FARMER FINANCE SUMMARY REGRESSION")
    print("=" * 72)

    tenant_id = f"finance-summary-{uuid.uuid4().hex[:8]}"
    actor_id = uuid.uuid4()
    category_id = uuid.uuid4()
    crop_id = uuid.uuid4()
    template_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    cycle_id = uuid.uuid4()
    stage_1_id = uuid.uuid4()
    stage_2_id = uuid.uuid4()

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Finance Summary Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.add(CropCategory(id=category_id, code=f"FINCAT_{uuid.uuid4().hex[:6]}", canonical_name="Finance Test Category", created_at=now(), updated_at=now()))
        db.flush()
        db.add(Crop(
            id=crop_id,
            code=f"FINRICE_{uuid.uuid4().hex[:6]}",
            category_id=category_id,
            canonical_name="Finance Test Rice",
            suitable_seasons=["KHARIF"],
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        crop_code = db.query(Crop).filter(Crop.id == crop_id).first().code
        db.add(CropLifecycleTemplate(
            id=template_id,
            code=f"FIN_TEMPLATE_{uuid.uuid4().hex[:6]}",
            crop_id=crop_id,
            season_code="KHARIF",
            canonical_name="Finance Test Template",
            total_duration_days=60,
            stages=[
                {
                    "code": "SOWING",
                    "name": {"en": "Sowing"},
                    "recommended_activities": [
                        {"activity_type": "SEED", "input_name": "Seed", "typical_quantity": "20 kg", "typical_cost_per_acre": 1200},
                        {"activity_type": "LABOR", "input_name": "Sowing Labor", "typical_quantity": "1 day", "typical_cost_per_acre": 800},
                    ],
                },
                {
                    "code": "VEGETATIVE",
                    "name": {"en": "Vegetative"},
                    "recommended_activities": [
                        {"activity_type": "FERTILIZER", "input_name": "Urea", "typical_quantity": "35 kg", "typical_cost_per_acre": 600},
                    ],
                },
            ],
            is_default=True,
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            mobile_number=f"+9197{uuid.uuid4().int % 100000000:08d}",
            display_name="Finance Farmer",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(Parcel(
            id=parcel_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            village_name_manual="Finance Village",
            pin_code="560001",
            reported_area=Decimal("2.00"),
            reported_area_unit="ACRE",
            ownership_type="OWNED",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(CropCycle(
            id=cycle_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            parcel_id=parcel_id,
            crop_code=crop_code,
            season_code="KHARIF",
            lifecycle_template_id=template_id,
            planned_sowing_date=date(2026, 7, 1),
            status="ACTIVE",
            total_revenue=Decimal("10000.00"),
            created_at=now(),
            updated_at=now(),
        ))
        db.add(CropStageInstance(
            id=stage_1_id,
            crop_cycle_id=cycle_id,
            tenant_id=tenant_id,
            stage_code="SOWING",
            stage_name="Sowing",
            stage_order=1,
            expected_duration_days=15,
            status="COMPLETED",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(CropStageInstance(
            id=stage_2_id,
            crop_cycle_id=cycle_id,
            tenant_id=tenant_id,
            stage_code="VEGETATIVE",
            stage_name="Vegetative",
            stage_order=2,
            expected_duration_days=45,
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(CropActivity(
            id=uuid.uuid4(),
            crop_cycle_id=cycle_id,
            stage_instance_id=stage_1_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            activity_type="SEED",
            input_name="Paddy Seed",
            quantity=Decimal("20"),
            quantity_unit="KG",
            cost_amount=Decimal("1500.00"),
            cost_currency="INR",
            activity_date=date(2026, 7, 1),
            logged_by=actor_id,
            created_at=now(),
            updated_at=now(),
        ))
        db.add(CropActivity(
            id=uuid.uuid4(),
            crop_cycle_id=cycle_id,
            stage_instance_id=stage_2_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            activity_type="FERTILIZER",
            input_name="Urea",
            quantity=Decimal("35"),
            quantity_unit="KG",
            cost_amount=Decimal("700.00"),
            cost_currency="INR",
            activity_date=date(2026, 7, 20),
            logged_by=actor_id,
            created_at=now(),
            updated_at=now(),
        ))
        db.add(FieldEventReport(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            parcel_id=parcel_id,
            crop_cycle_id=cycle_id,
            stage_code="VEGETATIVE",
            event_type="RAIN",
            severity="MEDIUM",
            event_date=now(),
            reported_at=now(),
            description="Useful rain during vegetative stage",
            source="FIELD_AGENT_ANDROID",
            status="REPORTED",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
    finally:
        db.close()

    try:
        r = client.get("/api/v1/crop-cycles/finance/report-config", headers={"X-Tenant-ID": tenant_id})
        check(r.status_code == 200, "Finance config endpoint returns 200", r.text)
        config = r.json()
        check(config["validation"]["valid"] is True, "Default finance config validates")
        check(config["config"]["fixed_formula"] == "profit_or_loss = total_income - total_expenses", "P&L formula fixed")

        bad = validate_finance_report_config({
            "income_categories": ["HARVEST_SALE", "BOGUS"],
            "expense_categories": ["SEED"],
            "context_event_categories": ["RAIN"],
            "activity_expense_mapping": {"SEED": "SEED"},
            "display": {"show_planned_cost": True},
            "thresholds": {"cost_variance_warning_percent": 20},
        })
        check(bad["valid"] is False, "Invalid category mapping fails validation", bad["errors"])

        r = client.get(f"/api/v1/crop-cycles/{cycle_id}/stage-cost-summary", headers={"X-Tenant-ID": tenant_id})
        check(r.status_code == 200, "Stage cost summary returns 200", r.text)
        stage_summary = r.json()
        check(stage_summary["schema_version"] == "crop_cycle_stage_cost_summary.v1", "Stage summary schema stable")
        check(stage_summary["totals"]["actual_expense"] == "2200.00", "Actual expenses aggregate")
        sowing = next(row for row in stage_summary["stage_summaries"] if row["stage_code"] == "SOWING")
        veg = next(row for row in stage_summary["stage_summaries"] if row["stage_code"] == "VEGETATIVE")
        check(sowing["planned_expense"] == "2000.00", "Sowing planned expense aggregates recommendations")
        check(sowing["actual_expense"] == "1500.00", "Sowing actual expense aggregates activities")
        check(veg["context_events"][0]["event_type"] == "RAIN", "Natural/context events included by stage")

        r = client.get(f"/api/v1/crop-cycles/{cycle_id}/profit-loss-summary", headers={"X-Tenant-ID": tenant_id})
        check(r.status_code == 200, "P&L summary returns 200", r.text)
        pnl = r.json()
        check(pnl["schema_version"] == "crop_cycle_profit_loss_summary.v1", "P&L schema stable")
        check(pnl["fixed_formula"] == "profit_or_loss = total_income - total_expenses", "P&L response states fixed formula")
        check(pnl["totals"]["total_income"] == "10000.00", "Income maps from captured revenue")
        check(pnl["totals"]["total_expenses"] == "2200.00", "Expenses map from configured activity categories")
        check(pnl["totals"]["profit_or_loss"] == "7800.00", "P&L equals income minus expenses")
        check(pnl["per_acre"]["profit_or_loss_per_acre"] == "3900.00", "Per-acre P&L calculated from parcel acres")

        print("=" * 72)
        print("Farmer finance summaries validated")
        print("=" * 72)
    finally:
        db = SessionLocal()
        try:
            db.query(FieldEventReport).filter(FieldEventReport.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(CropActivity).filter(CropActivity.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(CropStageInstance).filter(CropStageInstance.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(CropCycle).filter(CropCycle.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(CropLifecycleTemplate).filter(CropLifecycleTemplate.id == template_id).delete(synchronize_session=False)
            db.query(Crop).filter(Crop.id == crop_id).delete(synchronize_session=False)
            db.query(CropCategory).filter(CropCategory.id == category_id).delete(synchronize_session=False)
            db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    main()
