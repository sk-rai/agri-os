"""Resolve strict operational personas for an authenticated human.

A User is the login identity. Farmer, AgentProfile, ProjectRole, and active
farmer-project assignments provide concurrent operational capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from sqlalchemy.orm import Session

from app.core.human_auth import AuthenticatedPrincipal
from app.modules.auth.models import AgentProfile
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
    Project,
    ProjectRole,
)


@dataclass(frozen=True)
class HumanPersonaScope:
    user_id: uuid.UUID
    tenant_id: str
    login_role: str
    own_farmer_ids: frozenset[uuid.UUID]
    assigned_farmer_ids: frozenset[uuid.UUID]
    active_agent_profile_id: uuid.UUID | None
    agent_role_type: str | None
    project_roles: tuple[tuple[uuid.UUID, str], ...]

    @property
    def has_farmer_persona(self) -> bool:
        return bool(self.own_farmer_ids)

    @property
    def has_agent_persona(self) -> bool:
        return self.active_agent_profile_id is not None

    @property
    def is_dual_persona(self) -> bool:
        return self.has_farmer_persona and self.has_agent_persona

    def owns_farmer(self, farmer_id: uuid.UUID) -> bool:
        return farmer_id in self.own_farmer_ids

    def is_assigned_to_farmer(self, farmer_id: uuid.UUID) -> bool:
        return farmer_id in self.assigned_farmer_ids

    def can_operate_farmer(self, farmer_id: uuid.UUID) -> bool:
        return self.owns_farmer(farmer_id) or self.is_assigned_to_farmer(farmer_id)

    def has_project_access(self, project_id: uuid.UUID) -> bool:
        return any(item_project_id == project_id for item_project_id, _ in self.project_roles)


def resolve_human_persona_scope(
    db: Session,
    principal: AuthenticatedPrincipal,
) -> HumanPersonaScope:
    """Resolve active, tenant-bounded farmer and agent capabilities."""

    own_farmer_ids = frozenset(
        row[0]
        for row in (
            db.query(Farmer.id)
            .filter(
                Farmer.tenant_id == principal.tenant_id,
                Farmer.user_id == principal.user_id,
                Farmer.status != "ARCHIVED",
                Farmer.is_active == True,
            )
            .all()
        )
    )

    agent_profile = (
        db.query(AgentProfile)
        .filter(
            AgentProfile.tenant_id == principal.tenant_id,
            AgentProfile.user_id == principal.user_id,
            AgentProfile.status == "ACTIVE",
            AgentProfile.is_active == True,
        )
        .first()
    )

    project_role_rows = (
        db.query(ProjectRole.project_id, ProjectRole.role)
        .join(Project, Project.id == ProjectRole.project_id)
        .filter(
            ProjectRole.user_id == principal.user_id,
            ProjectRole.is_active == True,
            Project.tenant_id == principal.tenant_id,
            Project.is_active == True,
        )
        .all()
    )
    project_roles = tuple(
        (project_id, str(role or "").upper())
        for project_id, role in project_role_rows
    )
    accessible_project_ids = {
        project_id
        for project_id, _ in project_roles
    }

    assigned_farmer_ids: set[uuid.UUID] = set()
    if agent_profile:
        actor_id = str(principal.user_id)
        enrollments = (
            db.query(FarmerProjectEnrollment)
            .join(Farmer, Farmer.id == FarmerProjectEnrollment.farmer_id)
            .join(Project, Project.id == FarmerProjectEnrollment.project_id)
            .filter(
                FarmerProjectEnrollment.tenant_id == principal.tenant_id,
                FarmerProjectEnrollment.status == "ACTIVE",
                FarmerProjectEnrollment.is_active == True,
                Farmer.tenant_id == principal.tenant_id,
                Farmer.status != "ARCHIVED",
                Farmer.is_active == True,
                Project.tenant_id == principal.tenant_id,
                Project.is_active == True,
            )
            .all()
        )
        for enrollment in enrollments:
            if enrollment.project_id not in accessible_project_ids:
                continue
            assignment_ids = {
                str(value)
                for value in (enrollment.assigned_user_ids or [])
            }
            if actor_id in assignment_ids:
                assigned_farmer_ids.add(enrollment.farmer_id)

    return HumanPersonaScope(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        login_role=str(principal.role or "").upper(),
        own_farmer_ids=own_farmer_ids,
        assigned_farmer_ids=frozenset(assigned_farmer_ids),
        active_agent_profile_id=agent_profile.id if agent_profile else None,
        agent_role_type=(
            str(agent_profile.role_type or "").upper()
            if agent_profile
            else None
        ),
        project_roles=project_roles,
    )
