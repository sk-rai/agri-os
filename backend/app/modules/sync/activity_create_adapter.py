"""Queued crop-activity CREATE adapter for the canonical command service.

This module is imported lazily by the sync batch loop.  It owns the queued
ledger and correlation effects so activity CREATE never enters the legacy
generic replay or materialization paths.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.modules.sync.models import (
    CropActivityCommandBinding,
    CropActivitySyncEventBinding,
    SyncProcessedEvent,
)
from app.modules.workflow.activity_command import (
    CropActivityCreateCommand,
    QueuedActivityOrigin,
    canonicalize_activity_intent,
    normalize_activity_command,
)
from app.modules.workflow.activity_create_service import (
    ActivityCommandError,
    ResolvedActivityTraceability,
    execute_activity_create,
)


AuthorizeFarmer = Callable[[uuid.UUID], None]
AppendAudit = Callable[..., str]
ValidateDependencies = Callable[[], list[str]]


def _invalid(code: str = "ACTIVITY_PAYLOAD_INVALID") -> ActivityCommandError:
    return ActivityCommandError(code, 422, "Queued activity request is invalid.")


def _required_uuid(payload: dict, name: str) -> uuid.UUID:
    value = payload.get(name)
    if value is None:
        raise _invalid()
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        raise _invalid()


def _command_from_event(
    *,
    tenant_id: str,
    actor_id: str,
    event,
) -> CropActivityCreateCommand:
    from app.modules.workflow.activity_schema import ActivityCreate

    payload = dict(event.payload or {})
    farmer_id = _required_uuid(payload, "farmer_id")
    crop_cycle_id = _required_uuid(payload, "crop_cycle_id")
    payload_activity_id = _required_uuid(payload, "activity_id")
    if event.entity_id is None:
        raise _invalid()
    try:
        entity_id = uuid.UUID(str(event.entity_id))
    except (TypeError, ValueError):
        raise _invalid()
    if entity_id != payload_activity_id:
        raise _invalid("ACTIVITY_ID_MISMATCH")

    for key in ("farmer_id", "crop_cycle_id"):
        payload.pop(key, None)
    try:
        body = ActivityCreate.model_validate(payload)
    except ValidationError as exc:
        raise _invalid() from exc
    if body.activity_id != entity_id:
        raise _invalid("ACTIVITY_ID_MISMATCH")

    return CropActivityCreateCommand(
        tenant_id=tenant_id,
        actor_id=uuid.UUID(actor_id),
        farmer_id=farmer_id,
        crop_cycle_id=crop_cycle_id,
        activity_id=entity_id,
        requested_stage_id=body.requested_stage_id,
        requested_stage_code=body.requested_stage_code,
        activity_type=body.activity_type,
        activity_date=body.activity_date,
        input_code=body.input_code,
        input_name=body.input_name,
        input_rule_id=body.input_rule_id,
        product_id=body.product_id,
        product_code=body.product_code,
        package_id=body.package_id,
        package_sku=body.package_sku,
        quantity=body.quantity,
        quantity_unit=body.quantity_unit,
        area_applied=body.area_applied,
        area_unit=body.area_unit,
        recommended_quantity=body.recommended_quantity,
        recommended_quantity_unit=body.recommended_quantity_unit,
        actual_quantity=body.actual_quantity,
        actual_quantity_unit=body.actual_quantity_unit,
        dosage_variance_reason=body.dosage_variance_reason,
        cost_amount=body.cost_amount,
        cost_currency=body.cost_currency,
        gps_lat=body.gps_lat,
        gps_lng=body.gps_lng,
        irrigation_source=body.irrigation_source,
        duration_hours=body.duration_hours,
        notes=body.notes,
        queued_origin=QueuedActivityOrigin(
            event_id=uuid.UUID(str(event.event_id)),
            entity_type=event.entity_type,
            operation=event.operation,
            client_version=event.client_version,
            dependency_ids=tuple(uuid.UUID(str(value)) for value in event.dependency_ids),
            sync_envelope_canonical=event.sync_envelope_canonical,
        ),
    )


def _verify_replay_rows(
    db: Session,
    *,
    tenant_id: str,
    actor_id: str,
    event,
    activity_id: uuid.UUID,
    farmer_id: uuid.UUID,
    crop_cycle_id: uuid.UUID,
    intent,
) -> bool:
    event_id = uuid.UUID(str(event.event_id))
    processed = db.query(SyncProcessedEvent).filter(
        SyncProcessedEvent.event_id == event_id
    ).first()
    binding = db.query(CropActivitySyncEventBinding).filter(
        CropActivitySyncEventBinding.event_id == event_id
    ).first()
    command_bindings = db.query(CropActivityCommandBinding).filter(
        CropActivityCommandBinding.origin_kind == "SYNC",
        CropActivityCommandBinding.origin_event_id == event_id,
    ).all()
    command_binding = command_bindings[0] if len(command_bindings) == 1 else None
    present = (
        processed is not None,
        binding is not None,
        len(command_bindings) == 1,
    )
    if not any(present) and not command_bindings:
        return False
    if (
        not all(present)
        or processed is None
        or binding is None
        or command_binding is None
        or len(command_bindings) != 1
        or processed.tenant_id != tenant_id
        or processed.actor_id != uuid.UUID(actor_id)
        or processed.entity_type != event.entity_type
        or processed.entity_id != activity_id
        or processed.operation != "CREATE"
        or processed.server_version != event.client_version
        or processed.status != "COMMITTED"
        or binding.tenant_id != tenant_id
        or binding.actor_id != uuid.UUID(actor_id)
        or binding.activity_id != activity_id
        or binding.intent_version != intent.version
        or binding.intent_canonical != intent.canonical_text
        or binding.intent_sha256 != intent.sha256
        or binding.outcome != "COMMITTED"
        or command_binding.activity_id != activity_id
        or command_binding.tenant_id != tenant_id
        or command_binding.actor_id != uuid.UUID(actor_id)
        or command_binding.farmer_id != farmer_id
        or command_binding.crop_cycle_id != crop_cycle_id
        or command_binding.origin_event_id != event_id
        or command_binding.intent_version != intent.version
        or command_binding.intent_canonical != intent.canonical_text
        or command_binding.intent_sha256 != intent.sha256
    ):
        raise ActivityCommandError(
            "EVENT_ID_REUSE", 409, "Sync event identity is unavailable."
        )
    return True


def process_queued_activity_create(
    db: Session,
    *,
    tenant_id: str,
    actor_id: str,
    event,
    authorize_farmer: AuthorizeFarmer,
    append_audit: AppendAudit,
    validate_dependencies: ValidateDependencies,
) -> dict:
    """Commit or exactly replay one queued CREATE inside the caller savepoint."""

    command = _command_from_event(
        tenant_id=tenant_id,
        actor_id=actor_id,
        event=event,
    )
    try:
        normalized_command = normalize_activity_command(command)
        expected_intent = canonicalize_activity_intent(normalized_command)
    except ValueError as exc:
        raise _invalid() from exc

    def resolve_traceability(cycle, normalized):
        from app.modules.workflow.api import (
            _validate_activity_traceability,
            assert_catalog_input_allowed_for_project_crop,
        )

        try:
            traceability = _validate_activity_traceability(
                db,
                tenant_id=tenant_id,
                cycle=cycle,
                body=normalized,
            )
            input_code = traceability["input_code"] or normalized.input_code
            assert_catalog_input_allowed_for_project_crop(
                db,
                tenant_id=tenant_id,
                project_id=cycle.project_id,
                crop_code=cycle.crop_code,
                input_code=input_code,
            )
        except Exception as exc:
            from fastapi import HTTPException

            if not isinstance(exc, HTTPException):
                raise
            raise ActivityCommandError(
                "ACTIVITY_TRACEABILITY_INVALID",
                422,
                "Activity traceability selection is invalid.",
            ) from exc
        product = traceability["product"]
        package = traceability["package"]
        return ResolvedActivityTraceability(
            input_code=input_code,
            product_id=product.id if product else normalized.product_id,
            product_code=traceability["product_code"],
            package_id=package.id if package else normalized.package_id,
            package_sku=traceability["package_sku"],
        )

    def append_business_audit(correlation_id, payload, metadata):
        append_audit(
            db,
            tenant_id,
            actor_id,
            str(correlation_id),
            "crop_activity",
            str(command.activity_id),
            "ACTIVITY_LOGGED",
            payload,
            metadata,
        )

    event_id = uuid.UUID(str(event.event_id))
    occupied_replay = _verify_replay_rows(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        event=event,
        activity_id=normalized_command.activity_id,
        farmer_id=normalized_command.farmer_id,
        crop_cycle_id=normalized_command.crop_cycle_id,
        intent=expected_intent,
    )
    if not occupied_replay and validate_dependencies():
        raise ActivityCommandError(
            "DEPENDENCY_MISSING",
            409,
            "Queued activity dependencies are unavailable.",
        )

    def reauthorize_farmer(farmer_id: uuid.UUID) -> None:
        try:
            authorize_farmer(farmer_id)
        except Exception as exc:
            from fastapi import HTTPException

            if not isinstance(exc, HTTPException):
                raise
            raise ActivityCommandError(
                "ACTIVITY_AUTHORIZATION_DENIED",
                403,
                "Queued activity authorization was denied.",
            ) from exc

    command_result = execute_activity_create(
        db,
        command=command,
        authorize_farmer=reauthorize_farmer,
        resolve_traceability=resolve_traceability,
        append_business_audit=append_business_audit,
    )
    if command_result.outcome == "EXACT_REPLAY":
        _verify_replay_rows(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            event=event,
            activity_id=normalized_command.activity_id,
            farmer_id=normalized_command.farmer_id,
            crop_cycle_id=normalized_command.crop_cycle_id,
            intent=command_result.intent,
        )
    else:
        if occupied_replay:
            raise ActivityCommandError(
                "EVENT_ID_REUSE", 409, "Sync event identity is unavailable."
            )
        now = datetime.now(timezone.utc)
        db.add(
            SyncProcessedEvent(
                event_id=event_id,
                tenant_id=tenant_id,
                actor_id=uuid.UUID(actor_id),
                entity_type=event.entity_type,
                entity_id=command.activity_id,
                operation="CREATE",
                server_version=event.client_version,
                processed_at=now,
                status="COMMITTED",
            )
        )
        db.flush()
        db.add(
            CropActivitySyncEventBinding(
                event_id=event_id,
                tenant_id=tenant_id,
                actor_id=uuid.UUID(actor_id),
                activity_id=command.activity_id,
                intent_version=command_result.intent.version,
                intent_canonical=command_result.intent.canonical_text,
                intent_sha256=command_result.intent.sha256,
                outcome="COMMITTED",
                created_at=now,
            )
        )
        append_audit(
            db,
            tenant_id,
            actor_id,
            str(uuid.uuid4()),
            event.entity_type,
            str(command.activity_id),
            "SYNC_COMMIT",
            {},
            {
                "sync_event_id": str(event_id),
                "activity_id": str(command.activity_id),
                "outcome": "COMMITTED",
                "intent_version": command_result.intent.version,
                "intent_sha256": command_result.intent.sha256,
            },
        )
        db.flush()

    return {
        "event_id": str(event_id),
        "entity_type": event.entity_type,
        "entity_id": str(command.activity_id),
        "activity_id": str(command.activity_id),
        "outcome": command_result.outcome,
        "intent_version": command_result.intent.version,
        "intent_sha256": command_result.intent.sha256,
    }
