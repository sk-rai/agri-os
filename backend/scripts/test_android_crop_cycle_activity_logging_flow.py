#!/usr/bin/env python3
"""Focused direct crop-activity command regression.

Destructive to the deterministic crop-cycle fixture. Run only on a separately
approved disposable PostgreSQL database. Queued CREATE is verified separately.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import sys
import threading
import uuid
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

APPROVAL_ENV = "DIRECT_ACTIVITY_DISPOSABLE_APPROVED"
DATABASE_ENV = "DIRECT_ACTIVITY_DISPOSABLE_DATABASE"
DATABASE_PREFIX = "agrios_direct_activity_disposable_"
EXPECTED_PORT = 5432


def require_operator_admission() -> str:
    if os.environ.get(APPROVAL_ENV) != "YES":
        raise SystemExit("DIRECT_ACTIVITY_ADMISSION_REQUIRED")
    expected_database = os.environ.get(DATABASE_ENV, "")
    if not expected_database.startswith(DATABASE_PREFIX):
        raise SystemExit("DIRECT_ACTIVITY_DATABASE_NAME_REJECTED")
    if os.environ.get("DB_NAME") != expected_database:
        raise SystemExit("DIRECT_ACTIVITY_APPLICATION_DATABASE_REJECTED")
    if os.environ.get("DB_HOST") not in {"127.0.0.1", "::1"}:
        raise SystemExit("DIRECT_ACTIVITY_APPLICATION_HOST_REJECTED")
    if os.environ.get("DB_PORT") != str(EXPECTED_PORT):
        raise SystemExit("DIRECT_ACTIVITY_APPLICATION_PORT_REJECTED")
    return expected_database


# Fail before importing any module that initializes application database state.
EXPECTED_DATABASE = require_operator_admission()

try:
    from fastapi.testclient import TestClient
    from sqlalchemy import event, text

    from app.core.database import SessionLocal, get_db
    from app.main import app
    from app.modules.master_data.models import (
        AgriculturalInput,
        AgriculturalProduct,
        AgriculturalProductPackage,
        Manufacturer,
        ProjectProductApproval,
    )
    from app.modules.sync.models import (
        AuditChainEntry,
        CropActivityCommandBinding,
        CropActivitySyncEventBinding,
        SyncProcessedEvent,
    )
    from app.modules.workflow.models import CropActivity, CropCycle
    from app.modules.workflow import activity_create_service
    from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin
    from scripts.direct_crop_activity_current_contract import assert_current_read_contracts
    from scripts.seed_android_crop_cycle_test_fixture import (
        CROP_CODE,
        FARMER_ID,
        PARCEL_ID,
        PROJECT_ID,
        SEASON_CODE,
        TENANT_ID,
        main as seed_crop_cycle_fixture_main,
    )
except BaseException as exc:
    print(f"DIRECT_ACTIVITY_BOOTSTRAP_FAILURE:{type(exc).__name__}")
    raise SystemExit(1)


HEADERS: dict[str, str] = {}
ACTIVITY_COST = Decimal("325.50")
SECOND_ACTIVITY_COST = Decimal("174.50")
LOCK_TIMEOUT_MS = 5000
STATEMENT_TIMEOUT_MS = 15000


def _apply_connection_timeouts(dbapi_connection, _connection_record, *_args) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"SET lock_timeout = '{LOCK_TIMEOUT_MS}ms'")
        cursor.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'")
        cursor.execute(f"SET idle_in_transaction_session_timeout = '{STATEMENT_TIMEOUT_MS}ms'")
        dbapi_connection.commit()
    finally:
        cursor.close()


try:
    TEST_ENGINE = SessionLocal.kw["bind"]
    event.listen(TEST_ENGINE, "connect", _apply_connection_timeouts)
    TEST_ENGINE.dispose()
    client = TestClient(app, raise_server_exceptions=False)
except BaseException as exc:
    print(f"DIRECT_ACTIVITY_BOOTSTRAP_FAILURE:{type(exc).__name__}")
    raise SystemExit(1)


def check(condition, label):
    if not condition:
        raise AssertionError(f"DIRECT_ACTIVITY_CHECK_FAILED:{label}")
    print(f"PASS {label}")


def response_error(response) -> str | None:
    try:
        detail = response.json().get("detail")
    except (AttributeError, TypeError, ValueError):
        return None
    return detail.get("error") if isinstance(detail, dict) else None


def admit_actual_database() -> None:
    configured = urlsplit(str(SessionLocal.kw["bind"].url).replace("postgresql+psycopg2", "postgresql", 1))
    check(configured.hostname in {"127.0.0.1", "localhost", "::1"}, "configured endpoint is local")
    check(configured.port == EXPECTED_PORT, "configured port is 5432")
    check(configured.path == f"/{EXPECTED_DATABASE}", "configured database matches approval")
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT current_database(), host(inet_server_addr()), "
                "inet_server_port(), pg_is_in_recovery()"
            )
        ).one()
        check(row[0] == EXPECTED_DATABASE, "actual database matches approval")
        check(ipaddress.ip_address(row[1]).is_loopback, "actual server is loopback")
        check(row[2] == EXPECTED_PORT, "actual server port is 5432")
        check(row[3] is False, "actual server is primary")
    finally:
        db.close()


def reset_fixture() -> None:
    cleanup_db = SessionLocal()
    try:
        activity_ids = [row[0] for row in cleanup_db.query(CropActivity.id).join(
            CropCycle,
            CropCycle.id == CropActivity.crop_cycle_id,
        ).filter(
            CropCycle.tenant_id == TENANT_ID,
            CropCycle.farmer_id == FARMER_ID,
        ).all()]
        event_ids = [row[0] for row in cleanup_db.query(CropActivitySyncEventBinding.event_id).filter(
            CropActivitySyncEventBinding.activity_id.in_(activity_ids)
        ).all()]
        cleanup_db.query(CropActivitySyncEventBinding).filter(
            CropActivitySyncEventBinding.event_id.in_(event_ids)
        ).delete(synchronize_session=False)
        cleanup_db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id.in_(event_ids)
        ).delete(synchronize_session=False)
        cleanup_db.query(CropActivityCommandBinding).filter(
            CropActivityCommandBinding.activity_id.in_(activity_ids)
        ).delete(synchronize_session=False)
        cleanup_db.commit()
    except BaseException:
        cleanup_db.rollback()
        raise
    finally:
        cleanup_db.close()
    old_argv = list(sys.argv)
    try:
        sink = io.StringIO()
        with redirect_stdout(sink):
            sys.argv = ["seed_android_crop_cycle_test_fixture.py", "--reset", "--apply"]
            reset_status = seed_crop_cycle_fixture_main()
            sys.argv = ["seed_android_crop_cycle_test_fixture.py", "--apply"]
            apply_status = seed_crop_cycle_fixture_main()
        check(reset_status == 0, "fixture reset completed")
        check(apply_status == 0, "fixture apply completed")
    finally:
        sys.argv = old_argv


def install_test_admin() -> uuid.UUID:
    global HEADERS
    db = SessionLocal()
    try:
        user, HEADERS = create_test_admin(
            db,
            tenant_id=TENANT_ID,
            role="ENTERPRISE_ADMIN",
        )
        user_id = user.id
    finally:
        db.close()

    return user_id


def cleanup_test_admin(user_id: uuid.UUID) -> None:
    cleanup_db = SessionLocal()
    try:
        delete_test_admin(cleanup_db, user_id)
    except BaseException as exc:
        cleanup_db.rollback()
        print(f"DIRECT_ACTIVITY_CLEANUP_FAILURE:{type(exc).__name__}")
        raise RuntimeError("DIRECT_ACTIVITY_CLEANUP_FAILED") from None
    finally:
        cleanup_db.close()


def create_active_cycle(*, year_offset: int = 0) -> tuple[str, str, str]:
    planned = date.today().replace(year=date.today().year + year_offset) + timedelta(days=7)
    response = client.post(
        "/api/v1/crop-cycles",
        json={
            "farmer_id": str(FARMER_ID),
            "parcel_id": str(PARCEL_ID),
            "project_id": str(PROJECT_ID),
            "crop_code": CROP_CODE,
            "season_code": SEASON_CODE,
            "planned_sowing_date": planned.isoformat(),
            "seed_source": "OWN_SAVED",
        },
        headers=HEADERS,
    )
    check(response.status_code == 201, "crop cycle created")
    cycle = response.json()
    stage = cycle["stages"][0]
    started = client.patch(
        f"/api/v1/crop-cycles/{cycle['id']}/stages/{stage['id']}",
        json={"action": "START", "notes": "Direct command regression"},
        headers=HEADERS,
    )
    check(started.status_code == 200, "first stage started")
    return cycle["id"], stage["id"], stage["code"]


def set_cycle_completed(cycle_id: str) -> None:
    db = SessionLocal()
    try:
        cycle = db.query(CropCycle).filter(CropCycle.id == uuid.UUID(cycle_id)).one()
        cycle.status = "COMPLETED"
        db.commit()
    finally:
        db.close()


def activity_payload(activity_id: uuid.UUID, stage_id: str, stage_code: str) -> dict:
    return {
        "activity_id": str(activity_id),
        "requested_stage_id": stage_id,
        "requested_stage_code": stage_code.lower(),
        "activity_type": "LABOR",
        "input_name": "Cafe\u0301 nursery labor",
        "quantity": "1.00",
        "quantity_unit": "day",
        "area_applied": "1.25",
        "area_unit": "acre",
        "cost_amount": str(ACTIVITY_COST),
        "cost_currency": "inr",
        "activity_date": date.today().isoformat(),
        "gps_lat": "15.45890000",
        "gps_lng": "75.00780000",
        "notes": "Cafe\u0301 direct command",
    }


def assert_decimal_ingress_rejections(
    cycle_id: str,
    stage_id: str,
    stage_code: str,
) -> None:
    cases = (
        ("quantity precision", {"quantity": "123456789.12"}),
        ("quantity scale", {"quantity": "1.001"}),
        ("negative cost", {"cost_amount": "-0.01"}),
        ("latitude bound", {"gps_lat": "90.00000001"}),
        ("longitude bound", {"gps_lng": "-180.00000001"}),
    )
    for label, change in cases:
        activity_id = uuid.uuid4()
        payload = activity_payload(activity_id, stage_id, stage_code)
        payload.update(change)
        response = client.post(
            f"/api/v1/crop-cycles/{cycle_id}/activities",
            json=payload,
            headers=HEADERS,
        )
        check(response.status_code == 422, f"{label} rejects")
        check(response_error(response) == "ACTIVITY_PAYLOAD_INVALID", f"{label} is sanitized")
        db = SessionLocal()
        try:
            check(
                db.query(CropActivity).filter(CropActivity.id == activity_id).count() == 0,
                f"{label} stores no activity",
            )
            check(
                db.query(CropActivityCommandBinding).filter(
                    CropActivityCommandBinding.activity_id == activity_id
                ).count() == 0,
                f"{label} stores no binding",
            )
        finally:
            db.close()


def expected_canonical_text(cycle_id: str, payload: dict) -> str:
    expected = {
        "intent_version": "crop_activity_intent.v1",
        "tenant_id": TENANT_ID,
        "actor_id": HEADERS["X-Actor-ID"],
        "farmer_id": str(FARMER_ID),
        "crop_cycle_id": cycle_id,
        "activity_id": payload["activity_id"],
        "requested_stage_id": payload["requested_stage_id"],
        "requested_stage_code": payload["requested_stage_code"].upper(),
        "activity_type": "LABOR",
        "activity_date": payload["activity_date"],
        "input_code": None,
        "input_name": "Café nursery labor",
        "input_rule_id": None,
        "product_id": None,
        "product_code": None,
        "package_id": None,
        "package_sku": None,
        "quantity": "1",
        "quantity_unit": "DAY",
        "area_applied": "1.25",
        "area_unit": "ACRE",
        "recommended_quantity": None,
        "recommended_quantity_unit": None,
        "actual_quantity": None,
        "actual_quantity_unit": None,
        "dosage_variance_reason": None,
        "cost_amount": "325.5",
        "cost_currency": "INR",
        "gps_lat": "15.4589",
        "gps_lng": "75.0078",
        "irrigation_source": None,
        "duration_hours": None,
        "notes": "Café direct command",
        "origin_kind": "DIRECT",
        "event_id": None,
        "entity_type": None,
        "operation": None,
        "client_version": None,
        "dependency_ids": None,
    }
    return json.dumps(
        expected,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def utc_text(value: datetime) -> str:
    check(value is not None, "snapshot timestamp is present")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def expected_snapshot(row: CropActivity, cycle_id: str, payload: dict) -> dict:
    return {
        "activity_id": payload["activity_id"],
        "tenant_id": TENANT_ID,
        "farmer_id": str(FARMER_ID),
        "crop_cycle_id": cycle_id,
        "stage_instance_id": payload["requested_stage_id"],
        "activity_type": "LABOR",
        "activity_date": payload["activity_date"],
        "input_code": None,
        "input_name": "Café nursery labor",
        "input_rule_id": None,
        "product_id": None,
        "product_code": None,
        "package_id": None,
        "package_sku": None,
        "quantity": "1.00",
        "quantity_unit": "DAY",
        "area_applied": "1.25",
        "area_unit": "ACRE",
        "recommended_quantity": None,
        "recommended_quantity_unit": None,
        "actual_quantity": None,
        "actual_quantity_unit": None,
        "dosage_variance_reason": None,
        "cost_amount": "325.50",
        "cost_currency": "INR",
        "gps_lat": "15.45890000",
        "gps_lng": "75.00780000",
        "irrigation_source": None,
        "duration_hours": None,
        "logged_by": HEADERS["X-Actor-ID"],
        "logging_method": "MANUAL",
        "notes": "Café direct command",
        "version": "v1.0",
        "is_active": True,
        "created_at": utc_text(row.created_at),
        "updated_at": utc_text(row.updated_at),
    }


def assert_first_commit(cycle_id: str, payload: dict) -> dict:
    response = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/activities",
        json=payload,
        headers=HEADERS,
    )
    check(response.status_code == 201, "direct activity first commit returns 201")
    result = response.json()
    check(result["outcome"] == "COMMITTED", "First command reports COMMITTED")
    check(result["activity_id"] == payload["activity_id"], "Stable activity ID retained")
    check(result["intent_version"] == "crop_activity_intent.v1", "Intent version returned")
    expected_canonical = expected_canonical_text(cycle_id, payload)
    expected_digest = hashlib.sha256(expected_canonical.encode("utf-8")).hexdigest()
    check(result["intent_sha256"] == expected_digest, "independent intent digest returned")

    db = SessionLocal()
    try:
        activity_id = uuid.UUID(payload["activity_id"])
        row = db.query(CropActivity).filter(CropActivity.id == activity_id).one()
        binding = db.query(CropActivityCommandBinding).filter(
            CropActivityCommandBinding.activity_id == activity_id
        ).one()
        audits = db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == TENANT_ID,
            AuditChainEntry.entity_id == activity_id,
            AuditChainEntry.action == "ACTIVITY_LOGGED",
        ).all()
        cycle = db.query(CropCycle).filter(CropCycle.id == uuid.UUID(cycle_id)).one()
        check(row.input_name == "Café nursery labor", "NFC input name persisted")
        check(row.notes == "Café direct command", "NFC notes persisted")
        check(row.quantity_unit == "DAY", "Quantity unit normalized")
        check(row.area_unit == "ACRE", "Area unit normalized")
        check(row.cost_currency == "INR", "Currency normalized")
        check(row.cost_amount == ACTIVITY_COST, "Activity cost persisted")
        check(cycle.total_input_cost == ACTIVITY_COST, "Cycle total recomputed")
        check(binding.origin_kind == "DIRECT", "Direct binding retained")
        check(binding.intent_version == "crop_activity_intent.v1", "Binding intent version retained")
        check(binding.intent_canonical == expected_canonical, "Complete canonical intent retained")
        check(binding.intent_sha256 == expected_digest, "Binding digest independently verified")
        expected_response = {
            "activity_id": payload["activity_id"],
            "activity_type": "LABOR",
            "input_rule_id": None,
            "product_code": None,
            "package_sku": None,
            "stage_code": payload["requested_stage_code"].upper(),
            "cycle_total_input_cost": "325.50",
            "events_published": ["crop_activity_logged.v1"],
        }
        expected_result = {
            "response": expected_response,
            "persisted_activity": expected_snapshot(row, cycle_id, payload),
            "cycle_total_input_cost": "325.50",
            "audit_correlation_id": str(binding.audit_correlation_id),
        }
        check(binding.result_version == "crop_activity_result.v1", "Binding result version retained")
        check(binding.result_payload == expected_result, "Complete retained result matches expectation")
        check(
            {key: result[key] for key in expected_response} == expected_response,
            "Complete first response matches retained response",
        )
        check(len(audits) == 1, "Exactly one business audit retained")
        check(audits[0].correlation_id == binding.audit_correlation_id, "Audit correlation retained")
    finally:
        db.close()
    return result


def assert_second_activity(cycle_id: str, payload: dict) -> tuple[Decimal, str]:
    second = dict(payload)
    second["activity_id"] = str(uuid.uuid4())
    second["input_name"] = "Second nonzero activity"
    second["notes"] = "Replay total discriminator"
    second["cost_amount"] = str(SECOND_ACTIVITY_COST)
    response = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/activities",
        json=second,
        headers=HEADERS,
    )
    check(response.status_code == 201, "second nonzero activity commits")
    check(response.json().get("outcome") == "COMMITTED", "second activity reports COMMITTED")
    expected_total = ACTIVITY_COST + SECOND_ACTIVITY_COST
    db = SessionLocal()
    try:
        cycle = db.query(CropCycle).filter(CropCycle.id == uuid.UUID(cycle_id)).one()
        check(cycle.total_input_cost == expected_total, "current total differs from first retained total")
    finally:
        db.close()
    return expected_total, second["activity_id"]


def assert_exact_replay(cycle_id: str, payload: dict, first: dict, current_total: Decimal) -> None:
    set_cycle_completed(cycle_id)

    response = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/activities",
        json=payload,
        headers=HEADERS,
    )
    check(response.status_code == 201, "exact replay returns 201")
    replay = response.json()
    check(replay["outcome"] == "EXACT_REPLAY", "Replay reports EXACT_REPLAY")
    check(replay["intent_sha256"] == first["intent_sha256"], "Replay retains digest")
    check(replay["cycle_total_input_cost"] == first["cycle_total_input_cost"], "Replay retains original total")
    check(Decimal(replay["cycle_total_input_cost"]) == ACTIVITY_COST, "Replay total is not current total")

    db = SessionLocal()
    try:
        activity_id = uuid.UUID(payload["activity_id"])
        check(db.query(CropActivity).filter(CropActivity.id == activity_id).count() == 1, "Replay keeps one activity")
        check(db.query(CropActivityCommandBinding).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 1, "Replay keeps one binding")
        check(db.query(AuditChainEntry).filter(AuditChainEntry.entity_id == activity_id, AuditChainEntry.action == "ACTIVITY_LOGGED").count() == 1, "Replay keeps one audit")
        cycle = db.query(CropCycle).filter(CropCycle.id == uuid.UUID(cycle_id)).one()
        check(cycle.total_input_cost == current_total, "Replay leaves current economics unchanged")
    finally:
        db.close()


def expect_identity_reuse(cycle_id: str, payload: dict, label: str) -> None:
    response = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/activities",
        json=payload,
        headers=HEADERS,
    )
    check(response.status_code == 409, f"{label} rejects replay")
    check(response_error(response) == "ACTIVITY_ID_REUSE", f"{label} rejection is sanitized")


def expect_restored_exact_replay(cycle_id: str, payload: dict, label: str) -> None:
    response = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/activities",
        json=payload,
        headers=HEADERS,
    )
    check(response.status_code == 201, f"{label} restoration permits replay")
    check(response.json().get("outcome") == "EXACT_REPLAY", f"{label} restoration is exact")


def assert_tamper_fails_closed(cycle_id: str, payload: dict) -> None:
    activity_id = uuid.UUID(payload["activity_id"])
    baseline_db = SessionLocal()
    try:
        baseline_row = baseline_db.query(CropActivity).filter(
            CropActivity.id == activity_id
        ).one()
        baseline = {
            column.name: getattr(baseline_row, column.name)
            for column in CropActivity.__table__.columns
        }
        check("updated_at" in baseline, "tamper baseline includes updated_at")
    finally:
        baseline_db.close()
    mutations = (
        ("version", "v9.9"),
        ("is_active", False),
        ("created_at", datetime.now(timezone.utc) - timedelta(days=30)),
    )
    for field, changed in mutations:
        db = SessionLocal()
        try:
            db.query(CropActivity).filter(CropActivity.id == activity_id).update(
                {
                    field: changed,
                    "updated_at": baseline["updated_at"],
                },
                synchronize_session=False,
            )
            db.commit()
        finally:
            db.close()
        verification_db = SessionLocal()
        try:
            changed_row = verification_db.query(CropActivity).filter(
                CropActivity.id == activity_id
            ).one()
            changed_columns = {
                column.name
                for column in CropActivity.__table__.columns
                if getattr(changed_row, column.name) != baseline[column.name]
            }
            check(
                changed_columns == {field},
                f"changed persisted {field} is isolated",
            )
            check(
                changed_row.updated_at == baseline["updated_at"],
                f"changed persisted {field} preserves updated_at",
            )
        finally:
            verification_db.close()
        try:
            expect_identity_reuse(cycle_id, payload, f"changed persisted {field}")
        finally:
            db = SessionLocal()
            try:
                db.query(CropActivity).filter(CropActivity.id == activity_id).update(
                    baseline,
                    synchronize_session=False,
                )
                db.commit()
            finally:
                db.close()
        expect_restored_exact_replay(cycle_id, payload, f"changed persisted {field}")

    db = SessionLocal()
    try:
        binding = db.query(CropActivityCommandBinding).filter(
            CropActivityCommandBinding.activity_id == activity_id
        ).one()
        original_result = dict(binding.result_payload)
        changed_result = dict(original_result)
        changed_response = dict(changed_result["response"])
        changed_response["cycle_total_input_cost"] = "999.99"
        changed_result["response"] = changed_response
        binding.result_payload = changed_result
        db.commit()
    finally:
        db.close()
    try:
        expect_identity_reuse(cycle_id, payload, "changed retained result")
    finally:
        db = SessionLocal()
        try:
            binding = db.query(CropActivityCommandBinding).filter(
                CropActivityCommandBinding.activity_id == activity_id
            ).one()
            binding.result_payload = original_result
            db.commit()
        finally:
            db.close()
    expect_restored_exact_replay(cycle_id, payload, "changed retained result")

    db = SessionLocal()
    try:
        binding = db.query(CropActivityCommandBinding).filter(
            CropActivityCommandBinding.activity_id == activity_id
        ).one()
        audit = db.query(AuditChainEntry).filter(
            AuditChainEntry.correlation_id == binding.audit_correlation_id,
            AuditChainEntry.action == "ACTIVITY_LOGGED",
        ).one()
        audit_correlation_id = binding.audit_correlation_id
        original_action = audit.action
        audit.action = "ACTIVITY_LOGGED_TEST_TAMPER"
        db.commit()
    finally:
        db.close()
    try:
        expect_identity_reuse(cycle_id, payload, "changed audit correlation record")
    finally:
        db = SessionLocal()
        try:
            audit = db.query(AuditChainEntry).filter(
                AuditChainEntry.correlation_id == audit_correlation_id
            ).one()
            audit.action = original_action
            db.commit()
        finally:
            db.close()
    expect_restored_exact_replay(cycle_id, payload, "changed audit correlation record")


def assert_identity_boundaries(cycle_id: str, payload: dict) -> tuple[str, str, str]:
    db = SessionLocal()
    try:
        other_actor, other_headers = create_test_admin(
            db,
            tenant_id=TENANT_ID,
            role="ENTERPRISE_ADMIN",
        )
        other_actor_id = other_actor.id
    finally:
        db.close()
    try:
        response = client.post(
            f"/api/v1/crop-cycles/{cycle_id}/activities",
            json=payload,
            headers=other_headers,
        )
        check(response.status_code == 409, "different actor cannot replay binding")
        check(response_error(response) == "ACTIVITY_ID_REUSE", "actor rejection is sanitized")
    finally:
        db = SessionLocal()
        try:
            delete_test_admin(db, other_actor_id)
        finally:
            db.close()

    foreign_tenant = f"{TENANT_ID}-foreign"
    db = SessionLocal()
    try:
        foreign_actor, foreign_headers = create_test_admin(
            db,
            tenant_id=foreign_tenant,
            role="ENTERPRISE_ADMIN",
        )
        foreign_actor_id = foreign_actor.id
    finally:
        db.close()
    try:
        response = client.post(
            f"/api/v1/crop-cycles/{cycle_id}/activities",
            json=payload,
            headers=foreign_headers,
        )
        check(response.status_code == 404, "different tenant cannot discover cycle binding")
    finally:
        db = SessionLocal()
        try:
            delete_test_admin(db, foreign_actor_id)
        finally:
            db.close()

    other_cycle_id, other_stage_id, other_stage_code = create_active_cycle(year_offset=1)
    response = client.post(
        f"/api/v1/crop-cycles/{other_cycle_id}/activities",
        json={**payload, "requested_stage_id": None, "requested_stage_code": None},
        headers=HEADERS,
    )
    check(response.status_code == 409, "different cycle cannot adopt activity binding")
    check(response_error(response) == "ACTIVITY_ID_REUSE", "cycle rejection is sanitized")
    return other_cycle_id, other_stage_id, other_stage_code


def assert_commit_failure_rolls_back(cycle_id: str, stage_id: str, stage_code: str) -> None:
    activity_id = uuid.uuid4()
    payload = activity_payload(activity_id, stage_id, stage_code)
    baseline_db = SessionLocal()
    try:
        baseline_total = baseline_db.query(CropCycle.total_input_cost).filter(
            CropCycle.id == uuid.UUID(cycle_id)
        ).scalar()
    finally:
        baseline_db.close()
    failing_session = SessionLocal()
    real_commit = failing_session.commit
    real_rollback = failing_session.rollback
    real_close = failing_session.close
    observed = {
        "commit_reached": False,
        "pending_activity": False,
        "pending_binding": False,
        "pending_audit": False,
        "pending_economics": False,
        "rollback_before_close": False,
        "close_reached": False,
    }

    def fail_commit() -> None:
        observed["commit_reached"] = True
        observed["pending_activity"] = failing_session.query(CropActivity).filter(
            CropActivity.id == activity_id
        ).count() == 1
        observed["pending_binding"] = failing_session.query(
            CropActivityCommandBinding
        ).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 1
        observed["pending_audit"] = failing_session.query(AuditChainEntry).filter(
            AuditChainEntry.entity_id == activity_id,
            AuditChainEntry.action == "ACTIVITY_LOGGED",
        ).count() == 1
        observed["pending_economics"] = failing_session.query(
            CropCycle.total_input_cost
        ).filter(CropCycle.id == uuid.UUID(cycle_id)).scalar() == (
            Decimal(baseline_total or 0) + ACTIVITY_COST
        )
        raise RuntimeError("SYNTHETIC_COMMIT_FAILURE")

    def observe_rollback() -> None:
        observed["rollback_before_close"] = not observed["close_reached"]
        real_rollback()

    def observe_close() -> None:
        observed["close_reached"] = True
        real_close()

    def override_db():
        try:
            yield failing_session
        finally:
            failing_session.close()

    failing_session.commit = fail_commit
    failing_session.rollback = observe_rollback
    failing_session.close = observe_close
    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post(
            f"/api/v1/crop-cycles/{cycle_id}/activities",
            json=payload,
            headers=HEADERS,
        )
        check(response.status_code == 500, "commit failure returns server failure")
    finally:
        app.dependency_overrides.pop(get_db, None)
        failing_session.commit = real_commit
        failing_session.rollback = real_rollback
        failing_session.close = real_close
        real_close()
    check(observed["commit_reached"], "synthetic commit failure was reached")
    check(observed["pending_activity"], "activity was pending before commit failure")
    check(observed["pending_binding"], "binding was pending before commit failure")
    check(observed["pending_audit"], "audit was pending before commit failure")
    check(observed["pending_economics"], "economics were pending before commit failure")
    check(observed["rollback_before_close"], "endpoint rollback preceded dependency close")
    check(observed["close_reached"], "dependency close was observed")
    db = SessionLocal()
    try:
        check(db.query(CropActivity).filter(CropActivity.id == activity_id).count() == 0, "commit failure retains no activity")
        check(db.query(CropActivityCommandBinding).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 0, "commit failure retains no binding")
        check(db.query(AuditChainEntry).filter(AuditChainEntry.entity_id == activity_id).count() == 0, "commit failure retains no business audit")
        surviving_total = db.query(CropCycle.total_input_cost).filter(
            CropCycle.id == uuid.UUID(cycle_id)
        ).scalar()
        check(surviving_total == baseline_total, "commit failure retains no economic change")
    finally:
        db.close()


def assert_traceability_rejections(cycle_id: str, stage_id: str, stage_code: str) -> None:
    suffix = uuid.uuid4().hex[:10].upper()
    db = SessionLocal()
    try:
        canonical_input = db.query(AgriculturalInput).filter(
            AgriculturalInput.is_active == True,
            AgriculturalInput.catalog_status == "PUBLISHED",
        ).first()
        check(canonical_input is not None, "published canonical input exists")
        manufacturer = Manufacturer(
            id=uuid.uuid4(),
            code=f"DIRECT_{suffix}",
            canonical_name="Direct activity regression manufacturer",
            country="India",
            aliases=[],
        )
        first_product = AgriculturalProduct(
            id=uuid.uuid4(),
            code=f"DIRECT_PRODUCT_{suffix}_A",
            canonical_input_id=canonical_input.id,
            manufacturer_id=manufacturer.id,
            brand_name="Direct activity product A",
            status="ACTIVE",
        )
        second_product = AgriculturalProduct(
            id=uuid.uuid4(),
            code=f"DIRECT_PRODUCT_{suffix}_B",
            canonical_input_id=canonical_input.id,
            manufacturer_id=manufacturer.id,
            brand_name="Direct activity product B",
            status="ACTIVE",
        )
        first_package = AgriculturalProductPackage(
            id=uuid.uuid4(),
            product_id=first_product.id,
            sku=f"DIRECT_PACKAGE_{suffix}_A",
            quantity=Decimal("1"),
            unit="KG",
            pack_label="1 kg package A",
            status="ACTIVE",
        )
        second_package = AgriculturalProductPackage(
            id=uuid.uuid4(),
            product_id=second_product.id,
            sku=f"DIRECT_PACKAGE_{suffix}_B",
            quantity=Decimal("1"),
            unit="KG",
            pack_label="1 kg package B",
            status="ACTIVE",
        )
        disabled = ProjectProductApproval(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            product_id=first_product.id,
            enabled=False,
            preferred=False,
            display_order=1,
            reason="Focused package-only denial",
        )
        db.add(manufacturer)
        db.flush()
        db.add_all([first_product, second_product])
        db.flush()
        db.add_all([first_package, second_package, disabled])
        db.commit()
        ids = {
            "first_product": first_product.id,
            "second_product_code": second_product.code,
            "first_package": first_package.id,
            "second_package_sku": second_package.sku,
        }
    finally:
        db.close()

    cases = (
        (
            "package-only disabled product",
            {"package_id": str(ids["first_package"])},
        ),
        (
            "contradictory product selectors",
            {
                "product_id": str(ids["first_product"]),
                "product_code": ids["second_product_code"],
            },
        ),
        (
            "contradictory package selectors",
            {
                "package_id": str(ids["first_package"]),
                "package_sku": ids["second_package_sku"],
            },
        ),
    )
    for label, selectors in cases:
        activity_id = uuid.uuid4()
        payload = activity_payload(activity_id, stage_id, stage_code)
        payload.update(
            {
                "activity_type": "FERTILIZER",
                "input_name": label,
                **selectors,
            }
        )
        response = client.post(
            f"/api/v1/crop-cycles/{cycle_id}/activities",
            json=payload,
            headers=HEADERS,
        )
        check(response.status_code == 422, f"{label} rejects")
        check(response_error(response) == "ACTIVITY_TRACEABILITY_INVALID", f"{label} is sanitized")
        db = SessionLocal()
        try:
            check(db.query(CropActivity).filter(CropActivity.id == activity_id).count() == 0, f"{label} stores no activity")
            check(db.query(CropActivityCommandBinding).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 0, f"{label} stores no binding")
        finally:
            db.close()


def assert_concurrent_commands() -> None:
    same_cycle, same_stage, same_code = create_active_cycle(year_offset=2)
    same_payload = activity_payload(uuid.uuid4(), same_stage, same_code)

    def submit(cycle_id: str, payload: dict) -> tuple[int, str | None]:
        local_client = TestClient(app, raise_server_exceptions=False)
        response = local_client.post(
            f"/api/v1/crop-cycles/{cycle_id}/activities",
            json=payload,
            headers=HEADERS,
        )
        body = response.json() if response.status_code == 201 else {}
        return response.status_code, body.get("outcome")

    def controlled_pair(cycle_id: str, first: dict, second: dict):
        barrier = threading.Barrier(2)
        original = activity_create_service.acquire_direct_activity_locks

        def synchronized_locks(*args, **kwargs):
            barrier.wait(timeout=10)
            return original(*args, **kwargs)

        activity_create_service.acquire_direct_activity_locks = synchronized_locks
        executor = ThreadPoolExecutor(max_workers=2)
        try:
            futures = (
                executor.submit(submit, cycle_id, first),
                executor.submit(submit, cycle_id, second),
            )
            try:
                return [future.result(timeout=20) for future in futures]
            except FutureTimeoutError:
                raise AssertionError("DIRECT_ACTIVITY_CHECK_FAILED:concurrent worker timeout") from None
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            activity_create_service.acquire_direct_activity_locks = original

    results = controlled_pair(same_cycle, same_payload, same_payload)
    check(all(status == 201 for status, _ in results), "concurrent same identity requests succeed")
    check({outcome for _, outcome in results} == {"COMMITTED", "EXACT_REPLAY"}, "concurrent same identity has one commit and one replay")
    db = SessionLocal()
    try:
        same_id = uuid.UUID(same_payload["activity_id"])
        check(db.query(CropActivity).filter(CropActivity.id == same_id).count() == 1, "concurrent same identity stores one activity")
        check(db.query(AuditChainEntry).filter(AuditChainEntry.entity_id == same_id, AuditChainEntry.action == "ACTIVITY_LOGGED").count() == 1, "concurrent same identity stores one audit")
    finally:
        db.close()

    set_cycle_completed(same_cycle)
    distinct_cycle, distinct_stage, distinct_code = create_active_cycle(year_offset=3)
    first = activity_payload(uuid.uuid4(), distinct_stage, distinct_code)
    second = activity_payload(uuid.uuid4(), distinct_stage, distinct_code)
    first["cost_amount"] = "111.25"
    second["cost_amount"] = "222.75"
    results = controlled_pair(distinct_cycle, first, second)
    check(all(result == (201, "COMMITTED") for result in results), "concurrent distinct identities commit")
    db = SessionLocal()
    try:
        cycle = db.query(CropCycle).filter(CropCycle.id == uuid.UUID(distinct_cycle)).one()
        check(cycle.total_input_cost == Decimal("334.00"), "concurrent distinct costs are not lost")
    finally:
        db.close()
    set_cycle_completed(distinct_cycle)


def assert_stage_change_during_command() -> None:
    cycle_id, stage_id, stage_code = create_active_cycle(year_offset=4)
    payload = activity_payload(uuid.uuid4(), stage_id, stage_code)
    entered = threading.Event()
    release = threading.Event()
    original = activity_create_service._resolve_active_stage

    def controlled_resolve(*args, **kwargs):
        entered.set()
        check(release.wait(timeout=10), "controlled stage race released")
        return original(*args, **kwargs)

    activity_create_service._resolve_active_stage = controlled_resolve
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(
            client.post,
            f"/api/v1/crop-cycles/{cycle_id}/activities",
            json=payload,
            headers=HEADERS,
        )
        check(entered.wait(timeout=10), "activity reached controlled stage boundary")
        db = SessionLocal()
        try:
            stage = db.query(activity_create_service.CropStageInstance).filter(
                activity_create_service.CropStageInstance.id == uuid.UUID(stage_id)
            ).one()
            stage.status = "COMPLETED"
            stage.actual_end_date = date.today()
            db.commit()
        finally:
            db.close()
        release.set()
        try:
            response = future.result(timeout=15)
        except FutureTimeoutError:
            raise AssertionError("DIRECT_ACTIVITY_CHECK_FAILED:stage worker timeout") from None
        check(response.status_code == 409, "stage change before selection rejects command")
        check(response_error(response) == "ACTIVITY_CONTEXT_INVALID", "stage race rejection is sanitized")
    finally:
        release.set()
        executor.shutdown(wait=False, cancel_futures=True)
        activity_create_service._resolve_active_stage = original
    db = SessionLocal()
    try:
        activity_id = uuid.UUID(payload["activity_id"])
        check(db.query(CropActivity).filter(CropActivity.id == activity_id).count() == 0, "stage race stores no activity")
        check(db.query(CropActivityCommandBinding).filter(CropActivityCommandBinding.activity_id == activity_id).count() == 0, "stage race stores no binding")
    finally:
        db.close()


def assert_unsupported_sync_operations(cycle_id: str, payload: dict) -> None:
    for entity_type in ("crop_activity", "cropactivity"):
        for operation, code in (
            ("UPDATE", "ACTIVITY_OPERATION_UNSUPPORTED"),
            ("DELETE", "ACTIVITY_OPERATION_UNSUPPORTED"),
        ):
            event_id = uuid.uuid4()
            event = {
                "event_id": str(event_id),
                "entity_type": entity_type,
                "entity_id": payload["activity_id"],
                "operation": operation,
                "payload": {**payload, "farmer_id": str(FARMER_ID), "crop_cycle_id": cycle_id},
                "version": 1,
                "dependency_ids": [],
                "metadata": {},
            }
            response = client.post("/api/v1/sync/events", json={"events": [event]}, headers=HEADERS)
            check(response.status_code == 422, f"{entity_type} {operation} remains blocked")
            check(response.json()["detail"]["error"] == code, f"{entity_type} {operation} block code")
            db = SessionLocal()
            try:
                check(db.query(CropActivitySyncEventBinding).filter(CropActivitySyncEventBinding.event_id == event_id).count() == 0, "Blocked sync creates no binding")
                check(db.query(SyncProcessedEvent).filter(SyncProcessedEvent.event_id == event_id).count() == 0, "Blocked sync creates no ledger")
            finally:
                db.close()


def main() -> int:
    print("=" * 72)
    print("DIRECT CROP-ACTIVITY COMMAND FOCUSED REGRESSION")
    print("=" * 72)
    admit_actual_database()
    reset_fixture()
    user_id = install_test_admin()
    try:
        cycle_id, stage_id, stage_code = create_active_cycle()
        payload = activity_payload(uuid.uuid4(), stage_id, stage_code)

        invalid = client.post(
            f"/api/v1/crop-cycles/{cycle_id}/activities",
            json={**payload, "unknown_field": True},
            headers=HEADERS,
        )
        check(invalid.status_code == 422, "Unknown activity field rejects")
        check(response_error(invalid) == "ACTIVITY_PAYLOAD_INVALID", "Invalid payload sanitized")
        assert_decimal_ingress_rejections(cycle_id, stage_id, stage_code)

        first = assert_first_commit(cycle_id, payload)
        current_total, second_activity_id = assert_second_activity(cycle_id, payload)
        assert_current_read_contracts(
            client=client,
            headers=HEADERS,
            cycle_id=cycle_id,
            activity_ids={payload["activity_id"], second_activity_id},
            expected_total=current_total,
        )
        assert_exact_replay(cycle_id, payload, first, current_total)
        assert_tamper_fails_closed(cycle_id, payload)
        boundary_cycle, boundary_stage, boundary_code = assert_identity_boundaries(cycle_id, payload)
        assert_commit_failure_rolls_back(boundary_cycle, boundary_stage, boundary_code)
        assert_traceability_rejections(boundary_cycle, boundary_stage, boundary_code)
        set_cycle_completed(boundary_cycle)
        assert_concurrent_commands()
        assert_stage_change_during_command()
        assert_unsupported_sync_operations(cycle_id, payload)
    finally:
        cleanup_test_admin(user_id)
    print("DIRECT_CROP_ACTIVITY_COMMAND_FOCUSED_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except AssertionError as exc:
        message = str(exc)
        if message.startswith((
            "DIRECT_ACTIVITY_CHECK_FAILED:",
            "DIRECT_ACTIVITY_READ_CONTRACT_FAILED:",
        )):
            print(message)
        else:
            print("DIRECT_ACTIVITY_ASSERTION_FAILURE:AssertionError")
        raise SystemExit(1)
    except BaseException as exc:
        print(f"DIRECT_ACTIVITY_UNEXPECTED_FAILURE:{type(exc).__name__}")
        raise SystemExit(1)
