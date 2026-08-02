"""Prepare or restore Android stale-context sync failure fixture.

This helper intentionally mutates only the Android dynamic test parcel's
project_id so a queued offline crop_cycle replay fails with:

    error_code=MATERIALIZATION_FAILED
    detail_code=PARCEL_PROJECT_MISMATCH

Use only for the android-dynamic-test tenant.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data import models as _master_data_models  # noqa: F401
from app.modules.farmer.models import Parcel, Project, Tenant


TENANT_ID = "android-dynamic-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
ALT_PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000002")
FARMER_ID = uuid.UUID("e1ee0941-2bad-4a18-a239-2a4119608a06")
PARCEL_ID = uuid.UUID("98c1a0fa-4f5f-4b8c-97ae-d84992db1c44")


def ensure_alt_project(db, dry_run: bool) -> str:
    project = (
        db.query(Project)
        .filter(Project.id == ALT_PROJECT_ID, Project.tenant_id == TENANT_ID)
        .first()
    )
    if project:
        return "EXISTS"

    if dry_run:
        return "WOULD_CREATE"

    tenant = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    if not tenant:
        raise RuntimeError(f"tenant {TENANT_ID} not found; seed android dynamic test context first")

    project = Project(
        id=ALT_PROJECT_ID,
        tenant_id=TENANT_ID,
        name="Android Stale Context Alternate Project",
        description="Alternate project used only to force PARCEL_PROJECT_MISMATCH in Android sync tests.",
        status="ACTIVE",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=180),
        crop_scope=["RICE", "SUGARCANE"],
        geography_scope={"note": "Android stale-context sync failure fixture only"},
        metadata={
            "source": "ANDROID_STALE_CONTEXT_TEST",
            "do_not_use_for_production": True,
        },
        is_active=True,
    )
    db.add(project)
    return "CREATED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply the parcel project mutation.")
    parser.add_argument("--restore", action="store_true", help="Restore the parcel to the original Android project.")
    args = parser.parse_args()

    dry_run = not args.apply
    target_project_id = PROJECT_ID if args.restore else ALT_PROJECT_ID

    db = SessionLocal()
    try:
        parcel = (
            db.query(Parcel)
            .filter(Parcel.id == PARCEL_ID, Parcel.tenant_id == TENANT_ID)
            .first()
        )
        if not parcel:
            raise RuntimeError(
                f"parcel {PARCEL_ID} not found for tenant {TENANT_ID}; do not run this test yet"
            )

        before_project_id = str(parcel.project_id) if parcel.project_id else None
        alt_project_status = ensure_alt_project(db, dry_run)

        if not dry_run:
            parcel.project_id = target_project_id
            db.commit()
            db.refresh(parcel)
        else:
            db.rollback()

        after_project_id = str(parcel.project_id) if not dry_run and parcel.project_id else str(target_project_id)

        mode = "RESTORE_APPLY" if args.restore and args.apply else "APPLY" if args.apply else "DRY_RUN"
        result = {
            "schema_version": "android_stale_context_sync_failure_prepare.v1",
            "mode": mode,
            "tenant_id": TENANT_ID,
            "farmer_id": str(FARMER_ID),
            "parcel_id": str(PARCEL_ID),
            "queued_payload_project_id_android_should_send": str(PROJECT_ID),
            "before": {"parcel_project_id": before_project_id},
            "after": {"parcel_project_id": after_project_id},
            "alternate_project": {
                "project_id": str(ALT_PROJECT_ID),
                "status": alt_project_status,
            },
            "expected_sync_failure": {
                "entity_type": "crop_cycle",
                "operation": "CREATE",
                "error_code": "MATERIALIZATION_FAILED",
                "detail_code": "PARCEL_PROJECT_MISMATCH",
                "message_contains": "project does not match parcel project",
                "conflict_row_expected": False,
            },
            "android_payload_notes": {
                "use_new_event_id": True,
                "use_new_entity_id": True,
                "dependency_ids": [],
                "payload_project_id_must_remain": str(PROJECT_ID),
                "payload_farmer_id": str(FARMER_ID),
                "payload_parcel_id": str(PARCEL_ID),
            },
            "restore_command": (
                "cd ~/projects/farmint/backend && "
                "../venv/bin/python scripts/prepare_android_stale_context_sync_failure.py --restore --apply"
            ),
        }
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
