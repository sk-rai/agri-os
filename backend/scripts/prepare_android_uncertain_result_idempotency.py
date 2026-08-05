"""Prepare baseline for Android uncertain-result sync idempotency QA.

This flow simulates the uncomfortable but common case where Android sends a
sync event, the backend commits it, and Android loses the response before it
can mark its local queue row as synced. Android must retry the exact same
event_id/entity_id/payload, and the backend must not duplicate materialization.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance


TENANT_ID = "android-dynamic-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
FARMER_ID = uuid.UUID("e1ee0941-2bad-4a18-a239-2a4119608a06")
PARCEL_ID = uuid.UUID("98c1a0fa-4f5f-4b8c-97ae-d84992db1c44")
CYCLE_ID = uuid.UUID("aa346148-468b-47de-9c86-47ad41aa1f11")
EXPECTED_STAGE_CODE = "NURSERY"
EXPECTED_COST = Decimal("325.50")
BASELINE_PATH = Path("/tmp/android_uncertain_result_idempotency_baseline.json")
HEADERS = {"X-Tenant-ID": TENANT_ID}

client = TestClient(app)


def money(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def get_json(path: str) -> dict:
    response = client.get(path, headers=HEADERS)
    if response.status_code != 200:
        raise RuntimeError(f"{path} returned {response.status_code}: {response.text[:500]}")
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist ACTIVE cycle/stage normalization and baseline file.")
    args = parser.parse_args()
    dry_run = not args.apply

    db = SessionLocal()
    try:
        cycle = (
            db.query(CropCycle)
            .filter(CropCycle.id == CYCLE_ID, CropCycle.tenant_id == TENANT_ID)
            .first()
        )
        if not cycle:
            raise RuntimeError(f"crop cycle {CYCLE_ID} not found; run prior Android fixture setup first")

        stage = (
            db.query(CropStageInstance)
            .filter(
                CropStageInstance.crop_cycle_id == CYCLE_ID,
                CropStageInstance.tenant_id == TENANT_ID,
                CropStageInstance.stage_code == EXPECTED_STAGE_CODE,
            )
            .first()
        )
        if not stage:
            raise RuntimeError(f"{EXPECTED_STAGE_CODE} stage not found for cycle {CYCLE_ID}")

        before = {
            "cycle_status": cycle.status,
            "cycle_actual_sowing_date": cycle.actual_sowing_date,
            "stage_id": str(stage.id),
            "stage_status": stage.status,
            "stage_actual_start_date": stage.actual_start_date,
        }

        if not dry_run:
            cycle.status = "ACTIVE"
            cycle.actual_sowing_date = cycle.actual_sowing_date or date(2026, 8, 2)
            cycle.updated_at = datetime.now(timezone.utc)
            stage.status = "ACTIVE"
            stage.actual_start_date = stage.actual_start_date or date(2026, 8, 2)
            stage.actual_end_date = None
            stage.updated_at = datetime.now(timezone.utc)
            db.flush()

        activity_query = (
            db.query(CropActivity)
            .filter(
                CropActivity.tenant_id == TENANT_ID,
                CropActivity.crop_cycle_id == CYCLE_ID,
                CropActivity.stage_instance_id == stage.id,
            )
        )
        activity_count = activity_query.count()
        latest = activity_query.order_by(CropActivity.created_at.desc(), CropActivity.updated_at.desc()).first()
        db_activity_cost_total = sum(
            (row.cost_amount or Decimal("0"))
            for row in activity_query.all()
        )

        db.flush()
        stage_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/stage-cost-summary")
        pnl_summary = get_json(f"/api/v1/crop-cycles/{CYCLE_ID}/profit-loss-summary")
        stage_totals = stage_summary.get("totals") or {}
        pnl_totals = pnl_summary.get("totals") or {}

        baseline = {
            "schema_version": "android_uncertain_result_idempotency_baseline.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": TENANT_ID,
            "project_id": str(PROJECT_ID),
            "farmer_id": str(FARMER_ID),
            "parcel_id": str(PARCEL_ID),
            "cycle_id": str(CYCLE_ID),
            "stage_code": EXPECTED_STAGE_CODE,
            "stage_id": str(stage.id),
            "activity_count": activity_count,
            "stage_activity_cost_total": str(db_activity_cost_total),
            "stage_summary_actual_expense": str(money(stage_totals.get("actual_expense"))),
            "pnl_total_expenses": str(money(pnl_totals.get("total_expenses"))),
            "latest_activity_id": str(latest.id) if latest else None,
            "latest_activity_created_at": latest.created_at.isoformat() if latest and latest.created_at else None,
            "expected_new_activity_cost": str(EXPECTED_COST),
        }

        if dry_run:
            db.rollback()
        else:
            db.commit()
            BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True, default=str))

        result = {
            "schema_version": "android_uncertain_result_idempotency_prepare.v1",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "baseline_path": str(BASELINE_PATH),
            "before": before,
            "after": {
                "cycle_status": "ACTIVE" if dry_run else cycle.status,
                "stage_status": "ACTIVE" if dry_run else stage.status,
                "stage_id": str(stage.id),
            },
            "baseline": baseline,
            "android_payload_notes": {
                "entity_type": "crop_activity",
                "operation": "CREATE",
                "android_must_reuse_same_event_id_on_retry": True,
                "android_must_reuse_same_entity_id_on_retry": True,
                "required_cost_amount": str(EXPECTED_COST),
                "dependency_ids": [],
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
