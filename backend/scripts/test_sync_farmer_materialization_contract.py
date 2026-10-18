#!/usr/bin/env python3
"""Focused farmer sync field, retry, replay, and concurrency regression."""

from __future__ import annotations

import concurrent.futures
import sys
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Project, Tenant
from app.modules.master_data import models as _master_data_models  # noqa: F401
from app.modules.sync import service
from app.modules.sync.models import AuditChainEntry, SyncConflict, SyncProcessedEvent


RUN = uuid.uuid4()
TENANT_ID = f"sync-farmer-contract-{str(RUN)[:8]}"
PROJECT_ID = uuid.uuid4()
ACTOR_ID = uuid.uuid4()
NOW = datetime.now(timezone.utc)


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def mobile(offset: int) -> str:
    return f"+919{(RUN.int + offset) % 1_000_000_000:09d}"


def event(*, event_id: uuid.UUID, farmer_id: uuid.UUID, mobile_number: str, mode: str) -> dict:
    return {
        "event_id": str(event_id),
        "entity_type": "FARMER",
        "entity_id": str(farmer_id),
        "operation": "CREATE",
        "version": 1,
        "dependency_ids": [],
        "payload": {
            "user_id": str(ACTOR_ID),
            "mobile_number": mobile_number,
            "project_id": str(PROJECT_ID),
            "display_name": "Isolated farmer sync contract",
            "village_name_manual": "Isolated Test Village",
            "pin_code": "560001",
            "primary_crop_code": "RICE",
            "assistance_mode": mode,
        },
        "metadata": {"source": "isolated_farmer_sync_contract"},
    }


def process(item: dict):
    db = SessionLocal()
    try:
        return service.process_sync_batch(db, TENANT_ID, str(ACTOR_ID), [item])
    finally:
        db.close()


def result_shape(result) -> dict:
    return {
        "accepted_count": len(result.accepted),
        "failed": [
            {
                "error_code": row.get("error_code"),
                "detail_code": row.get("detail_code"),
            }
            for row in result.failed
        ],
        "conflict_types": [row.get("conflict_type") for row in result.conflicts],
    }


def setup() -> None:
    db = SessionLocal()
    try:
        db.add(Tenant(
            id=TENANT_ID,
            name="Isolated farmer sync contract",
            type="ENTERPRISE",
            config={},
            created_at=NOW,
            updated_at=NOW,
        ))
        db.add(Project(
            id=PROJECT_ID,
            tenant_id=TENANT_ID,
            name="Isolated farmer sync project",
            description="Temporary regression scope",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=1),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            created_at=NOW,
            updated_at=NOW,
        ))
        db.add(User(
            id=ACTOR_ID,
            mobile_number=mobile(0),
            role="FARMER",
            tenant_id=TENANT_ID,
            display_name="Isolated farmer sync actor",
            is_active=True,
            created_at=NOW,
            updated_at=NOW,
        ))
        db.commit()
    finally:
        db.close()


def cleanup() -> None:
    db = SessionLocal()
    try:
        db.query(SyncConflict).filter(SyncConflict.tenant_id == TENANT_ID).delete(
            synchronize_session=False
        )
        db.query(AuditChainEntry).filter(AuditChainEntry.tenant_id == TENANT_ID).delete(
            synchronize_session=False
        )
        db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.tenant_id == TENANT_ID
        ).delete(synchronize_session=False)
        db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == TENANT_ID
        ).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == TENANT_ID).delete(
            synchronize_session=False
        )
        db.query(Project).filter(Project.id == PROJECT_ID).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id == ACTOR_ID).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == TENANT_ID).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def assert_materialized(
    farmer_id: uuid.UUID,
    *,
    expected_method: str,
    expected_commits: int = 1,
) -> None:
    db = SessionLocal()
    try:
        farmer = db.query(Farmer).filter(
            Farmer.id == farmer_id,
            Farmer.tenant_id == TENANT_ID,
        ).one()
        enrollment = db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == TENANT_ID,
            FarmerProjectEnrollment.farmer_id == farmer_id,
            FarmerProjectEnrollment.project_id == PROJECT_ID,
        ).one()
        commits = db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == TENANT_ID,
            AuditChainEntry.entity_id == farmer_id,
            AuditChainEntry.action == "SYNC_COMMIT",
        ).count()
        check(farmer.pin_code == "560001", "farmer sync preserves PIN code")
        check(
            farmer.enrollment_method == expected_method,
            f"farmer enrollment method is {expected_method}",
        )
        check(
            enrollment.enrollment_method == expected_method,
            f"project enrollment method is {expected_method}",
        )
        check(enrollment.status == "ACTIVE", "project enrollment is active")
        check(commits == expected_commits, "farmer has one successful sync audit")
    finally:
        db.close()


def main() -> int:
    setup()
    original_materializer = service._materialize_farmer_event
    try:
        self_event_id = uuid.uuid4()
        self_farmer_id = uuid.uuid4()
        self_event = event(
            event_id=self_event_id,
            farmer_id=self_farmer_id,
            mobile_number=mobile(1),
            mode="SELF_SERVICE",
        )
        first = process(self_event)
        print({"self_service_result": result_shape(first)})
        check(first.accepted == [str(self_event_id)], "self-service farmer sync is accepted")
        check(not first.failed and not first.conflicts, "self-service farmer sync is clean")
        assert_materialized(self_farmer_id, expected_method="SELF")

        replay = process(self_event)
        check(replay.accepted == [str(self_event_id)], "committed replay is accepted idempotently")
        check(not replay.failed and not replay.conflicts, "committed replay has no failure")
        assert_materialized(self_farmer_id, expected_method="SELF")

        assisted_event_id = uuid.uuid4()
        assisted_farmer_id = uuid.uuid4()
        assisted = process(event(
            event_id=assisted_event_id,
            farmer_id=assisted_farmer_id,
            mobile_number=mobile(2),
            mode="FIELD_AGENT_ASSISTED",
        ))
        check(assisted.accepted == [str(assisted_event_id)], "assisted farmer sync is accepted")
        assert_materialized(assisted_farmer_id, expected_method="ASSISTED")

        recovery_event_id = uuid.uuid4()
        recovery_farmer_id = uuid.uuid4()
        recovery_event = event(
            event_id=recovery_event_id,
            farmer_id=recovery_farmer_id,
            mobile_number=mobile(3),
            mode="SELF_SERVICE",
        )

        def fail_once(*args, **kwargs):
            raise ValueError("synthetic isolated materialization failure")

        service._materialize_farmer_event = fail_once
        failed = process(recovery_event)
        check(not failed.accepted and len(failed.failed) == 1, "failed materialization is reported")
        service._materialize_farmer_event = original_materializer
        recovered = process(recovery_event)
        check(recovered.accepted == [str(recovery_event_id)], "failed event safely retries with same ID")
        assert_materialized(recovery_farmer_id, expected_method="SELF")

        concurrent_event_id = uuid.uuid4()
        concurrent_farmer_id = uuid.uuid4()
        concurrent_event = event(
            event_id=concurrent_event_id,
            farmer_id=concurrent_farmer_id,
            mobile_number=mobile(4),
            mode="SELF_SERVICE",
        )
        barrier = threading.Barrier(2)

        def concurrent_process():
            barrier.wait(timeout=10)
            return process(concurrent_event)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: concurrent_process(), range(2)))
        check(
            all(result.accepted == [str(concurrent_event_id)] for result in results),
            "concurrent same-event requests return accepted",
        )
        check(
            all(not result.failed and not result.conflicts for result in results),
            "concurrent same-event requests avoid failure and conflict",
        )
        assert_materialized(concurrent_farmer_id, expected_method="SELF")

        ordered_event_ids = [uuid.uuid4(), uuid.uuid4()]
        ordered_farmer_ids = [uuid.uuid4(), uuid.uuid4()]
        ordered_events = [
            event(
                event_id=event_id,
                farmer_id=farmer_id,
                mobile_number=mobile(5 + index),
                mode="SELF_SERVICE",
            )
            for index, (event_id, farmer_id) in enumerate(
                zip(ordered_event_ids, ordered_farmer_ids)
            )
        ]
        db = SessionLocal()
        try:
            ordered = service.process_sync_batch(
                db,
                TENANT_ID,
                str(ACTOR_ID),
                ordered_events,
            )
        finally:
            db.close()
        check(
            ordered.accepted == [str(event_id) for event_id in ordered_event_ids],
            "distinct sync events retain input acceptance order",
        )
        for farmer_id in ordered_farmer_ids:
            assert_materialized(farmer_id, expected_method="SELF")

        duplicate_event_id = uuid.uuid4()
        duplicate_farmer_id = uuid.uuid4()
        duplicate_event = event(
            event_id=duplicate_event_id,
            farmer_id=duplicate_farmer_id,
            mobile_number=mobile(7),
            mode="SELF_SERVICE",
        )
        db = SessionLocal()
        try:
            duplicate = service.process_sync_batch(
                db,
                TENANT_ID,
                str(ACTOR_ID),
                [duplicate_event, duplicate_event],
            )
        finally:
            db.close()
        check(
            duplicate.accepted == [str(duplicate_event_id), str(duplicate_event_id)],
            "same-batch duplicate retains idempotent response shape",
        )
        check(not duplicate.failed, "same-batch duplicate has no failure")
        assert_materialized(duplicate_farmer_id, expected_method="SELF")

        db = SessionLocal()
        try:
            row = db.query(SyncProcessedEvent).filter(
                SyncProcessedEvent.event_id == concurrent_event_id,
                SyncProcessedEvent.tenant_id == TENANT_ID,
            ).one()
            failures = db.query(AuditChainEntry).filter(
                AuditChainEntry.tenant_id == TENANT_ID,
                AuditChainEntry.entity_id == concurrent_farmer_id,
                AuditChainEntry.action == "SYNC_FAILED",
            ).count()
            check(row.status == "COMMITTED", "concurrent event finishes committed")
            check(failures == 0, "concurrent event creates no failed audit")
            check(
                db.query(Farmer).filter(Farmer.id == concurrent_farmer_id).count() == 1,
                "concurrent event creates one farmer",
            )
            check(
                db.query(FarmerProjectEnrollment).filter(
                    FarmerProjectEnrollment.farmer_id == concurrent_farmer_id
                ).count() == 1,
                "concurrent event creates one enrollment",
            )
        finally:
            db.close()
    finally:
        service._materialize_farmer_event = original_materializer
        cleanup()

    print("SYNC FARMER MATERIALIZATION CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
