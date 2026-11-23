#!/usr/bin/env python3
"""Focused queued crop-activity CREATE regression proposal.

Destructive to the deterministic crop-cycle fixture.  Run only against the
same separately approved disposable PostgreSQL target required by the direct
activity regression.  Source review is required before execution.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from scripts import test_android_crop_cycle_activity_logging_flow as base

    from app.modules.sync import service as sync_service
    from app.modules.workflow import api as workflow_api
    from app.modules.workflow import activity_create_service
    from app.modules.sync.models import (
        AuditChainEntry,
        CropActivityCommandBinding,
        CropActivitySyncEventBinding,
        SyncProcessedEvent,
    )
    from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance
    from fastapi import HTTPException
except BaseException as exc:
    print(f"QUEUED_ACTIVITY_BOOTSTRAP_FAILURE:{type(exc).__name__}")
    raise SystemExit(1)


SYNTHETIC_LEDGER_IDS: set[uuid.UUID] = set()


def check(condition, label: str) -> None:
    if not condition:
        raise AssertionError(f"QUEUED_ACTIVITY_CHECK_FAILED:{label}")
    print(f"PASS {label}")


def queued_event(
    *,
    event_id: uuid.UUID,
    activity_id: uuid.UUID,
    cycle_id: str,
    stage_id: str,
    stage_code: str,
    cost: str = "25.00",
    entity_type: str = "crop_activity",
    dependency_ids: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    payload = base.activity_payload(activity_id, stage_id, stage_code)
    payload.update({
        "farmer_id": str(base.FARMER_ID),
        "crop_cycle_id": cycle_id,
        "cost_amount": cost,
    })
    return {
        "event_id": str(event_id),
        "entity_type": entity_type,
        "entity_id": str(activity_id),
        "operation": "CREATE",
        "payload": payload,
        "version": 1,
        "dependency_ids": dependency_ids or [],
        "metadata": metadata or {},
    }


def post_event(event: dict, test_client=None):
    active_client = test_client or base.client
    return active_client.post(
        "/api/v1/sync/events",
        content=json.dumps(
            {"events": [event]},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
        headers={**base.HEADERS, "Content-Type": "application/json"},
    )


def post_batch(events: list[dict], test_client=None):
    active_client = test_client or base.client
    return active_client.post(
        "/api/v1/sync/events",
        content=json.dumps(
            {"events": events},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
        headers={**base.HEADERS, "Content-Type": "application/json"},
    )


def response_failure_code(response) -> str | None:
    try:
        failed = response.json().get("failed") or []
    except (AttributeError, TypeError, ValueError):
        return None
    return failed[0].get("error_code") if len(failed) == 1 else None


def assert_single_correlated_detail(body: dict, event: dict, outcome: str, label: str) -> None:
    check(body["accepted"] == [event["event_id"]], f"{label} accepted event ID")
    check(body["failed"] == [], f"{label} has no failure")
    check(len(body["accepted_details"]) == 1, f"{label} detail cardinality")
    detail = body["accepted_details"][0]
    check(detail["event_id"] == event["event_id"], f"{label} detail event ID")
    check(detail["entity_type"] == event["entity_type"], f"{label} detail entity type")
    check(detail["entity_id"] == event["entity_id"], f"{label} detail entity ID")
    check(detail["activity_id"] == event["entity_id"], f"{label} detail activity ID")
    check(detail["outcome"] == outcome, f"{label} detail outcome")


def expected_lossless_envelope(event: dict) -> str:
    def tagged(value):
        if value is None:
            return ["null"]
        if isinstance(value, bool):
            return ["boolean", value]
        if isinstance(value, int):
            return ["number", str(value), str(value)]
        if isinstance(value, str):
            return ["string", value]
        if isinstance(value, list):
            return ["array", [tagged(item) for item in value]]
        if isinstance(value, dict):
            return ["object", [[key, tagged(value[key])] for key in sorted(value)]]
        raise AssertionError("QUEUED_ACTIVITY_CHECK_FAILED:unsupported expected scalar")

    return json.dumps(
        ["sync_envelope.v1", tagged(event)],
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def expected_queued_canonical(cycle_id: str, event: dict) -> str:
    expected = json.loads(base.expected_canonical_text(cycle_id, event["payload"]))
    expected.update({
        "origin_kind": "SYNC",
        "event_id": event["event_id"],
        "entity_type": event["entity_type"],
        "operation": "CREATE",
        "client_version": event["version"],
        "dependency_ids": event["dependency_ids"],
        "sync_envelope_canonical": expected_lossless_envelope(event),
        "cost_amount": str(Decimal(event["payload"]["cost_amount"]).normalize()),
    })
    return json.dumps(
        expected,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def complete_row_snapshot(row) -> dict:
    def stable(value):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (dict, list)):
            return json.loads(json.dumps(value, sort_keys=True, default=str))
        return value

    return {
        column.name: stable(getattr(row, column.name))
        for column in row.__table__.columns
    }


def cycle_total(cycle_id: str) -> Decimal:
    db = base.SessionLocal()
    try:
        return Decimal(str(db.query(CropCycle.total_input_cost).filter(
            CropCycle.id == uuid.UUID(cycle_id)
        ).scalar() or 0))
    finally:
        db.close()


def assert_no_activity_effects(event: dict, baseline: Decimal, label: str) -> None:
    activity_id = uuid.UUID(event["entity_id"])
    event_id = uuid.UUID(event["event_id"])
    db = base.SessionLocal()
    try:
        check(db.query(CropActivity).filter(CropActivity.id == activity_id).count() == 0, f"{label} has no activity")
        check(db.query(CropActivityCommandBinding).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 0, f"{label} has no command binding")
        check(db.query(CropActivitySyncEventBinding).filter(CropActivitySyncEventBinding.event_id == event_id).count() == 0, f"{label} has no event binding")
        check(db.query(SyncProcessedEvent).filter(SyncProcessedEvent.event_id == event_id).count() == 0, f"{label} has no ledger")
        check(db.query(AuditChainEntry).filter(AuditChainEntry.entity_id == activity_id).count() == 0, f"{label} has no audit")
        current = Decimal(str(db.query(CropCycle.total_input_cost).filter(
            CropCycle.id == uuid.UUID(event["payload"]["crop_cycle_id"])
        ).scalar() or 0))
        check(current == baseline, f"{label} has no economics")
    finally:
        db.close()


def assert_committed_event(event: dict, label: str) -> None:
    activity_id = uuid.UUID(event["entity_id"])
    event_id = uuid.UUID(event["event_id"])
    db = base.SessionLocal()
    try:
        activity = db.query(CropActivity).filter(CropActivity.id == activity_id).one()
        check(activity.cost_amount == Decimal(event["payload"]["cost_amount"]), f"{label} stored cost")
        check(db.query(CropActivityCommandBinding).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 1, f"{label} one command binding")
        check(db.query(CropActivitySyncEventBinding).filter(
            CropActivitySyncEventBinding.event_id == event_id,
            CropActivitySyncEventBinding.activity_id == activity_id,
        ).count() == 1, f"{label} one event binding")
        check(db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == event_id,
            SyncProcessedEvent.entity_id == activity_id,
            SyncProcessedEvent.status == "COMMITTED",
        ).count() == 1, f"{label} one committed ledger")
        check(db.query(AuditChainEntry).filter(
            AuditChainEntry.entity_id == activity_id,
            AuditChainEntry.action == "ACTIVITY_LOGGED",
        ).count() == 1, f"{label} one business audit")
        check(db.query(AuditChainEntry).filter(
            AuditChainEntry.entity_id == activity_id,
            AuditChainEntry.action == "SYNC_COMMIT",
        ).count() == 1, f"{label} one operational audit")
    finally:
        db.close()


def cleanup_synthetic_ledgers() -> None:
    if not SYNTHETIC_LEDGER_IDS:
        return
    db = base.SessionLocal()
    try:
        referenced = {
            row[0]
            for row in db.query(CropActivitySyncEventBinding.event_id).filter(
                CropActivitySyncEventBinding.event_id.in_(SYNTHETIC_LEDGER_IDS)
            ).all()
        }
        removable = SYNTHETIC_LEDGER_IDS - referenced
        if removable:
            db.query(SyncProcessedEvent).filter(
                SyncProcessedEvent.event_id.in_(removable)
            ).delete(synchronize_session=False)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def assert_first_commit_and_replay(
    cycle_id: str,
    stage_id: str,
    stage_code: str,
) -> tuple[dict, Decimal]:
    event_id = uuid.uuid4()
    activity_id = uuid.uuid4()
    dependency_id = uuid.uuid4()
    SYNTHETIC_LEDGER_IDS.add(dependency_id)
    dependency_db = base.SessionLocal()
    try:
        dependency_db.add(SyncProcessedEvent(
            event_id=dependency_id,
            tenant_id=base.TENANT_ID,
            actor_id=uuid.UUID(base.HEADERS["X-Actor-ID"]),
            entity_type="farmer",
            entity_id=base.FARMER_ID,
            operation="CREATE",
            server_version=1,
            status="COMMITTED",
        ))
        dependency_db.commit()
    finally:
        dependency_db.close()
    event = queued_event(
        event_id=event_id,
        activity_id=activity_id,
        cycle_id=cycle_id,
        stage_id=stage_id,
        stage_code=stage_code,
        dependency_ids=[str(dependency_id)],
    )
    db = base.SessionLocal()
    try:
        before_total = Decimal(str(db.query(CropCycle.total_input_cost).filter(
            CropCycle.id == uuid.UUID(cycle_id)
        ).scalar() or 0))
    finally:
        db.close()
    expected_total = before_total + Decimal(event["payload"]["cost_amount"])
    expected_canonical = expected_queued_canonical(cycle_id, event)
    expected_digest = __import__("hashlib").sha256(
        expected_canonical.encode("utf-8")
    ).hexdigest()
    first = post_event(event)
    check(first.status_code == 200, "queued first request returns 200")
    body = first.json()
    check(body["accepted"] == [str(event_id)], "queued first event accepted")
    check(body["failed"] == [], "queued first event has no failure")
    check(len(body["accepted_details"]) == 1, "queued first detail cardinality")
    detail = body["accepted_details"][0]
    check(set(detail) == {
        "event_id", "entity_type", "entity_id", "activity_id", "outcome",
        "intent_version", "intent_sha256",
    }, "detail field set")
    check(detail["event_id"] == str(event_id), "detail event identity")
    check(detail["entity_type"] == event["entity_type"], "detail entity spelling")
    check(detail["entity_id"] == str(activity_id), "detail entity identity")
    check(detail["activity_id"] == str(activity_id), "detail activity identity")
    check(detail["outcome"] == "COMMITTED", "detail committed outcome")
    check(detail["intent_version"] == "crop_activity_intent.v1", "detail intent version")
    check(detail["intent_sha256"] == expected_digest, "detail independent intent digest")

    db = base.SessionLocal()
    try:
        activity = db.query(CropActivity).filter(CropActivity.id == activity_id).one()
        command = db.query(CropActivityCommandBinding).filter(
            CropActivityCommandBinding.activity_id == activity_id
        ).one()
        event_binding = db.query(CropActivitySyncEventBinding).filter(
            CropActivitySyncEventBinding.event_id == event_id
        ).one()
        processed = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == event_id
        ).one()
        business_audit = db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == base.TENANT_ID,
            AuditChainEntry.entity_id == activity_id,
            AuditChainEntry.action == "ACTIVITY_LOGGED",
        ).one()
        operational_audit = db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == base.TENANT_ID,
            AuditChainEntry.entity_id == activity_id,
            AuditChainEntry.action == "SYNC_COMMIT",
        ).one()
        check(command.origin_kind == "SYNC", "command records sync origin")
        check(command.origin_event_id == event_id, "command binds event identity")
        check(command.intent_canonical == expected_canonical, "complete canonical intent retained")
        check(command.intent_sha256 == expected_digest, "independent digest retained")
        check(event_binding.activity_id == activity_id, "event binding activity identity")
        check(event_binding.intent_canonical == command.intent_canonical, "binding canonical agreement")
        check(processed.status == "COMMITTED", "processed event committed")
        check(processed.entity_id == activity_id, "processed event activity identity")
        check(str(business_audit.correlation_id) == str(command.audit_correlation_id), "business audit correlation matches binding")
        check(operational_audit.correlation_id != command.audit_correlation_id, "operational audit has separate correlation")
        check(command.result_version == "crop_activity_result.v1", "fixed result version retained")
        expected_snapshot = base.expected_snapshot(activity, cycle_id, event["payload"])
        expected_snapshot["cost_amount"] = str(Decimal(event["payload"]["cost_amount"]).quantize(Decimal("0.01")))
        expected_response = {
            "activity_id": str(activity_id),
            "activity_type": "LABOR",
            "input_rule_id": None,
            "product_code": None,
            "package_sku": None,
            "stage_code": stage_code,
            "cycle_total_input_cost": str(expected_total),
            "events_published": ["crop_activity_logged.v1"],
        }
        expected_result = {
            "response": expected_response,
            "persisted_activity": expected_snapshot,
            "cycle_total_input_cost": str(expected_total),
            "audit_correlation_id": str(command.audit_correlation_id),
        }
        check(command.result_payload == expected_result, "complete retained result independently matches")
        check(body["accepted_details"][0] == detail, "single correlated detail is stable")
        retained_total = expected_total
        before_replay_state = {
            "activity": complete_row_snapshot(activity),
            "command": complete_row_snapshot(command),
            "event_binding": complete_row_snapshot(event_binding),
            "processed": complete_row_snapshot(processed),
            "business_audit": complete_row_snapshot(business_audit),
            "operational_audit": complete_row_snapshot(operational_audit),
        }
    finally:
        db.close()

    dependency_db = base.SessionLocal()
    try:
        deleted = dependency_db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == dependency_id
        ).delete(synchronize_session=False)
        check(deleted == 1, "historical dependency removed before replay")
        dependency_db.commit()
    finally:
        dependency_db.close()

    replay = post_event(event)
    check(replay.status_code == 200, "queued exact replay returns 200")
    replay_body = replay.json()
    check(replay_body["accepted"] == [str(event_id)], "queued replay accepted")
    check(replay_body["accepted_details"][0]["outcome"] == "EXACT_REPLAY", "queued replay outcome")
    check(replay_body["accepted_details"][0]["intent_sha256"] == detail["intent_sha256"], "queued replay digest")

    db = base.SessionLocal()
    try:
        check(db.query(CropActivity).filter(CropActivity.id == activity_id).count() == 1, "replay keeps one activity")
        check(db.query(CropActivityCommandBinding).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 1, "replay keeps one command binding")
        check(db.query(CropActivitySyncEventBinding).filter(CropActivitySyncEventBinding.event_id == event_id).count() == 1, "replay keeps one event binding")
        check(db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == base.TENANT_ID,
            AuditChainEntry.entity_id == activity_id,
            AuditChainEntry.action == "ACTIVITY_LOGGED",
        ).count() == 1, "replay adds no business audit")
        check(db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == base.TENANT_ID,
            AuditChainEntry.entity_id == activity_id,
            AuditChainEntry.action == "SYNC_COMMIT",
        ).count() == 1, "replay adds no operational audit")
        current_total = Decimal(str(db.query(CropCycle.total_input_cost).filter(
            CropCycle.id == uuid.UUID(cycle_id)
        ).scalar() or 0))
        check(current_total == retained_total, "replay adds no economics")
        command_after = db.query(CropActivityCommandBinding).filter(
            CropActivityCommandBinding.activity_id == activity_id
        ).one()
        event_after = db.query(CropActivitySyncEventBinding).filter(
            CropActivitySyncEventBinding.event_id == event_id
        ).one()
        processed_after = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == event_id
        ).one()
        activity_after = db.query(CropActivity).filter(CropActivity.id == activity_id).one()
        business_after = db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == base.TENANT_ID,
            AuditChainEntry.entity_id == activity_id,
            AuditChainEntry.action == "ACTIVITY_LOGGED",
        ).one()
        operational_after = db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == base.TENANT_ID,
            AuditChainEntry.entity_id == activity_id,
            AuditChainEntry.action == "SYNC_COMMIT",
        ).one()
        after_replay_state = {
            "activity": complete_row_snapshot(activity_after),
            "command": complete_row_snapshot(command_after),
            "event_binding": complete_row_snapshot(event_after),
            "processed": complete_row_snapshot(processed_after),
            "business_audit": complete_row_snapshot(business_after),
            "operational_audit": complete_row_snapshot(operational_after),
        }
        check(after_replay_state == before_replay_state, "replay preserves complete retained state")
    finally:
        db.close()
    return event, retained_total


def assert_conflicting_replays(event: dict) -> None:
    changed = json.loads(json.dumps(event))
    changed["metadata"] = {"unicode": "e\u0301"}
    response = post_event(changed)
    check(response.status_code == 200, "changed envelope returns batch response")
    check(response.json()["accepted"] == [], "changed envelope not accepted")
    check(response_failure_code(response) in {"ACTIVITY_ID_REUSE", "EVENT_ID_REUSE"}, "changed envelope rejects identity")

    adopted = json.loads(json.dumps(event))
    adopted["event_id"] = str(uuid.uuid4())
    adopted["dependency_ids"] = []
    response = post_event(adopted)
    check(response.status_code == 200, "different event returns batch response")
    check(response.json()["accepted"] == [], "different event cannot adopt activity")
    check(response_failure_code(response) == "ACTIVITY_ID_REUSE", "different event rejects activity identity")


def assert_command_binding_only_rejects(
    cycle_id: str,
    stage_id: str,
    stage_code: str,
) -> None:
    existing_id = uuid.uuid4()
    direct_payload = base.activity_payload(existing_id, stage_id, stage_code)
    direct = base.client.post(
        f"/api/v1/crop-cycles/{cycle_id}/activities",
        json=direct_payload,
        headers=base.HEADERS,
    )
    check(direct.status_code == 201, "command-only fixture direct activity commits")
    occupied_event_id = uuid.uuid4()
    db = base.SessionLocal()
    try:
        binding = db.query(CropActivityCommandBinding).filter(
            CropActivityCommandBinding.activity_id == existing_id
        ).one()
        binding.origin_kind = "SYNC"
        binding.origin_event_id = occupied_event_id
        db.commit()
    finally:
        db.close()

    new_activity_id = uuid.uuid4()
    response = post_event(queued_event(
        event_id=occupied_event_id,
        activity_id=new_activity_id,
        cycle_id=cycle_id,
        stage_id=stage_id,
        stage_code=stage_code,
    ))
    check(response.status_code == 200, "command-only occupation returns batch response")
    check(response_failure_code(response) == "EVENT_ID_REUSE", "command-only occupation rejects")
    db = base.SessionLocal()
    try:
        check(db.query(CropActivity).filter(CropActivity.id == new_activity_id).count() == 0, "command-only rejection creates no activity")
        check(db.query(SyncProcessedEvent).filter(SyncProcessedEvent.event_id == occupied_event_id).count() == 0, "command-only rejection creates no ledger")
    finally:
        db.close()


def assert_additional_identity_states(
    cycle_id: str,
    stage_id: str,
    stage_code: str,
    committed_event: dict,
) -> None:
    processed_only = uuid.uuid4()
    SYNTHETIC_LEDGER_IDS.add(processed_only)
    db = base.SessionLocal()
    try:
        db.add(SyncProcessedEvent(
            event_id=processed_only,
            tenant_id=base.TENANT_ID,
            actor_id=uuid.UUID(base.HEADERS["X-Actor-ID"]),
            entity_type="crop_activity",
            entity_id=uuid.uuid4(),
            operation="CREATE",
            server_version=1,
            status="COMMITTED",
        ))
        db.commit()
    finally:
        db.close()
    candidate = uuid.uuid4()
    response = post_event(queued_event(
        event_id=processed_only, activity_id=candidate, cycle_id=cycle_id,
        stage_id=stage_id, stage_code=stage_code,
    ))
    check(response_failure_code(response) == "EVENT_ID_REUSE", "processed-only occupation rejects")
    db = base.SessionLocal()
    try:
        check(db.query(CropActivity).filter(CropActivity.id == candidate).count() == 0, "processed-only rejection has no activity")
    finally:
        db.close()


def assert_partial_and_mismatch_states(
    cycle_id: str,
    stage_id: str,
    stage_code: str,
    committed_event: dict,
) -> None:
    def direct_binding_for(event_id: uuid.UUID) -> uuid.UUID:
        activity_id = uuid.uuid4()
        response = base.client.post(
            f"/api/v1/crop-cycles/{cycle_id}/activities",
            json=base.activity_payload(activity_id, stage_id, stage_code),
            headers=base.HEADERS,
        )
        check(response.status_code == 201, "partial-state direct fixture commits")
        db = base.SessionLocal()
        try:
            binding = db.query(CropActivityCommandBinding).filter(
                CropActivityCommandBinding.activity_id == activity_id
            ).one()
            binding.origin_kind = "SYNC"
            binding.origin_event_id = event_id
            db.commit()
        finally:
            db.close()
        return activity_id

    partial_event = uuid.uuid4()
    SYNTHETIC_LEDGER_IDS.add(partial_event)
    direct_binding_for(partial_event)
    db = base.SessionLocal()
    try:
        db.add(SyncProcessedEvent(
            event_id=partial_event,
            tenant_id=base.TENANT_ID,
            actor_id=uuid.UUID(base.HEADERS["X-Actor-ID"]),
            entity_type="crop_activity",
            entity_id=uuid.uuid4(),
            operation="CREATE",
            server_version=1,
            status="COMMITTED",
        ))
        db.commit()
    finally:
        db.close()
    candidate = uuid.uuid4()
    response = post_event(queued_event(
        event_id=partial_event, activity_id=candidate, cycle_id=cycle_id,
        stage_id=stage_id, stage_code=stage_code,
    ))
    check(response_failure_code(response) == "EVENT_ID_REUSE", "processed-plus-command partial state rejects")
    db = base.SessionLocal()
    try:
        check(db.query(CropActivity).filter(CropActivity.id == candidate).count() == 0, "partial state creates no activity")
    finally:
        db.close()

    duplicate_event = uuid.uuid4()
    direct_binding_for(duplicate_event)
    direct_binding_for(duplicate_event)
    candidate = uuid.uuid4()
    response = post_event(queued_event(
        event_id=duplicate_event, activity_id=candidate, cycle_id=cycle_id,
        stage_id=stage_id, stage_code=stage_code,
    ))
    check(response_failure_code(response) == "EVENT_ID_REUSE", "duplicate command bindings reject")
    db = base.SessionLocal()
    try:
        check(db.query(CropActivity).filter(CropActivity.id == candidate).count() == 0, "duplicate binding rejection creates no activity")
    finally:
        db.close()

    cross_tenant_event = uuid.uuid4()
    SYNTHETIC_LEDGER_IDS.add(cross_tenant_event)
    db = base.SessionLocal()
    try:
        db.add(SyncProcessedEvent(
            event_id=cross_tenant_event,
            tenant_id="other-tenant",
            actor_id=uuid.uuid4(),
            entity_type="crop_activity",
            entity_id=uuid.uuid4(),
            operation="CREATE",
            server_version=1,
            status="COMMITTED",
        ))
        db.commit()
    finally:
        db.close()
    response = post_event(queued_event(
        event_id=cross_tenant_event, activity_id=uuid.uuid4(), cycle_id=cycle_id,
        stage_id=stage_id, stage_code=stage_code,
    ))
    check(response_failure_code(response) == "EVENT_ID_REUSE", "cross-tenant event collision is nondisclosing")
    cross_failure = response.json()["failed"][0]
    check(cross_failure["message"] == "Sync event identity is unavailable.", "cross-tenant collision uses fixed message")
    check("other-tenant" not in json.dumps(cross_failure), "cross-tenant collision hides tenant")

    committed_id = uuid.UUID(committed_event["event_id"])
    alternate_activity_id = direct_binding_for(uuid.uuid4())
    mismatch_cases = (
        (SyncProcessedEvent, "tenant_id", "wrong-tenant"),
        (SyncProcessedEvent, "actor_id", uuid.uuid4()),
        (SyncProcessedEvent, "entity_type", "cropactivity"),
        (SyncProcessedEvent, "entity_id", uuid.uuid4()),
        (SyncProcessedEvent, "operation", "UPDATE"),
        (SyncProcessedEvent, "server_version", 2),
        (CropActivitySyncEventBinding, "tenant_id", "wrong-tenant"),
        (CropActivitySyncEventBinding, "actor_id", uuid.uuid4()),
        (CropActivitySyncEventBinding, "activity_id", alternate_activity_id),
        (CropActivitySyncEventBinding, "intent_version", "wrong.v1"),
        (CropActivitySyncEventBinding, "intent_canonical", "{}"),
        (CropActivitySyncEventBinding, "intent_sha256", "0" * 64),
        (CropActivityCommandBinding, "tenant_id", "wrong-tenant"),
        (CropActivityCommandBinding, "actor_id", uuid.uuid4()),
        (CropActivityCommandBinding, "farmer_id", uuid.uuid4()),
        (CropActivityCommandBinding, "crop_cycle_id", uuid.uuid4()),
        (CropActivityCommandBinding, "intent_version", "wrong.v1"),
        (CropActivityCommandBinding, "intent_canonical", "{}"),
        (CropActivityCommandBinding, "intent_sha256", "0" * 64),
        (CropActivityCommandBinding, "origin_event_id", uuid.uuid4()),
    )
    for model, field, changed in mismatch_cases:
        db = base.SessionLocal()
        try:
            if model is SyncProcessedEvent:
                row = db.query(model).filter(model.event_id == committed_id).one()
            elif model is CropActivitySyncEventBinding:
                row = db.query(model).filter(model.event_id == committed_id).one()
            else:
                row = db.query(model).filter(
                    model.activity_id == uuid.UUID(committed_event["entity_id"])
                ).one()
            original = getattr(row, field)
            setattr(row, field, changed)
            db.commit()
        finally:
            db.close()
        try:
            response = post_event(committed_event)
            check(response_failure_code(response) == "EVENT_ID_REUSE", f"retained mismatch rejects {model.__name__}.{field}")
        finally:
            db = base.SessionLocal()
            try:
                if model is SyncProcessedEvent:
                    row = db.query(model).filter(model.event_id == committed_id).one()
                elif model is CropActivitySyncEventBinding:
                    row = db.query(model).filter(model.event_id == committed_id).one()
                else:
                    row = db.query(model).filter(
                        model.activity_id == uuid.UUID(committed_event["entity_id"])
                    ).one()
                setattr(row, field, original)
                db.commit()
            finally:
                db.close()
        restored = post_event(committed_event)
        check(restored.json()["accepted_details"][0]["outcome"] == "EXACT_REPLAY", f"retained mismatch restoration replays {model.__name__}.{field}")


def assert_queued_policy_boundaries(
    cycle_id: str,
    stage_id: str,
    stage_code: str,
    committed_event: dict,
) -> None:
    legacy_called = {"value": False}
    original_legacy = sync_service._materialize_crop_activity_event

    def forbidden_legacy(*args, **kwargs):
        legacy_called["value"] = True
        raise AssertionError("legacy materializer called")

    sync_service._materialize_crop_activity_event = forbidden_legacy
    try:
        event = queued_event(
            event_id=uuid.uuid4(), activity_id=uuid.uuid4(), cycle_id=cycle_id,
            stage_id=stage_id, stage_code=stage_code, cost="17.00",
        )
        response = post_event(event)
    finally:
        sync_service._materialize_crop_activity_event = original_legacy
    check(response.json()["accepted"] == [event["event_id"]], "queued CREATE bypasses legacy materializer")
    check(not legacy_called["value"], "legacy activity materializer was not called")

    suffix = uuid.uuid4().hex[:10].upper()
    db = base.SessionLocal()
    try:
        canonical_input = db.query(base.AgriculturalInput).filter(
            base.AgriculturalInput.is_active == True,
            base.AgriculturalInput.catalog_status == "PUBLISHED",
        ).first()
        check(canonical_input is not None, "queued traceability canonical input exists")
        manufacturer = base.Manufacturer(
            id=uuid.uuid4(), code=f"QUEUED_{suffix}",
            canonical_name="Queued activity regression manufacturer",
            country="India", aliases=[],
        )
        first_product = base.AgriculturalProduct(
            id=uuid.uuid4(), code=f"QUEUED_PRODUCT_{suffix}_A",
            canonical_input_id=canonical_input.id,
            manufacturer_id=manufacturer.id,
            brand_name="Queued activity product A", status="ACTIVE",
        )
        second_product = base.AgriculturalProduct(
            id=uuid.uuid4(), code=f"QUEUED_PRODUCT_{suffix}_B",
            canonical_input_id=canonical_input.id,
            manufacturer_id=manufacturer.id,
            brand_name="Queued activity product B", status="ACTIVE",
        )
        first_package = base.AgriculturalProductPackage(
            id=uuid.uuid4(), product_id=first_product.id,
            sku=f"QUEUED_PACKAGE_{suffix}_A", quantity=Decimal("1"),
            unit="KG", pack_label="1 kg queued package A", status="ACTIVE",
        )
        second_package = base.AgriculturalProductPackage(
            id=uuid.uuid4(), product_id=second_product.id,
            sku=f"QUEUED_PACKAGE_{suffix}_B", quantity=Decimal("1"),
            unit="KG", pack_label="1 kg queued package B", status="ACTIVE",
        )
        disabled = base.ProjectProductApproval(
            id=uuid.uuid4(), tenant_id=base.TENANT_ID,
            project_id=base.PROJECT_ID, product_id=first_product.id,
            enabled=False, preferred=False, display_order=1,
            reason="Queued package-only denial",
        )
        db.add(manufacturer)
        db.flush()
        db.add_all([first_product, second_product])
        db.flush()
        db.add_all([first_package, second_package, disabled])
        db.commit()
        selectors = (
            ("package-only disabled product", {"package_id": str(first_package.id)}),
            ("contradictory product selectors", {
                "product_id": str(first_product.id),
                "product_code": second_product.code,
            }),
            ("contradictory package selectors", {
                "package_id": str(first_package.id),
                "package_sku": second_package.sku,
            }),
        )
    finally:
        db.close()
    for label, selected in selectors:
        trace_baseline = cycle_total(cycle_id)
        trace_event = queued_event(
            event_id=uuid.uuid4(), activity_id=uuid.uuid4(), cycle_id=cycle_id,
            stage_id=stage_id, stage_code=stage_code,
        )
        trace_event["payload"].update({
            "activity_type": "FERTILIZER",
            "input_name": label,
            **selected,
        })
        response = post_event(trace_event)
        check(response_failure_code(response) == "ACTIVITY_TRACEABILITY_INVALID", f"queued {label} rejects")
        assert_no_activity_effects(trace_event, trace_baseline, f"queued {label}")

    auth_event = queued_event(
        event_id=uuid.uuid4(), activity_id=uuid.uuid4(), cycle_id=cycle_id,
        stage_id=stage_id, stage_code=stage_code,
    )
    auth_baseline = cycle_total(cycle_id)
    entered = __import__("threading").Event()
    release = __import__("threading").Event()
    original_authorize = workflow_api._require_principal_can_operate_cycle_farmer

    def revoked(*args, **kwargs):
        entered.set()
        if not release.wait(timeout=10):
            raise RuntimeError("authorization test timeout")
        raise HTTPException(403, "revoked")

    workflow_api._require_principal_can_operate_cycle_farmer = revoked
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(post_event, auth_event)
    try:
        check(entered.wait(timeout=10), "queued reauthorization boundary reached")
        release.set()
        response = future.result(timeout=30)
    finally:
        release.set()
        workflow_api._require_principal_can_operate_cycle_farmer = original_authorize
        pool.shutdown(wait=False, cancel_futures=True)
    check(response_failure_code(response) == "ACTIVITY_AUTHORIZATION_DENIED", "queued authorization revocation rejects")
    assert_no_activity_effects(auth_event, auth_baseline, "authorization revocation")

    stage_event = queued_event(
        event_id=uuid.uuid4(), activity_id=uuid.uuid4(), cycle_id=cycle_id,
        stage_id=stage_id, stage_code=stage_code,
    )
    stage_baseline = cycle_total(cycle_id)
    entered = __import__("threading").Event()
    release = __import__("threading").Event()
    original_resolve = activity_create_service._resolve_active_stage

    def delayed_resolve(*args, **kwargs):
        entered.set()
        if not release.wait(timeout=10):
            raise RuntimeError("stage test timeout")
        return original_resolve(*args, **kwargs)

    activity_create_service._resolve_active_stage = delayed_resolve
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(post_event, stage_event)
    stage_mutated = False
    original_status = None
    try:
        check(entered.wait(timeout=10), "queued stage selection boundary reached")
        db = base.SessionLocal()
        try:
            stage = db.query(CropStageInstance).filter(
                CropStageInstance.id == uuid.UUID(stage_id)
            ).one()
            original_status = stage.status
            stage.status = "COMPLETED"
            db.commit()
            stage_mutated = True
        finally:
            db.close()
        release.set()
        response = future.result(timeout=30)
        check(response_failure_code(response) == "ACTIVITY_CONTEXT_INVALID", "queued stage change rejects")
    finally:
        release.set()
        activity_create_service._resolve_active_stage = original_resolve
        if stage_mutated:
            db = base.SessionLocal()
            try:
                stage = db.query(CropStageInstance).filter(
                    CropStageInstance.id == uuid.UUID(stage_id)
                ).one()
                stage.status = original_status
                db.commit()
            finally:
                db.close()
        pool.shutdown(wait=False, cancel_futures=True)
    assert_no_activity_effects(stage_event, stage_baseline, "stage change rejection")

    queued_activity_id = uuid.UUID(committed_event["entity_id"])
    direct_reuse_payload = dict(committed_event["payload"])
    direct_reuse_payload.pop("farmer_id", None)
    direct_reuse_payload.pop("crop_cycle_id", None)
    direct = base.client.post(
        f"/api/v1/crop-cycles/{cycle_id}/activities",
        json=direct_reuse_payload,
        headers=base.HEADERS,
    )
    check(direct.status_code == 409, "queued binding blocks direct adoption")
    check(base.response_error(direct) == "ACTIVITY_ID_REUSE", "queued-to-direct collision sanitized")

    direct_id = uuid.uuid4()
    direct_payload = base.activity_payload(direct_id, stage_id, stage_code)
    created = base.client.post(
        f"/api/v1/crop-cycles/{cycle_id}/activities",
        json=direct_payload,
        headers=base.HEADERS,
    )
    check(created.status_code == 201, "direct-to-queued fixture commits")
    response = post_event(queued_event(
        event_id=uuid.uuid4(), activity_id=direct_id, cycle_id=cycle_id,
        stage_id=stage_id, stage_code=stage_code,
    ))
    check(response_failure_code(response) == "ACTIVITY_ID_REUSE", "direct binding blocks queued adoption")

    generic_collision = {
        "event_id": committed_event["event_id"],
        "entity_type": "farmer",
        "entity_id": str(base.FARMER_ID),
        "operation": "UPDATE",
        "payload": {"id": str(base.FARMER_ID)},
        "version": 1,
        "dependency_ids": [],
        "metadata": {},
    }
    generic = post_event(generic_collision)
    check(response_failure_code(generic) == "EVENT_ID_REUSE", "activity-bound event blocks generic replay")

    generic_first_id = uuid.uuid4()
    SYNTHETIC_LEDGER_IDS.add(generic_first_id)
    generic_first = dict(generic_collision)
    generic_first["event_id"] = str(generic_first_id)
    generic_commit = post_event(generic_first)
    check(generic_commit.status_code == 200, "generic collision fixture returns batch response")
    check(generic_commit.json()["accepted"] == [str(generic_first_id)], "generic collision fixture commits")
    activity_after_generic = post_event(queued_event(
        event_id=generic_first_id, activity_id=uuid.uuid4(), cycle_id=cycle_id,
        stage_id=stage_id, stage_code=stage_code,
    ))
    check(response_failure_code(activity_after_generic) == "EVENT_ID_REUSE", "generic-bound event blocks activity")

    mismatch_event = uuid.UUID(committed_event["event_id"])
    db = base.SessionLocal()
    try:
        processed = db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == mismatch_event
        ).one()
        original_status = processed.status
        processed.status = "FAILED"
        db.commit()
    finally:
        db.close()
    try:
        mismatch = post_event(committed_event)
        check(response_failure_code(mismatch) == "EVENT_ID_REUSE", "complete record status mismatch rejects")
    finally:
        db = base.SessionLocal()
        try:
            processed = db.query(SyncProcessedEvent).filter(
                SyncProcessedEvent.event_id == mismatch_event
            ).one()
            processed.status = original_status
            db.commit()
        finally:
            db.close()
    restored = post_event(committed_event)
    check(restored.json()["accepted_details"][0]["outcome"] == "EXACT_REPLAY", "status mismatch restoration replays")

def assert_late_failure_rolls_back(
    cycle_id: str,
    stage_id: str,
    stage_code: str,
) -> None:
    event_id = uuid.uuid4()
    activity_id = uuid.uuid4()
    event = queued_event(
        event_id=event_id,
        activity_id=activity_id,
        cycle_id=cycle_id,
        stage_id=stage_id,
        stage_code=stage_code,
        cost="33.00",
    )
    baseline_db = base.SessionLocal()
    try:
        baseline_total = Decimal(str(baseline_db.query(CropCycle.total_input_cost).filter(
            CropCycle.id == uuid.UUID(cycle_id)
        ).scalar() or 0))
    finally:
        baseline_db.close()
    original = sync_service.append_audit
    observed = {"reached": False, "effects": False}

    def fail_sync_commit(*args, **kwargs):
        action = args[6] if len(args) > 6 else kwargs.get("action")
        if action == "SYNC_COMMIT":
            db = args[0]
            db.flush()
            observed["reached"] = True
            pending_total = Decimal(str(db.query(CropCycle.total_input_cost).filter(
                CropCycle.id == uuid.UUID(cycle_id)
            ).scalar() or 0))
            observed["effects"] = all((
                db.query(CropActivity).filter(CropActivity.id == activity_id).count() == 1,
                db.query(CropActivityCommandBinding).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 1,
                db.query(SyncProcessedEvent).filter(SyncProcessedEvent.event_id == event_id).count() == 1,
                db.query(CropActivitySyncEventBinding).filter(CropActivitySyncEventBinding.event_id == event_id).count() == 1,
                db.query(AuditChainEntry).filter(
                    AuditChainEntry.entity_id == activity_id,
                    AuditChainEntry.action == "ACTIVITY_LOGGED",
                ).count() == 1,
                pending_total == baseline_total + Decimal("33.00"),
            ))
            raise RuntimeError("synthetic late failure")
        return original(*args, **kwargs)

    sync_service.append_audit = fail_sync_commit
    try:
        response = post_event(event)
    finally:
        sync_service.append_audit = original
    check(response.status_code == 200, "late failure returns batch response")
    check(response_failure_code(response) == "ACTIVITY_CREATE_FAILED", "late failure is sanitized")
    check(observed["reached"], "late failure reached SYNC_COMMIT boundary")
    check(observed["effects"], "all six pending effects observed before failure")
    db = base.SessionLocal()
    try:
        check(db.query(CropActivity).filter(CropActivity.id == activity_id).count() == 0, "late failure rolls back activity")
        check(db.query(CropActivityCommandBinding).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 0, "late failure rolls back command binding")
        check(db.query(CropActivitySyncEventBinding).filter(CropActivitySyncEventBinding.event_id == event_id).count() == 0, "late failure rolls back event binding")
        check(db.query(SyncProcessedEvent).filter(SyncProcessedEvent.event_id == event_id).count() == 0, "late failure rolls back ledger")
        check(db.query(AuditChainEntry).filter(AuditChainEntry.entity_id == activity_id).count() == 0, "late failure rolls back audits")
        final_total = Decimal(str(db.query(CropCycle.total_input_cost).filter(
            CropCycle.id == uuid.UUID(cycle_id)
        ).scalar() or 0))
        check(final_total == baseline_total, "late failure rolls back economics")
    finally:
        db.close()


def assert_same_event_concurrency(
    cycle_id: str,
    stage_id: str,
    stage_code: str,
) -> None:
    event = queued_event(
        event_id=uuid.uuid4(),
        activity_id=uuid.uuid4(),
        cycle_id=cycle_id,
        stage_id=stage_id,
        stage_code=stage_code,
        cost="41.00",
    )
    db = base.SessionLocal()
    try:
        baseline_total = Decimal(str(db.query(CropCycle.total_input_cost).filter(
            CropCycle.id == uuid.UUID(cycle_id)
        ).scalar() or 0))
    finally:
        db.close()

    barrier = __import__("threading").Barrier(2)
    original_lock = sync_service.lock_sync_event_ids

    def controlled_lock(db, tenant_id, event_ids):
        barrier.wait(timeout=10)
        return original_lock(db, tenant_id, event_ids)

    def worker():
        with base.TestClient(base.app, raise_server_exceptions=False) as isolated:
            return post_event(event, isolated)

    sync_service.lock_sync_event_ids = controlled_lock
    pool = ThreadPoolExecutor(max_workers=2)
    futures = [pool.submit(worker) for _ in range(2)]
    try:
        responses = [future.result(timeout=30) for future in futures]
    except FutureTimeoutError:
        for future in futures:
            future.cancel()
        raise AssertionError("QUEUED_ACTIVITY_CHECK_FAILED:concurrent worker timeout") from None
    finally:
        sync_service.lock_sync_event_ids = original_lock
        pool.shutdown(wait=False, cancel_futures=True)
    check(all(response.status_code == 200 for response in responses), "same-event concurrent responses succeed")
    outcomes = sorted(response.json()["accepted_details"][0]["outcome"] for response in responses)
    check(outcomes == ["COMMITTED", "EXACT_REPLAY"], "same-event concurrency commits once")
    check(all(response.json()["accepted"] == [event["event_id"]] for response in responses), "same-event responses retain exact event ID")
    for index, response in enumerate(responses):
        outcome = response.json()["accepted_details"][0]["outcome"]
        assert_single_correlated_detail(response.json(), event, outcome, f"same-event response {index}")
    activity_id = uuid.UUID(event["entity_id"])
    event_id = uuid.UUID(event["event_id"])
    db = base.SessionLocal()
    try:
        check(db.query(CropActivity).filter(CropActivity.id == activity_id).count() == 1, "same-event concurrency stores one activity")
        check(db.query(CropActivityCommandBinding).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 1, "same-event concurrency stores one command binding")
        check(db.query(CropActivitySyncEventBinding).filter(CropActivitySyncEventBinding.event_id == event_id).count() == 1, "same-event concurrency stores one event binding")
        current_total = Decimal(str(db.query(CropCycle.total_input_cost).filter(
            CropCycle.id == uuid.UUID(cycle_id)
        ).scalar() or 0))
        check(current_total == baseline_total + Decimal("41.00"), "same-event concurrency charges once")
    finally:
        db.close()
    assert_committed_event(event, "same-event concurrency")


def assert_additional_concurrency(
    cycle_id: str,
    stage_id: str,
    stage_code: str,
) -> None:
    def totals() -> Decimal:
        db = base.SessionLocal()
        try:
            return Decimal(str(db.query(CropCycle.total_input_cost).filter(
                CropCycle.id == uuid.UUID(cycle_id)
            ).scalar() or 0))
        finally:
            db.close()

    def run_controlled(callables):
        barrier = __import__("threading").Barrier(2)
        original_lock = sync_service.lock_sync_event_ids

        def controlled_lock(db, tenant_id, event_ids):
            barrier.wait(timeout=10)
            return original_lock(db, tenant_id, event_ids)

        sync_service.lock_sync_event_ids = controlled_lock
        pool = ThreadPoolExecutor(max_workers=2)
        futures = [pool.submit(callback) for callback in callables]
        try:
            return [future.result(timeout=30) for future in futures]
        except FutureTimeoutError:
            for future in futures:
                future.cancel()
            raise AssertionError("QUEUED_ACTIVITY_CHECK_FAILED:concurrent worker timeout") from None
        finally:
            sync_service.lock_sync_event_ids = original_lock
            pool.shutdown(wait=False, cancel_futures=True)

    def isolated_post(event_or_events):
        with base.TestClient(base.app, raise_server_exceptions=False) as isolated:
            if isinstance(event_or_events, list):
                return post_batch(event_or_events, isolated)
            return post_event(event_or_events, isolated)

    shared_activity = uuid.uuid4()
    first = queued_event(
        event_id=uuid.uuid4(), activity_id=shared_activity, cycle_id=cycle_id,
        stage_id=stage_id, stage_code=stage_code, cost="43.00",
    )
    second = queued_event(
        event_id=uuid.uuid4(), activity_id=shared_activity, cycle_id=cycle_id,
        stage_id=stage_id, stage_code=stage_code, cost="43.00",
    )
    before = totals()
    responses = run_controlled([
        lambda: isolated_post(first),
        lambda: isolated_post(second),
    ])
    for request_event, response in zip((first, second), responses):
        body = response.json()
        if body["accepted"]:
            assert_single_correlated_detail(
                body,
                request_event,
                "COMMITTED",
                "same activity request winner",
            )
        else:
            check(body["accepted"] == [], "same activity request loser has no acceptance")
            check(body["accepted_details"] == [], "same activity request loser has no detail")
            check(len(body["failed"]) == 1, "same activity request loser failure cardinality")
            check(body["failed"][0]["event_id"] == request_event["event_id"], "same activity request loser event ID")
            check(body["failed"][0]["error_code"] == "ACTIVITY_ID_REUSE", "same activity request loser error code")
    check(sum(len(response.json()["accepted"]) for response in responses) == 1, "same activity different events accepts once")
    check(sum(len(response.json()["failed"]) for response in responses) == 1, "same activity different events rejects once")
    check(totals() == before + Decimal("43.00"), "same activity different events charges once")
    accepted_event_id = next(
        response.json()["accepted"][0]
        for response in responses
        if response.json()["accepted"]
    )
    committed_shared = first if first["event_id"] == accepted_event_id else second
    rejected_shared = second if committed_shared is first else first
    winner = next(response.json() for response in responses if response.json()["accepted"])
    loser = next(response.json() for response in responses if response.json()["failed"])
    assert_single_correlated_detail(winner, committed_shared, "COMMITTED", "same activity winner")
    check(loser["accepted"] == [], "same activity loser has no acceptance")
    check(loser["accepted_details"] == [], "same activity loser has no detail")
    check(len(loser["failed"]) == 1, "same activity loser failure cardinality")
    check(loser["failed"][0]["event_id"] == rejected_shared["event_id"], "same activity loser event ID")
    check(loser["failed"][0]["error_code"] == "ACTIVITY_ID_REUSE", "same activity loser error code")
    assert_committed_event(committed_shared, "same activity different events")
    db = base.SessionLocal()
    try:
        check(db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == uuid.UUID(rejected_shared["event_id"])
        ).count() == 0, "rejected competing event has no ledger")
        check(db.query(CropActivitySyncEventBinding).filter(
            CropActivitySyncEventBinding.event_id == uuid.UUID(rejected_shared["event_id"])
        ).count() == 0, "rejected competing event has no binding")
    finally:
        db.close()

    distinct = [
        queued_event(
            event_id=uuid.uuid4(), activity_id=uuid.uuid4(), cycle_id=cycle_id,
            stage_id=stage_id, stage_code=stage_code, cost=cost,
        )
        for cost in ("47.00", "53.00")
    ]
    before = totals()
    responses = run_controlled([
        lambda: isolated_post(distinct[0]),
        lambda: isolated_post(distinct[1]),
    ])
    check(all(len(response.json()["accepted"]) == 1 for response in responses), "distinct activity concurrency accepts both")
    check({response.json()["accepted"][0] for response in responses} == {event["event_id"] for event in distinct}, "distinct activity responses retain exact IDs")
    check(totals() == before + Decimal("100.00"), "distinct activity costs both survive")
    for index, (event, response) in enumerate(zip(distinct, responses)):
        assert_single_correlated_detail(response.json(), event, "COMMITTED", f"distinct activity response {index}")
        assert_committed_event(event, f"distinct activity {index}")

    opposite = [
        queued_event(
            event_id=uuid.uuid4(), activity_id=uuid.uuid4(), cycle_id=cycle_id,
            stage_id=stage_id, stage_code=stage_code, cost=cost,
        )
        for cost in ("59.00", "61.00")
    ]
    before = totals()
    responses = run_controlled([
        lambda: isolated_post(opposite),
        lambda: isolated_post(list(reversed(opposite))),
    ])
    check(all(len(response.json()["accepted"]) == 2 for response in responses), "opposite-order batches both resolve")
    outcomes = sorted(
        detail["outcome"]
        for response in responses
        for detail in response.json()["accepted_details"]
    )
    check(outcomes == ["COMMITTED", "COMMITTED", "EXACT_REPLAY", "EXACT_REPLAY"], "opposite-order batches commit once")
    check(all(set(response.json()["accepted"]) == {event["event_id"] for event in opposite} for response in responses), "opposite-order responses retain exact IDs")
    response_outcomes = []
    expected_by_id = {event["event_id"]: event for event in opposite}
    for response_index, response in enumerate(responses):
        body = response.json()
        check(body["failed"] == [], f"opposite-order response {response_index} has no failure")
        check(len(body["accepted_details"]) == 2, f"opposite-order response {response_index} detail cardinality")
        check(
            {detail["event_id"] for detail in body["accepted_details"]}
            == set(expected_by_id),
            f"opposite-order response {response_index} detail event ID set",
        )
        per_response = {detail["outcome"] for detail in body["accepted_details"]}
        check(len(per_response) == 1, f"opposite-order response {response_index} has one outcome class")
        response_outcome = next(iter(per_response))
        response_outcomes.append(response_outcome)
        for detail in body["accepted_details"]:
            expected = expected_by_id[detail["event_id"]]
            check(detail["entity_type"] == expected["entity_type"], f"opposite-order response {response_index} entity type")
            check(detail["entity_id"] == expected["entity_id"], f"opposite-order response {response_index} entity ID")
            check(detail["activity_id"] == expected["entity_id"], f"opposite-order response {response_index} activity ID")
            check(detail["outcome"] == response_outcome, f"opposite-order response {response_index} correlated outcome")
    check(sorted(response_outcomes) == ["COMMITTED", "EXACT_REPLAY"], "opposite-order response outcome classes")
    check(totals() == before + Decimal("120.00"), "opposite-order costs apply once")
    for index, event in enumerate(opposite):
        assert_committed_event(event, f"opposite-order activity {index}")


def main() -> int:
    print("=" * 72)
    print("QUEUED CROP-ACTIVITY CREATE FOCUSED REGRESSION")
    print("=" * 72)
    base.admit_actual_database()
    base.reset_fixture()
    user_id = base.install_test_admin()
    try:
        cycle_id, stage_id, stage_code = base.create_active_cycle()
        event, _ = assert_first_commit_and_replay(cycle_id, stage_id, stage_code)
        assert_conflicting_replays(event)
        assert_command_binding_only_rejects(cycle_id, stage_id, stage_code)
        assert_additional_identity_states(cycle_id, stage_id, stage_code, event)
        assert_partial_and_mismatch_states(cycle_id, stage_id, stage_code, event)
        assert_queued_policy_boundaries(cycle_id, stage_id, stage_code, event)
        assert_late_failure_rolls_back(cycle_id, stage_id, stage_code)
        assert_same_event_concurrency(cycle_id, stage_id, stage_code)
        assert_additional_concurrency(cycle_id, stage_id, stage_code)
        base.assert_unsupported_sync_operations(cycle_id, base.activity_payload(uuid.uuid4(), stage_id, stage_code))
    finally:
        try:
            cleanup_synthetic_ledgers()
        finally:
            base.cleanup_test_admin(user_id)
    print("QUEUED_CROP_ACTIVITY_CREATE_FOCUSED_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except AssertionError as exc:
        message = str(exc)
        if message.startswith("QUEUED_ACTIVITY_CHECK_FAILED:"):
            print(message)
        else:
            print("QUEUED_ACTIVITY_ASSERTION_FAILURE:AssertionError")
        raise SystemExit(1)
    except BaseException as exc:
        print(f"QUEUED_ACTIVITY_UNEXPECTED_FAILURE:{type(exc).__name__}")
        raise SystemExit(1)
