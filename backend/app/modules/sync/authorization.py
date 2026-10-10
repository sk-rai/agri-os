"""Persona authorization for operational offline sync events."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, ROLE_PERMISSIONS
from app.core.human_auth import AuthenticatedPrincipal
from app.core.human_persona_scope import resolve_human_persona_scope
from app.modules.auth.models import User
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
    Parcel,
)
from app.modules.farmer.soil_profile import SoilProfile
from app.modules.media.models import (
    FieldEventReport,
    QueryMessage,
    QueryThread,
)
from app.modules.workflow.models import (
    CropActivity,
    CropCycle,
    CropStageInstance,
)


SYNC_WEB_ADMIN_ROLES = {
    "ENTERPRISE_ADMIN",
    "MANAGER",
    "ADMIN_EDITOR",
    "ADMIN_PUBLISHER",
}


def _uuid_or_none(value):
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _value(payload: dict, *keys: str):
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _normalized_mobile(value) -> str:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


def _is_admin(principal: AuthenticatedPrincipal) -> bool:
    role = str(principal.role or "").upper()
    return (
        role in SYNC_WEB_ADMIN_ROLES
        and AdminPermission.EDIT in ROLE_PERMISSIONS.get(role, set())
    )


def _existing_farmer_id(
    db: Session,
    tenant_id: str,
    event: dict,
):
    payload = event.get("payload") or {}
    entity_type = str(event.get("entity_type") or "").lower()
    entity_id = _uuid_or_none(event.get("entity_id"))

    if entity_type == "farmer":
        farmer_id = entity_id or _uuid_or_none(
            _value(payload, "id", "farmer_id", "farmerId")
        )
        if farmer_id:
            row = db.query(Farmer.id).filter(
                Farmer.id == farmer_id,
                Farmer.tenant_id == tenant_id,
            ).first()
            if row:
                return row[0]
        mobile = _value(payload, "mobile_number", "mobileNumber", "phone")
        if mobile:
            rows = db.query(Farmer.id, Farmer.mobile_number).filter(
                Farmer.tenant_id == tenant_id,
                Farmer.status != "ARCHIVED",
            ).all()
            wanted = _normalized_mobile(mobile)
            for row_id, row_mobile in rows:
                if _normalized_mobile(row_mobile) == wanted:
                    return row_id
        return None

    if entity_type == "parcel":
        if entity_id:
            row = db.query(Parcel.farmer_id).filter(
                Parcel.id == entity_id,
                Parcel.tenant_id == tenant_id,
            ).first()
            if row:
                return row[0]
        return _uuid_or_none(_value(payload, "farmer_id", "farmerId"))

    if entity_type in {"parcel_geometry", "parcelgeometry"}:
        parcel_id = entity_id or _uuid_or_none(
            _value(payload, "parcel_id", "parcelId")
        )
        if parcel_id:
            row = db.query(Parcel.farmer_id).filter(
                Parcel.id == parcel_id,
                Parcel.tenant_id == tenant_id,
            ).first()
            return row[0] if row else None

    if entity_type in {"soil_profile", "soilprofile"}:
        if entity_id:
            row = db.query(SoilProfile.farmer_id).filter(
                SoilProfile.id == entity_id,
                SoilProfile.tenant_id == tenant_id,
            ).first()
            if row:
                return row[0]
        farmer_id = _uuid_or_none(_value(payload, "farmer_id", "farmerId"))
        if farmer_id:
            return farmer_id
        parcel_id = _uuid_or_none(_value(payload, "parcel_id", "parcelId"))
        if parcel_id:
            row = db.query(Parcel.farmer_id).filter(
                Parcel.id == parcel_id,
                Parcel.tenant_id == tenant_id,
            ).first()
            return row[0] if row else None

    if entity_type in {
        "farmer_project_enrollment",
        "farmerprojectenrollment",
        "project_enrollment",
        "projectenrollment",
    }:
        if entity_id:
            row = db.query(FarmerProjectEnrollment.farmer_id).filter(
                FarmerProjectEnrollment.id == entity_id,
                FarmerProjectEnrollment.tenant_id == tenant_id,
            ).first()
            if row:
                return row[0]
        return _uuid_or_none(_value(payload, "farmer_id", "farmerId"))

    if entity_type in {
        "query_thread",
        "querythread",
        "farmer_query_thread",
        "farmerquerythread",
    }:
        if entity_id:
            row = db.query(QueryThread.farmer_id).filter(
                QueryThread.id == entity_id,
                QueryThread.tenant_id == tenant_id,
            ).first()
            if row:
                return row[0]
        return _uuid_or_none(_value(payload, "farmer_id", "farmerId"))

    if entity_type in {
        "query_message",
        "querymessage",
        "farmer_query_message",
        "farmerquerymessage",
    }:
        message_id = entity_id or _uuid_or_none(
            _value(payload, "id", "message_id", "messageId")
        )
        if message_id:
            row = (
                db.query(QueryThread.farmer_id)
                .join(QueryMessage, QueryMessage.thread_id == QueryThread.id)
                .filter(
                    QueryMessage.id == message_id,
                    QueryMessage.tenant_id == tenant_id,
                    QueryThread.tenant_id == tenant_id,
                )
                .first()
            )
            if row:
                return row[0]
        thread_id = _uuid_or_none(_value(payload, "thread_id", "threadId"))
        if thread_id:
            row = db.query(QueryThread.farmer_id).filter(
                QueryThread.id == thread_id,
                QueryThread.tenant_id == tenant_id,
            ).first()
            return row[0] if row else None

    if entity_type in {
        "field_event_report",
        "fieldeventreport",
        "field_event",
        "fieldevent",
    }:
        if entity_id:
            row = db.query(FieldEventReport.farmer_id).filter(
                FieldEventReport.id == entity_id,
                FieldEventReport.tenant_id == tenant_id,
            ).first()
            if row:
                return row[0]
        return _uuid_or_none(_value(payload, "farmer_id", "farmerId"))

    if entity_type in {"crop_cycle", "cropcycle"}:
        if entity_id:
            row = db.query(CropCycle.farmer_id).filter(
                CropCycle.id == entity_id,
                CropCycle.tenant_id == tenant_id,
            ).first()
            if row:
                return row[0]
        farmer_id = _uuid_or_none(_value(payload, "farmer_id", "farmerId"))
        if farmer_id:
            return farmer_id
        parcel_id = _uuid_or_none(_value(payload, "parcel_id", "parcelId"))
        if parcel_id:
            row = db.query(Parcel.farmer_id).filter(
                Parcel.id == parcel_id,
                Parcel.tenant_id == tenant_id,
            ).first()
            return row[0] if row else None

    if entity_type in {
        "crop_stage",
        "cropstage",
        "crop_stage_instance",
        "cropstageinstance",
    }:
        cycle_id = _uuid_or_none(_value(payload, "crop_cycle_id", "cropCycleId"))
        if not cycle_id and entity_id:
            row = db.query(CropStageInstance.crop_cycle_id).filter(
                CropStageInstance.id == entity_id,
                CropStageInstance.tenant_id == tenant_id,
            ).first()
            cycle_id = row[0] if row else None
        if cycle_id:
            row = db.query(CropCycle.farmer_id).filter(
                CropCycle.id == cycle_id,
                CropCycle.tenant_id == tenant_id,
            ).first()
            return row[0] if row else None

    if entity_type in {"crop_activity", "cropactivity"}:
        if entity_id:
            row = db.query(CropActivity.farmer_id).filter(
                CropActivity.id == entity_id,
                CropActivity.tenant_id == tenant_id,
            ).first()
            if row:
                return row[0]
        cycle_id = _uuid_or_none(_value(payload, "crop_cycle_id", "cropCycleId"))
        if cycle_id:
            row = db.query(CropCycle.farmer_id).filter(
                CropCycle.id == cycle_id,
                CropCycle.tenant_id == tenant_id,
            ).first()
            return row[0] if row else None

    return None


def authorize_sync_events(
    db: Session,
    *,
    principal: AuthenticatedPrincipal,
    events: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Partition a batch into authorized events and per-event denials."""

    if _is_admin(principal):
        return events, []

    scope = resolve_human_persona_scope(db, principal)
    allowed_farmer_ids = set(scope.own_farmer_ids | scope.assigned_farmer_ids)
    provisional_farmer_ids: set[uuid.UUID] = set()
    authorized = []
    denied = []

    user = db.query(User).filter(
        User.id == principal.user_id,
        User.tenant_id == principal.tenant_id,
        User.is_active == True,
    ).first()

    for event in events:
        payload = event.get("payload") or {}
        event["payload"] = payload
        event_id = str(event.get("event_id"))
        entity_type = str(event.get("entity_type") or "").lower()
        farmer_id = _existing_farmer_id(
            db,
            principal.tenant_id,
            event,
        )

        if entity_type == "farmer" and farmer_id is None:
            proposed_id = _uuid_or_none(
                event.get("entity_id")
                or _value(payload, "id", "farmer_id", "farmerId")
            )
            project_id = _uuid_or_none(
                _value(payload, "project_id", "projectId")
            )
            self_enrollment = (
                str(principal.role or "").upper() == "FARMER"
                and user is not None
                and _normalized_mobile(user.mobile_number)
                == _normalized_mobile(
                    _value(payload, "mobile_number", "mobileNumber", "phone")
                )
            )
            agent_enrollment = (
                scope.has_agent_persona
                and project_id is not None
                and scope.has_project_access(project_id)
            )
            if proposed_id and (self_enrollment or agent_enrollment):
                farmer_id = proposed_id
                provisional_farmer_ids.add(proposed_id)
                payload["enrolled_by"] = str(principal.user_id)
                if self_enrollment:
                    payload["user_id"] = str(principal.user_id)
                    payload["assigned_user_ids"] = []
                if agent_enrollment:
                    payload["user_id"] = None
                    payload["assigned_user_ids"] = [
                        str(principal.user_id)
                    ]

        enrollment_types = {
            "farmer_project_enrollment",
            "farmerprojectenrollment",
            "project_enrollment",
            "projectenrollment",
        }
        if entity_type in enrollment_types:
            project_id = _uuid_or_none(
                _value(payload, "project_id", "projectId")
            )
            if not (
                scope.has_agent_persona
                and project_id is not None
                and scope.has_project_access(project_id)
            ):
                farmer_id = None
            else:
                payload["enrolled_by"] = str(principal.user_id)

        if farmer_id in allowed_farmer_ids or farmer_id in provisional_farmer_ids:
            authorized.append(event)
            continue

        denied.append({
            "event_id": event_id,
            "error_code": "SYNC_SCOPE_DENIED",
            "detail_code": "PERSONA_SCOPE_DENIED",
            "message": (
                "Authenticated user cannot sync this farmer-scoped entity."
            ),
        })

    return authorized, denied
