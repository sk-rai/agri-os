#!/usr/bin/env python3
"""Database-backed behavior contract for authenticated-human persona scope."""

import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app  # noqa: F401 - registers the complete ORM model graph
from app.core.human_auth import AuthenticatedPrincipal
from app.core.human_persona_scope import resolve_human_persona_scope
from app.modules.auth.models import AgentProfile, User
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
    Project,
    ProjectRole,
    Tenant,
)


def now():
    return datetime.now(timezone.utc)


def require(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def principal(user, tenant_id):
    return AuthenticatedPrincipal(
        user_id=user.id,
        tenant_id=tenant_id,
        role=user.role,
        device_id="persona-scope-regression",
    )


def make_user(tenant_id, role, label):
    return User(
        id=uuid.uuid4(),
        mobile_number=f"+919{uuid.uuid4().int % 1000000000:09d}"[:13],
        role=role,
        tenant_id=tenant_id,
        display_name=label,
        language_preference="hi",
        created_at=now(),
        updated_at=now(),
    )


def make_farmer(tenant_id, project_id, label, user_id=None):
    return Farmer(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        user_id=user_id,
        mobile_number=f"9{uuid.uuid4().int % 1000000000:09d}",
        display_name=label,
        village_name_manual="Persona Scope Village",
        total_land_unit="ACRE",
        status="ACTIVE",
        created_at=now(),
        updated_at=now(),
    )


def main():
    tenant_id = f"persona-scope-{uuid.uuid4().hex[:8]}"
    other_tenant_id = f"{tenant_id}-other"

    db = SessionLocal()
    try:
        tenant = Tenant(
            id=tenant_id,
            name="Persona Scope Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        )
        other_tenant = Tenant(
            id=other_tenant_id,
            name="Other Persona Scope Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([tenant, other_tenant])
        db.flush()

        project = Project(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name="Persona Scope Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["RICE"],
            config={},
            created_at=now(),
            updated_at=now(),
        )
        other_project = Project(
            id=uuid.uuid4(),
            tenant_id=other_tenant_id,
            name="Other Persona Scope Project",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status="ACTIVE",
            geography_scope={},
            crop_scope=["WHEAT"],
            config={},
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([project, other_project])
        db.flush()

        farmer_user = make_user(tenant_id, "FARMER", "Persona Farmer")
        agent_user = make_user(tenant_id, "AGRONOMIST", "Persona Agent")
        dual_user = make_user(tenant_id, "AGRONOMIST", "Persona Dual User")
        db.add_all([farmer_user, agent_user, dual_user])
        db.flush()

        farmer_own = make_farmer(
            tenant_id,
            project.id,
            "Farmer Personal Farm",
            farmer_user.id,
        )
        assisted_farmer = make_farmer(
            tenant_id,
            project.id,
            "Assigned Assisted Farmer",
        )
        unassigned_farmer = make_farmer(
            tenant_id,
            project.id,
            "Unassigned Assisted Farmer",
        )
        dual_own_farmer = make_farmer(
            tenant_id,
            project.id,
            "Dual User Personal Farm",
            dual_user.id,
        )
        cross_tenant_farmer = make_farmer(
            other_tenant_id,
            other_project.id,
            "Cross Tenant Farmer",
        )
        db.add_all([
            farmer_own,
            assisted_farmer,
            unassigned_farmer,
            dual_own_farmer,
            cross_tenant_farmer,
        ])
        db.flush()

        agent_profile = AgentProfile(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=agent_user.id,
            farmer_id=None,
            agent_code="PERSONA-AGENT",
            role_type="AGRONOMIST",
            display_name="Persona Agent",
            mobile_number=agent_user.mobile_number,
            status="ACTIVE",
            skills=["CROP_HEALTH"],
            languages=["hi"],
            territory_scope={"village_names": ["Persona Scope Village"]},
            availability={},
            certification={},
            metadata_={"regression": True},
            created_at=now(),
            updated_at=now(),
        )
        dual_profile = AgentProfile(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=dual_user.id,
            farmer_id=dual_own_farmer.id,
            agent_code="PERSONA-DUAL",
            role_type="FIELD_AGENT",
            display_name="Persona Dual User",
            mobile_number=dual_user.mobile_number,
            status="ACTIVE",
            skills=["PROFILE_CAPTURE"],
            languages=["hi"],
            territory_scope={"village_names": ["Persona Scope Village"]},
            availability={},
            certification={},
            metadata_={"can_also_act_as_farmer": True, "regression": True},
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([agent_profile, dual_profile])

        agent_project_role = ProjectRole(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=agent_user.id,
            role="AGRONOMIST",
            territory_scope={"village_names": ["Persona Scope Village"]},
            created_at=now(),
            updated_at=now(),
        )
        dual_project_role = ProjectRole(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=dual_user.id,
            role="FIELD_AGENT",
            territory_scope={"village_names": ["Persona Scope Village"]},
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([agent_project_role, dual_project_role])

        assigned_enrollment = FarmerProjectEnrollment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            farmer_id=assisted_farmer.id,
            project_id=project.id,
            enrollment_method="ASSISTED",
            enrollment_source="PERSONA_SCOPE_REGRESSION",
            status="ACTIVE",
            parcel_ids=[],
            assigned_user_ids=[
                str(agent_user.id),
                str(dual_user.id),
            ],
            metadata_={"regression": True},
            notes="Assigned farmer persona-scope regression.",
            created_at=now(),
            updated_at=now(),
        )
        unassigned_enrollment = FarmerProjectEnrollment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            farmer_id=unassigned_farmer.id,
            project_id=project.id,
            enrollment_method="ASSISTED",
            enrollment_source="PERSONA_SCOPE_REGRESSION",
            status="ACTIVE",
            parcel_ids=[],
            assigned_user_ids=[],
            metadata_={"regression": True},
            notes="Unassigned farmer persona-scope regression.",
            created_at=now(),
            updated_at=now(),
        )
        cross_tenant_enrollment = FarmerProjectEnrollment(
            id=uuid.uuid4(),
            tenant_id=other_tenant_id,
            farmer_id=cross_tenant_farmer.id,
            project_id=other_project.id,
            enrollment_method="ASSISTED",
            enrollment_source="PERSONA_SCOPE_REGRESSION",
            status="ACTIVE",
            parcel_ids=[],
            assigned_user_ids=[str(agent_user.id)],
            metadata_={"regression": True},
            notes="Cross-tenant isolation regression.",
            created_at=now(),
            updated_at=now(),
        )
        db.add_all([
            assigned_enrollment,
            unassigned_enrollment,
            cross_tenant_enrollment,
        ])
        db.flush()

        farmer_scope = resolve_human_persona_scope(
            db,
            principal(farmer_user, tenant_id),
        )
        require(farmer_scope.has_farmer_persona, "Farmer persona is resolved")
        require(not farmer_scope.has_agent_persona, "Farmer-only user has no agent persona")
        require(farmer_scope.owns_farmer(farmer_own.id), "Farmer owns linked farmer profile")
        require(
            not farmer_scope.can_operate_farmer(assisted_farmer.id),
            "Farmer cannot operate unrelated assisted farmer",
        )

        agent_scope = resolve_human_persona_scope(
            db,
            principal(agent_user, tenant_id),
        )
        require(agent_scope.has_agent_persona, "Agent persona is resolved")
        require(not agent_scope.has_farmer_persona, "Agent-only user has no farmer persona")
        require(
            agent_scope.is_assigned_to_farmer(assisted_farmer.id),
            "Assigned agent can operate assisted farmer",
        )
        require(
            not agent_scope.can_operate_farmer(unassigned_farmer.id),
            "Unassigned agent cannot operate farmer",
        )
        require(
            agent_scope.has_project_access(project.id),
            "Agent project role is resolved",
        )
        require(
            cross_tenant_farmer.id not in agent_scope.assigned_farmer_ids,
            "Cross-tenant assignment is excluded",
        )

        dual_scope = resolve_human_persona_scope(
            db,
            principal(dual_user, tenant_id),
        )
        require(dual_scope.is_dual_persona, "Same user resolves both personas")
        require(
            dual_scope.owns_farmer(dual_own_farmer.id),
            "Dual user can operate personal farm",
        )
        require(
            dual_scope.is_assigned_to_farmer(assisted_farmer.id),
            "Dual user can operate assigned farmer",
        )

        assigned_enrollment.status = "CANCELLED"
        db.flush()
        inactive_assignment_scope = resolve_human_persona_scope(
            db,
            principal(agent_user, tenant_id),
        )
        require(
            assisted_farmer.id not in inactive_assignment_scope.assigned_farmer_ids,
            "Inactive assignment grants no farmer access",
        )
        assigned_enrollment.status = "ACTIVE"
        db.flush()

        agent_project_role.is_active = False
        db.flush()
        inactive_project_role_scope = resolve_human_persona_scope(
            db,
            principal(agent_user, tenant_id),
        )
        require(
            assisted_farmer.id
            not in inactive_project_role_scope.assigned_farmer_ids,
            "Inactive project role grants no assigned farmers",
        )
        agent_project_role.is_active = True
        db.flush()

        agent_profile.status = "INACTIVE"
        db.flush()
        inactive_agent_scope = resolve_human_persona_scope(
            db,
            principal(agent_user, tenant_id),
        )
        require(
            not inactive_agent_scope.has_agent_persona,
            "Inactive agent profile grants no agent persona",
        )
        require(
            not inactive_agent_scope.assigned_farmer_ids,
            "Inactive agent profile grants no assigned farmers",
        )

        print({
            "schema_version": "human_persona_scope_test.v1",
            "farmer_only": True,
            "agent_only": True,
            "dual_persona": True,
            "unassigned_denied": True,
            "inactive_assignment_excluded": True,
            "inactive_project_role_excluded": True,
            "inactive_agent_excluded": True,
            "cross_tenant_excluded": True,
        })
        print("HUMAN PERSONA SCOPE BEHAVIOR PASSED")
    finally:
        db.rollback()
        db.close()

    verification_db = SessionLocal()
    try:
        remaining = verification_db.execute(
            text(
                """
                select count(*)
                from tenants
                where id in (:tenant_id, :other_tenant_id)
                """
            ),
            {
                "tenant_id": tenant_id,
                "other_tenant_id": other_tenant_id,
            },
        ).scalar()
        require(remaining == 0, "Persona-scope test rows were rolled back")
    finally:
        verification_db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
