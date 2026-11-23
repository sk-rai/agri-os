"""Transactional crop-activity CREATE command service.

Direct and queued entry points use this same command core.  Entry-point-specific
ledger and response effects remain outside it.  This module never commits its
SQLAlchemy session.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.modules.sync.models import AuditChainEntry, CropActivityCommandBinding
from app.modules.workflow.activity_command import (
    ACTIVITY_RESULT_VERSION,
    CanonicalActivityIntent,
    CropActivityCreateCommand,
    canonicalize_activity_intent,
    normalize_activity_command,
)
from app.modules.workflow.models import CropActivity, CropCycle, CropStageInstance


_ACTIVITY_LOCK_NAMESPACE = b"crop-activity-v1"
_CYCLE_LOCK_NAMESPACE = b"crop-cycle-v1"


class ActivityCommandError(RuntimeError):
    """Fixed, sanitized command failure suitable for an API boundary."""

    def __init__(self, code: str, status_code: int, message: str):
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.public_message = message


@dataclass(frozen=True)
class ResolvedActivityTraceability:
    input_code: str | None
    product_id: uuid.UUID | None
    product_code: str | None
    package_id: uuid.UUID | None
    package_sku: str | None


@dataclass(frozen=True)
class ActivityCommandResult:
    outcome: str
    intent: CanonicalActivityIntent
    payload: dict


AuthorizeFarmer = Callable[[uuid.UUID], None]
ResolveTraceability = Callable[
    [CropCycle, CropActivityCreateCommand],
    ResolvedActivityTraceability,
]
AppendBusinessAudit = Callable[[uuid.UUID, dict, dict], None]


def _identity_unavailable() -> ActivityCommandError:
    return ActivityCommandError(
        "ACTIVITY_ID_REUSE",
        409,
        "Activity identity is unavailable.",
    )


def _context_invalid(message: str) -> ActivityCommandError:
    return ActivityCommandError("ACTIVITY_CONTEXT_INVALID", 409, message)


def _lock_key(namespace: bytes, identity: uuid.UUID) -> int:
    digest = hashlib.sha256(namespace + identity.bytes).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _advisory_lock(db: Session, namespace: bytes, identity: uuid.UUID) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _lock_key(namespace, identity)},
    )


def acquire_direct_activity_locks(
    db: Session,
    *,
    activity_id: uuid.UUID,
    crop_cycle_id: uuid.UUID,
) -> None:
    """Acquire DIRECT's ACTIVITY -> CYCLE lock classes in fixed order."""

    _advisory_lock(db, _ACTIVITY_LOCK_NAMESPACE, activity_id)
    _advisory_lock(db, _CYCLE_LOCK_NAMESPACE, crop_cycle_id)


def acquire_activity_identity_locks(
    db: Session,
    identities: set[uuid.UUID],
) -> None:
    """Acquire a transaction-wide sorted ACTIVITY lock set."""

    for identity in sorted(identities, key=str):
        _advisory_lock(db, _ACTIVITY_LOCK_NAMESPACE, identity)


def acquire_cycle_identity_locks(
    db: Session,
    identities: set[uuid.UUID],
) -> None:
    """Acquire a transaction-wide sorted CYCLE lock set after activity locks."""

    for identity in sorted(identities, key=str):
        _advisory_lock(db, _CYCLE_LOCK_NAMESPACE, identity)


def _load_locked_cycle(
    db: Session,
    *,
    tenant_id: str,
    cycle_id: uuid.UUID,
) -> CropCycle:
    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.id == cycle_id, CropCycle.tenant_id == tenant_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if cycle is None:
        raise _context_invalid("Crop cycle is unavailable.")
    db.refresh(cycle)
    return cycle


def _resolve_active_stage(
    db: Session,
    *,
    tenant_id: str,
    cycle_id: uuid.UUID,
    requested_id: uuid.UUID | None,
    requested_code: str | None,
) -> CropStageInstance | None:
    active = (
        db.query(CropStageInstance)
        .filter(
            CropStageInstance.crop_cycle_id == cycle_id,
            CropStageInstance.tenant_id == tenant_id,
            CropStageInstance.status == "ACTIVE",
        )
        .order_by(CropStageInstance.stage_order.desc())
        .populate_existing()
        .with_for_update()
        .all()
    )
    if len(active) > 1:
        raise _context_invalid("Crop cycle has an ambiguous active stage.")
    selected = active[0] if active else None
    if selected is None:
        if requested_id is not None or requested_code is not None:
            raise _context_invalid("Requested stage is not the active cycle stage.")
        return None
    if requested_id is not None and requested_id != selected.id:
        raise _context_invalid("Requested stage is not the active cycle stage.")
    if requested_code is not None and requested_code != selected.stage_code:
        raise _context_invalid("Requested stage is not the active cycle stage.")
    return selected


def _validate_field_relationships(command: CropActivityCreateCommand) -> None:
    if command.activity_type == "IRRIGATION":
        return
    if command.irrigation_source is not None or command.duration_hours is not None:
        raise ActivityCommandError(
            "ACTIVITY_PAYLOAD_INVALID",
            422,
            "Irrigation fields require an irrigation activity.",
        )


def _binding_matches(
    binding: CropActivityCommandBinding,
    command: CropActivityCreateCommand,
    intent: CanonicalActivityIntent,
) -> bool:
    expected_origin = "SYNC" if command.queued_origin is not None else "DIRECT"
    expected_event_id = (
        command.queued_origin.event_id if command.queued_origin is not None else None
    )
    return (
        binding.origin_kind == expected_origin
        and binding.origin_event_id == expected_event_id
        and binding.tenant_id == command.tenant_id
        and binding.actor_id == command.actor_id
        and binding.farmer_id == command.farmer_id
        and binding.crop_cycle_id == command.crop_cycle_id
        and binding.intent_version == intent.version
        and binding.intent_canonical == intent.canonical_text
        and binding.intent_sha256 == intent.sha256
    )


def _persisted_activity_snapshot(activity: CropActivity) -> dict:
    def utc_timestamp(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "activity_id": str(activity.id),
        "tenant_id": activity.tenant_id,
        "farmer_id": str(activity.farmer_id),
        "crop_cycle_id": str(activity.crop_cycle_id),
        "stage_instance_id": str(activity.stage_instance_id) if activity.stage_instance_id else None,
        "activity_type": activity.activity_type,
        "activity_date": activity.activity_date.isoformat(),
        "input_code": activity.input_code,
        "input_name": activity.input_name,
        "input_rule_id": str(activity.input_rule_id) if activity.input_rule_id else None,
        "product_id": str(activity.product_id) if activity.product_id else None,
        "product_code": activity.product_code,
        "package_id": str(activity.package_id) if activity.package_id else None,
        "package_sku": activity.package_sku,
        "quantity": str(activity.quantity) if activity.quantity is not None else None,
        "quantity_unit": activity.quantity_unit,
        "area_applied": str(activity.area_applied) if activity.area_applied is not None else None,
        "area_unit": activity.area_unit,
        "recommended_quantity": str(activity.recommended_quantity) if activity.recommended_quantity is not None else None,
        "recommended_quantity_unit": activity.recommended_quantity_unit,
        "actual_quantity": str(activity.actual_quantity) if activity.actual_quantity is not None else None,
        "actual_quantity_unit": activity.actual_quantity_unit,
        "dosage_variance_reason": activity.dosage_variance_reason,
        "cost_amount": str(activity.cost_amount) if activity.cost_amount is not None else None,
        "cost_currency": activity.cost_currency,
        "gps_lat": str(activity.gps_lat) if activity.gps_lat is not None else None,
        "gps_lng": str(activity.gps_lng) if activity.gps_lng is not None else None,
        "irrigation_source": activity.irrigation_source,
        "duration_hours": str(activity.duration_hours) if activity.duration_hours is not None else None,
        "logged_by": str(activity.logged_by),
        "logging_method": activity.logging_method,
        "notes": activity.notes,
        "version": activity.version,
        "is_active": activity.is_active,
        "created_at": utc_timestamp(activity.created_at),
        "updated_at": utc_timestamp(activity.updated_at),
    }


def _replay_result(
    db: Session,
    *,
    activity: CropActivity | None,
    binding: CropActivityCommandBinding,
    command: CropActivityCreateCommand,
    intent: CanonicalActivityIntent,
) -> ActivityCommandResult:
    if activity is None or activity.id != binding.activity_id:
        raise _identity_unavailable()
    if not _binding_matches(binding, command, intent):
        raise _identity_unavailable()
    if binding.result_version != ACTIVITY_RESULT_VERSION:
        raise _identity_unavailable()
    if binding.resolved_stage_id != activity.stage_instance_id:
        raise _identity_unavailable()
    retained = dict(binding.result_payload or {})
    payload = retained.get("response")
    persisted = retained.get("persisted_activity")
    if not isinstance(payload, dict) or not isinstance(persisted, dict):
        raise _identity_unavailable()
    if payload.get("activity_id") != str(command.activity_id):
        raise _identity_unavailable()
    if persisted.get("activity_id") != str(command.activity_id):
        raise _identity_unavailable()
    if persisted.get("tenant_id") != command.tenant_id:
        raise _identity_unavailable()
    if persisted.get("farmer_id") != str(command.farmer_id):
        raise _identity_unavailable()
    if persisted.get("crop_cycle_id") != str(command.crop_cycle_id):
        raise _identity_unavailable()
    if retained.get("audit_correlation_id") != str(binding.audit_correlation_id):
        raise _identity_unavailable()
    if persisted != _persisted_activity_snapshot(activity):
        raise _identity_unavailable()
    expected_response_keys = {
        "activity_id",
        "activity_type",
        "input_rule_id",
        "product_code",
        "package_sku",
        "stage_code",
        "cycle_total_input_cost",
        "events_published",
    }
    if set(payload) != expected_response_keys:
        raise _identity_unavailable()
    if payload.get("activity_type") != activity.activity_type:
        raise _identity_unavailable()
    if payload.get("input_rule_id") != persisted.get("input_rule_id"):
        raise _identity_unavailable()
    if payload.get("product_code") != activity.product_code:
        raise _identity_unavailable()
    if payload.get("package_sku") != activity.package_sku:
        raise _identity_unavailable()
    retained_total = retained.get("cycle_total_input_cost")
    if not isinstance(retained_total, str) or payload.get("cycle_total_input_cost") != retained_total:
        raise _identity_unavailable()
    if payload.get("events_published") != ["crop_activity_logged.v1"]:
        raise _identity_unavailable()
    stage_code = None
    if activity.stage_instance_id is not None:
        stage_code = db.query(CropStageInstance.stage_code).filter(
            CropStageInstance.id == activity.stage_instance_id,
            CropStageInstance.tenant_id == command.tenant_id,
            CropStageInstance.crop_cycle_id == command.crop_cycle_id,
        ).scalar()
        if stage_code is None:
            raise _identity_unavailable()
    if payload.get("stage_code") != stage_code:
        raise _identity_unavailable()
    audit_count = db.query(AuditChainEntry).filter(
        AuditChainEntry.tenant_id == command.tenant_id,
        AuditChainEntry.actor_id == command.actor_id,
        AuditChainEntry.correlation_id == binding.audit_correlation_id,
        AuditChainEntry.entity_type == "crop_activity",
        AuditChainEntry.entity_id == command.activity_id,
        AuditChainEntry.action == "ACTIVITY_LOGGED",
    ).count()
    if audit_count != 1:
        raise _identity_unavailable()
    return ActivityCommandResult(
        outcome="EXACT_REPLAY",
        intent=intent,
        payload=dict(payload),
    )


def execute_activity_create(
    db: Session,
    *,
    command: CropActivityCreateCommand,
    authorize_farmer: AuthorizeFarmer,
    resolve_traceability: ResolveTraceability,
    append_business_audit: AppendBusinessAudit,
) -> ActivityCommandResult:
    """Execute or exactly replay one canonical activity command without commit."""
    try:
        normalized_command = normalize_activity_command(command)
        intent = canonicalize_activity_intent(normalized_command)
    except ValueError as exc:
        raise ActivityCommandError(
            "ACTIVITY_PAYLOAD_INVALID",
            422,
            "Activity request validation failed.",
        ) from exc
    command = normalized_command
    acquire_direct_activity_locks(
        db,
        activity_id=command.activity_id,
        crop_cycle_id=command.crop_cycle_id,
    )
    cycle = _load_locked_cycle(
        db,
        tenant_id=command.tenant_id,
        cycle_id=command.crop_cycle_id,
    )
    authorize_farmer(cycle.farmer_id)
    if cycle.farmer_id != command.farmer_id:
        raise _context_invalid("Activity farmer does not match the crop cycle.")

    binding = db.query(CropActivityCommandBinding).filter(
        CropActivityCommandBinding.activity_id == command.activity_id
    ).first()
    activity = db.query(CropActivity).filter(CropActivity.id == command.activity_id).first()
    if binding is not None:
        return _replay_result(
            db,
            activity=activity,
            binding=binding,
            command=command,
            intent=intent,
        )
    if activity is not None:
        raise _identity_unavailable()

    if cycle.status in {"COMPLETED", "ABANDONED", "ARCHIVED"}:
        raise _context_invalid("Crop cycle is read-only.")
    _validate_field_relationships(command)
    stage = _resolve_active_stage(
        db,
        tenant_id=command.tenant_id,
        cycle_id=command.crop_cycle_id,
        requested_id=command.requested_stage_id,
        requested_code=command.requested_stage_code,
    )
    trace = resolve_traceability(cycle, command)
    now = datetime.now(timezone.utc)
    activity = CropActivity(
        id=command.activity_id,
        crop_cycle_id=command.crop_cycle_id,
        stage_instance_id=stage.id if stage else None,
        tenant_id=command.tenant_id,
        farmer_id=command.farmer_id,
        activity_type=command.activity_type,
        input_code=trace.input_code,
        input_name=command.input_name,
        quantity=command.quantity,
        quantity_unit=command.quantity_unit,
        area_applied=command.area_applied,
        area_unit=command.area_unit,
        input_rule_id=command.input_rule_id,
        product_id=trace.product_id,
        product_code=trace.product_code,
        package_id=trace.package_id,
        package_sku=trace.package_sku,
        recommended_quantity=command.recommended_quantity,
        recommended_quantity_unit=command.recommended_quantity_unit,
        actual_quantity=command.actual_quantity,
        actual_quantity_unit=command.actual_quantity_unit,
        dosage_variance_reason=command.dosage_variance_reason,
        cost_amount=command.cost_amount,
        cost_currency=command.cost_currency or "INR",
        activity_date=command.activity_date,
        gps_lat=command.gps_lat,
        gps_lng=command.gps_lng,
        irrigation_source=command.irrigation_source,
        duration_hours=command.duration_hours,
        logged_by=command.actor_id,
        notes=command.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(activity)
    db.flush()
    db.refresh(activity)

    total = db.query(
        func.coalesce(func.sum(CropActivity.cost_amount), Decimal("0"))
    ).filter(
        CropActivity.tenant_id == command.tenant_id,
        CropActivity.crop_cycle_id == command.crop_cycle_id,
    ).scalar()
    cycle.total_input_cost = Decimal(total or 0)
    cycle.updated_at = now

    correlation_id = uuid.uuid4()
    audit_payload = {
        "activity_type": command.activity_type,
        "input_code": trace.input_code,
        "input_rule_id": str(command.input_rule_id) if command.input_rule_id else None,
        "product_code": trace.product_code,
        "package_sku": trace.package_sku,
        "quantity": str(command.quantity) if command.quantity is not None else None,
        "cost": str(command.cost_amount) if command.cost_amount is not None else None,
        "stage_code": stage.stage_code if stage else None,
    }
    audit_metadata = {
        "gps_lat": str(command.gps_lat) if command.gps_lat is not None else None,
        "gps_lng": str(command.gps_lng) if command.gps_lng is not None else None,
        "cycle_id": str(command.crop_cycle_id),
    }
    append_business_audit(correlation_id, audit_payload, audit_metadata)

    payload = {
        "activity_id": str(activity.id),
        "activity_type": activity.activity_type,
        "input_rule_id": str(activity.input_rule_id) if activity.input_rule_id else None,
        "product_code": activity.product_code,
        "package_sku": activity.package_sku,
        "stage_code": stage.stage_code if stage else None,
        "cycle_total_input_cost": str(cycle.total_input_cost or 0),
        "events_published": ["crop_activity_logged.v1"],
    }
    persisted_activity = _persisted_activity_snapshot(activity)
    retained_result = {
        "response": payload,
        "persisted_activity": persisted_activity,
        "cycle_total_input_cost": str(cycle.total_input_cost or 0),
        "audit_correlation_id": str(correlation_id),
    }
    db.add(
        CropActivityCommandBinding(
            activity_id=activity.id,
            tenant_id=command.tenant_id,
            actor_id=command.actor_id,
            farmer_id=command.farmer_id,
            crop_cycle_id=command.crop_cycle_id,
            origin_kind="SYNC" if command.queued_origin is not None else "DIRECT",
            origin_event_id=(
                command.queued_origin.event_id
                if command.queued_origin is not None
                else None
            ),
            intent_version=intent.version,
            intent_canonical=intent.canonical_text,
            intent_sha256=intent.sha256,
            resolved_stage_id=stage.id if stage else None,
            result_version=ACTIVITY_RESULT_VERSION,
            result_payload=retained_result,
            audit_correlation_id=correlation_id,
            created_at=now,
        )
    )
    db.flush()
    return ActivityCommandResult(outcome="COMMITTED", intent=intent, payload=payload)


def execute_direct_activity_create(
    db: Session,
    *,
    command: CropActivityCreateCommand,
    authorize_farmer: AuthorizeFarmer,
    resolve_traceability: ResolveTraceability,
    append_business_audit: AppendBusinessAudit,
) -> ActivityCommandResult:
    """Compatibility wrapper that admits only the direct command origin."""

    if command.queued_origin is not None:
        raise ActivityCommandError(
            "ACTIVITY_PAYLOAD_INVALID", 422, "Direct activity origin is invalid."
        )
    return execute_activity_create(
        db,
        command=command,
        authorize_farmer=authorize_farmer,
        resolve_traceability=resolve_traceability,
        append_business_audit=append_business_audit,
    )
