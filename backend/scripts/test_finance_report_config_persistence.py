#!/usr/bin/env python3
"""Regression checks for persisted finance report config and analytics dimensions."""

from __future__ import annotations

from pathlib import Path
import sys
import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.master_data.models import CropLifecycleTemplate
from app.modules.workflow.finance_summary import DEFAULT_FINANCE_REPORT_CONFIG
from app.modules.workflow.models import (
    CropActivity,
    CropCycle,
    CropStageInstance,
    WorkflowFinanceReportConfig,
)


client = TestClient(app)


def check(condition, label, detail=None):
    if condition:
        print(f"  PASS {label}")
        if detail is not None:
            print(f"       {detail}")
        return
    print(f"  FAIL {label}")
    if detail is not None:
        print(f"       {detail}")
    raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("FINANCE REPORT CONFIG PERSISTENCE REGRESSION")
    print("=" * 72)

    tenant_id = f"finance-config-{uuid.uuid4().hex[:8]}"
    headers = {"X-Tenant-ID": tenant_id, "X-Actor-ID": str(uuid.uuid4())}

    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    cycle_id = uuid.uuid4()
    stage_id = uuid.uuid4()

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        lifecycle_template = db.query(CropLifecycleTemplate).first()
        check(lifecycle_template is not None, "At least one lifecycle template exists")

        db.add(Tenant(id=tenant_id, name="Finance Config Tenant", type="ENTERPRISE", created_at=now, updated_at=now))
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Finance Config Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            created_at=now,
            updated_at=now,
        ))
        db.commit()
        db.add(Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            mobile_number=f"+9199{uuid.uuid4().int % 100000000:08d}",
            display_name="Finance Config Farmer",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        ))
        db.add(Parcel(
            id=parcel_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            project_id=project_id,
            reported_area=Decimal("2.00"),
            reported_area_unit="ACRE",
            geometry_source="NONE",
            pin_code="560001",
            village_name_manual="Finance Village",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        ))
        db.add(CropCycle(
            id=cycle_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            parcel_id=parcel_id,
            project_id=project_id,
            crop_code="RICE",
            season_code="KHARIF",
            lifecycle_template_id=lifecycle_template.id,
            planned_sowing_date=date(2026, 6, 15),
            actual_sowing_date=date(2026, 6, 20),
            expected_harvest_date=date(2026, 10, 15),
            status="ACTIVE",
            total_revenue=Decimal("15000.00"),
            created_at=now,
            updated_at=now,
        ))
        db.add(CropStageInstance(
            id=stage_id,
            tenant_id=tenant_id,
            crop_cycle_id=cycle_id,
            stage_code="VEGETATIVE",
            stage_name="Vegetative",
            stage_order=1,
            planned_start_date=date(2026, 7, 1),
            actual_start_date=date(2026, 7, 2),
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        ))
        db.add(CropActivity(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            crop_cycle_id=cycle_id,
            stage_instance_id=stage_id,
            farmer_id=farmer_id,
            activity_type="FERTILIZER",
            input_code="UREA",
            input_name="Urea",
            quantity=Decimal("20"),
            quantity_unit="KG",
            area_applied=Decimal("2"),
            area_unit="ACRE",
            cost_amount=Decimal("1200.00"),
            cost_currency="INR",
            activity_date=date(2026, 7, 10),
            logged_by=uuid.uuid4(),
            logging_method="MANUAL",
            created_at=now,
            updated_at=now,
        ))
        db.commit()

        get_default = client.get("/api/v1/crop-cycles/finance/report-config", headers=headers)
        check(get_default.status_code == 200, "Default finance config lookup returns 200", get_default.text[:500])
        default_payload = get_default.json()
        check(default_payload["source"]["source"] == "DEFAULT_CONFIG", "Default config source is reported")

        invalid_config = dict(DEFAULT_FINANCE_REPORT_CONFIG)
        invalid_config["expense_categories"] = ["SEED"]
        invalid_config["activity_expense_mapping"] = {"FERTILIZER": "NOT_ALLOWED"}

        invalid = client.post(
            "/api/v1/crop-cycles/finance/report-config/publish",
            headers=headers,
            json={"config": invalid_config, "reason": "invalid regression"},
        )
        check(invalid.status_code == 409, "Invalid persisted config publish is rejected", invalid.text[:500])

        config = dict(DEFAULT_FINANCE_REPORT_CONFIG)
        config["status"] = "PUBLISHED_TEST"
        config["display"] = dict(config["display"])
        config["display"]["show_activity_rows"] = False

        publish = client.post(
            "/api/v1/crop-cycles/finance/report-config/publish",
            headers=headers,
            json={"config": config, "reason": "regression publish"},
        )
        check(publish.status_code == 200, "Valid finance config publish returns 200", publish.text[:500])
        published = publish.json()
        check(published["status"] == "PUBLISHED", "Published config status is PUBLISHED")
        check(published["config_version"] == 1, "First config version is 1")

        get_published = client.get("/api/v1/crop-cycles/finance/report-config", headers=headers)
        check(get_published.status_code == 200, "Published finance config lookup returns 200", get_published.text[:500])
        check(get_published.json()["source"]["source"] == "PUBLISHED_CONFIG", "Published config source is reported")

        stage = client.get(f"/api/v1/crop-cycles/{cycle_id}/stage-cost-summary", headers=headers)
        check(stage.status_code == 200, "Stage summary returns 200", stage.text[:500])
        stage_payload = stage.json()
        check(stage_payload["report_config"]["source"]["source"] == "PUBLISHED_CONFIG", "Stage summary uses published config")
        check(stage_payload["analytics_dimensions"]["crop_code"] == "RICE", "Cycle analytics crop dimension present")
        check(stage_payload["analytics_dimensions"]["season_code"] == "KHARIF", "Cycle analytics season dimension present")
        check(stage_payload["analytics_dimensions"]["season_year"] == 2026, "Cycle analytics season year present")
        check(stage_payload["stage_summaries"][0]["analytics_dimensions"]["stage_code"] == "VEGETATIVE", "Stage analytics dimension present")
        check(stage_payload["stage_summaries"][0]["activities"][0]["analytics_dimensions"]["activity_date"]["month"] == "2026-07", "Activity month dimension present")

        pnl = client.get(f"/api/v1/crop-cycles/{cycle_id}/profit-loss-summary", headers=headers)
        check(pnl.status_code == 200, "P&L summary returns 200", pnl.text[:500])
        pnl_payload = pnl.json()
        check(pnl_payload["fixed_formula"] == "profit_or_loss = total_income - total_expenses", "P&L formula remains fixed")
        check(pnl_payload["totals"]["total_income"] == "15000.00", "P&L income captured")
        check(pnl_payload["totals"]["total_expenses"] == "1200.00", "P&L expenses captured")
        check(pnl_payload["totals"]["profit_or_loss"] == "13800.00", "P&L fixed formula computed")
        check(pnl_payload["analytics_dimensions"]["season_code"] == "KHARIF", "P&L analytics dimensions present")

        stored_count = db.query(WorkflowFinanceReportConfig).filter(WorkflowFinanceReportConfig.tenant_id == tenant_id).count()
        check(stored_count == 1, "One persisted finance config row stored")

        print("=" * 72)
        print("Finance report config persistence validated")
        print("=" * 72)
        return 0

    finally:
        db.query(CropActivity).filter(CropActivity.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(CropStageInstance).filter(CropStageInstance.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(CropCycle).filter(CropCycle.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(WorkflowFinanceReportConfig).filter(WorkflowFinanceReportConfig.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())