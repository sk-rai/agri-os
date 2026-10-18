#!/usr/bin/env python3
"""Identity helpers for deterministic Android fixtures.

These helpers never authenticate as an administrator and never print credentials.
They only repair the explicitly named fixture user, farmer linkage, and project
enrollment after validating tenant ownership.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.farmer.models import Farmer, FarmerProjectEnrollment, Project
from app.modules.master_data import models as _master_data_models  # noqa: F401


def _now():
    return datetime.now(timezone.utc)


def _tenant_conflict(value: str | None, expected: str) -> bool:
    return bool(value and value.strip() and value != expected)


def ensure_fixture_farmer_identity(
    db: Session,
    *,
    mobile: str,
    tenant_id: str,
    project_id: uuid.UUID,
    dry_run: bool,
    result: dict,
    deterministic_user_id: uuid.UUID | None = None,
    expected_farmer_id: uuid.UUID | None = None,
    link_existing_farmer: bool = True,
) -> User | None:
    """Plan or apply a tenant-safe fixture identity repair.

    Existing user IDs are always preserved. A fixture mobile assigned to another
    nonempty tenant is rejected rather than reassigned.
    """
    identity = result.setdefault("identity", {})
    identity.update({"mobile": mobile, "tenant_id": tenant_id, "actions": []})

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or project.tenant_id != tenant_id:
        raise RuntimeError(
            f"Fixture project {project_id} is absent or does not belong to {tenant_id}."
        )

    user = db.query(User).filter(User.mobile_number == mobile).first()
    identity["before_user"] = (
        {
            "id": str(user.id),
            "tenant_id": user.tenant_id,
            "role": user.role,
            "is_active": bool(user.is_active),
        }
        if user
        else None
    )
    if user and _tenant_conflict(user.tenant_id, tenant_id):
        raise RuntimeError(
            f"Fixture mobile ending {mobile[-4:]} belongs to tenant {user.tenant_id}; refusing reassignment."
        )

    if not user:
        user_id = deterministic_user_id or uuid.uuid5(
            uuid.UUID("9e971442-bc63-4b42-a45a-574bac21ea66"), mobile
        )
        if db.query(User).filter(User.id == user_id).first():
            raise RuntimeError(f"Deterministic fixture user ID {user_id} is already in use.")
        identity["actions"].append("CREATE_ACTIVE_FARMER_USER")
        if not dry_run:
            user = User(
                id=user_id,
                mobile_number=mobile,
                role="FARMER",
                display_name=f"Android fixture farmer {mobile[-4:]}",
                tenant_id=tenant_id,
                is_active=True,
                created_at=_now(),
                updated_at=_now(),
            )
            db.add(user)
            db.flush()
    else:
        if user.tenant_id != tenant_id:
            identity["actions"].append("ASSIGN_EMPTY_USER_TENANT")
            if not dry_run:
                user.tenant_id = tenant_id
        if user.role != "FARMER":
            identity["actions"].append("SET_USER_ROLE_FARMER")
            if not dry_run:
                user.role = "FARMER"
        if not user.is_active:
            identity["actions"].append("ACTIVATE_USER")
            if not dry_run:
                user.is_active = True
        if not dry_run and identity["actions"]:
            user.updated_at = _now()

    user_id = user.id if user else (deterministic_user_id or uuid.uuid5(
        uuid.UUID("9e971442-bc63-4b42-a45a-574bac21ea66"), mobile
    ))
    if not link_existing_farmer:
        identity["before_farmer"] = None
        identity["farmer_linkage"] = "ABSENT_SELF_ENROLLMENT_READY"
        identity["after_user"] = {
            "id": str(user_id), "tenant_id": tenant_id, "role": "FARMER", "is_active": True
        }
        return user

    farmer_query = db.query(Farmer).filter(Farmer.mobile_number == mobile)
    farmers = farmer_query.all()
    conflicts = [farmer for farmer in farmers if farmer.tenant_id != tenant_id]
    if conflicts:
        raise RuntimeError(
            f"Fixture mobile ending {mobile[-4:]} has farmer rows outside {tenant_id}; refusing repair."
        )
    farmer = None
    if expected_farmer_id:
        farmer = next((row for row in farmers if row.id == expected_farmer_id), None)
        wrong_id = [row for row in farmers if row.id != expected_farmer_id]
        if wrong_id:
            raise RuntimeError(
                f"Fixture mobile ending {mobile[-4:]} is attached to an unexpected farmer ID."
            )
    elif len(farmers) == 1:
        farmer = farmers[0]
    elif len(farmers) > 1:
        raise RuntimeError(f"Fixture mobile ending {mobile[-4:]} has multiple farmer rows.")

    identity["before_farmer"] = (
        {
            "id": str(farmer.id),
            "tenant_id": farmer.tenant_id,
            "project_id": str(farmer.project_id) if farmer.project_id else None,
            "user_id": str(farmer.user_id) if farmer.user_id else None,
            "status": farmer.status,
        }
        if farmer
        else None
    )
    if not farmer:
        identity["farmer_linkage"] = "ABSENT_SELF_ENROLLMENT_READY"
        identity["after_user"] = {
            "id": str(user_id), "tenant_id": tenant_id, "role": "FARMER", "is_active": True
        }
        return user

    if farmer.user_id and farmer.user_id != user_id:
        raise RuntimeError(
            f"Farmer {farmer.id} is already linked to a different user; refusing repair."
        )
    if farmer.user_id != user_id:
        identity["actions"].append("LINK_FARMER_TO_USER")
        if not dry_run:
            farmer.user_id = user_id
    if farmer.project_id is None:
        identity["actions"].append("SET_FARMER_PROJECT")
        if not dry_run:
            farmer.project_id = project_id
    elif farmer.project_id != project_id:
        raise RuntimeError(f"Farmer {farmer.id} belongs to a different project; refusing repair.")
    if farmer.status != "ACTIVE":
        identity["actions"].append("ACTIVATE_FARMER")
        if not dry_run:
            farmer.status = "ACTIVE"
    if not farmer.is_active:
        identity["actions"].append("ENABLE_FARMER")
        if not dry_run:
            farmer.is_active = True

    enrollment = db.query(FarmerProjectEnrollment).filter(
        FarmerProjectEnrollment.tenant_id == tenant_id,
        FarmerProjectEnrollment.farmer_id == farmer.id,
        FarmerProjectEnrollment.project_id == project_id,
    ).first()
    identity["before_enrollment"] = (
        {"id": str(enrollment.id), "status": enrollment.status} if enrollment else None
    )
    if not enrollment:
        identity["actions"].append("CREATE_ACTIVE_PROJECT_ENROLLMENT")
        if not dry_run:
            enrollment = FarmerProjectEnrollment(
                tenant_id=tenant_id,
                farmer_id=farmer.id,
                project_id=project_id,
                enrollment_method="SELF",
                enrollment_source="ANDROID_FIXTURE_AUTH_COMPAT",
                enrolled_by=user_id,
                status="ACTIVE",
                parcel_ids=[],
                assigned_user_ids=[],
                metadata_={"fixture": True},
                created_at=_now(),
                updated_at=_now(),
            )
            db.add(enrollment)
    elif enrollment.status != "ACTIVE" or not enrollment.is_active:
        identity["actions"].append("ACTIVATE_PROJECT_ENROLLMENT")
        if not dry_run:
            enrollment.status = "ACTIVE"
            enrollment.is_active = True
            enrollment.updated_at = _now()

    if not dry_run:
        farmer.updated_at = _now()
    identity["farmer_linkage"] = "LINKED_OR_PLANNED"
    identity["after_user"] = {
        "id": str(user_id), "tenant_id": tenant_id, "role": "FARMER", "is_active": True
    }
    return user
