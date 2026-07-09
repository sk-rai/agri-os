"""Tenant-admin user and project-access management APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPermission, AdminPrincipal, require_admin_permission
from app.core.database import get_db
from app.modules.auth.models import TenantUserAccessAuditEvent, User
from app.modules.farmer.models import Project, ProjectRole


router = APIRouter(prefix="/api/v1/admin", tags=["admin-users"])

TENANT_ADMIN_ROLES = {
    "ADMIN_VIEWER",
    "ADMIN_EDITOR",
    "ADMIN_PUBLISHER",
    "AGRONOMIST",
    "MANAGER",
    "ENTERPRISE_ADMIN",
}
PROJECT_ACCESS_ROLES = {"ADMIN_VIEWER", "AGRONOMIST", "MANAGER"}


class TenantUserRoleUpdate(BaseModel):
    mobile_number: str
    role: str
    display_name: Optional[str] = None
    reason: str = Field(..., min_length=3, max_length=500)

    @field_validator("mobile_number")
    @classmethod
    def normalize_mobile(cls, value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) == 10:
            return f"+91{digits}"
        if len(digits) == 12 and digits.startswith("91"):
            return f"+{digits}"
        raise ValueError("Mobile must be a valid 10-digit Indian number")

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        role = value.strip().upper()
        if role not in TENANT_ADMIN_ROLES:
            raise ValueError(f"Role must be one of {sorted(TENANT_ADMIN_ROLES)}")
        return role


class AccessRevokeRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class TenantUserRoleChange(BaseModel):
    role: str
    display_name: Optional[str] = None
    reason: str = Field(..., min_length=3, max_length=500)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        role = value.strip().upper()
        if role not in TENANT_ADMIN_ROLES:
            raise ValueError(f"Role must be one of {sorted(TENANT_ADMIN_ROLES)}")
        return role


class ProjectAccessUpdate(BaseModel):
    role: str
    territory_scope: dict = Field(default_factory=dict)
    reason: str = Field(..., min_length=3, max_length=500)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        role = value.strip().upper()
        if role not in PROJECT_ACCESS_ROLES:
            raise ValueError(f"Project role must be one of {sorted(PROJECT_ACCESS_ROLES)}")
        return role


def _project_access_payload(db: Session, user_id: uuid.UUID, tenant_id: str) -> list[dict]:
    rows = (
        db.query(ProjectRole, Project)
        .join(Project, Project.id == ProjectRole.project_id)
        .filter(
            ProjectRole.user_id == user_id,
            ProjectRole.is_active == True,
            Project.tenant_id == tenant_id,
            Project.is_active == True,
        )
        .order_by(Project.name)
        .all()
    )
    return [
        {
            "project_role_id": str(role.id),
            "project_id": str(project.id),
            "project_name": project.name,
            "project_status": project.status,
            "role": role.role,
            "territory_scope": role.territory_scope or {},
        }
        for role, project in rows
    ]


def _user_payload(db: Session, user: User, tenant_id: str) -> dict:
    return {
        "id": str(user.id),
        "mobile_number_masked": f"******{user.mobile_number[-4:]}",
        "display_name": user.display_name,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "login_count": user.login_count or 0,
        "project_access": _project_access_payload(db, user.id, tenant_id),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


def _role_snapshot(user: User) -> dict:
    return {
        "user_id": str(user.id),
        "tenant_id": user.tenant_id,
        "role": user.role,
        "display_name": user.display_name,
        "is_active": user.is_active,
    }


def _project_role_snapshot(role: Optional[ProjectRole]) -> Optional[dict]:
    if not role:
        return None
    return {
        "project_role_id": str(role.id),
        "project_id": str(role.project_id),
        "user_id": str(role.user_id),
        "role": role.role,
        "territory_scope": role.territory_scope or {},
        "is_active": role.is_active,
    }


def _record_access_audit(
    db: Session,
    *,
    principal: AdminPrincipal,
    target_user_id: uuid.UUID,
    action: str,
    before: Optional[dict],
    after: Optional[dict],
    reason: str,
    project_id: Optional[uuid.UUID] = None,
) -> None:
    db.add(TenantUserAccessAuditEvent(
        id=uuid.uuid4(),
        tenant_id=principal.tenant_id,
        target_user_id=target_user_id,
        actor_id=principal.user_id,
        project_id=project_id,
        action=action,
        before_payload=before,
        after_payload=after,
        reason=reason,
        created_at=datetime.now(timezone.utc),
    ))


def _tenant_user(db: Session, user_id: uuid.UUID, tenant_id: str) -> User:
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id,
        User.is_active == True,
    ).first()
    if not user:
        raise HTTPException(404, "Tenant user not found")
    return user


def _assert_not_last_enterprise_admin(db: Session, user: User, tenant_id: str) -> None:
    if user.role != "ENTERPRISE_ADMIN":
        return
    count = db.query(User).filter(
        User.tenant_id == tenant_id,
        User.role == "ENTERPRISE_ADMIN",
        User.is_active == True,
    ).count()
    if count <= 1:
        raise HTTPException(409, {
            "error": "LAST_ENTERPRISE_ADMIN",
            "message": "Assign another enterprise admin before changing or revoking this user.",
        })


@router.get("/users")
def list_tenant_admin_users(
    role: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.MANAGE_USERS)),
):
    query = db.query(User).filter(
        User.tenant_id == x_tenant_id,
        User.role.in_(sorted(TENANT_ADMIN_ROLES)),
        User.is_active == True,
    )
    if role:
        query = query.filter(User.role == role.upper())
    users = query.order_by(User.display_name, User.mobile_number).all()
    return {
        "schema_version": "tenant_admin_users.v1",
        "tenant_id": x_tenant_id,
        "available_roles": sorted(TENANT_ADMIN_ROLES),
        "project_roles": sorted(PROJECT_ACCESS_ROLES),
        "count": len(users),
        "users": [_user_payload(db, user, x_tenant_id) for user in users],
    }


@router.put("/users/by-mobile")
def assign_tenant_admin_role(
    body: TenantUserRoleUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.MANAGE_USERS)),
):
    user = db.query(User).filter(User.mobile_number == body.mobile_number).first()
    created = user is None
    if user and user.tenant_id and user.tenant_id != x_tenant_id:
        raise HTTPException(409, {
            "error": "USER_BELONGS_TO_ANOTHER_TENANT",
            "message": "This mobile number is already assigned to another tenant.",
        })
    if not user:
        user = User(
            id=uuid.uuid4(),
            mobile_number=body.mobile_number,
            role=body.role,
            tenant_id=x_tenant_id,
            display_name=body.display_name,
            language_preference="hi",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()
        before = None
        action = "INVITE_TENANT_USER"
    else:
        if user.id == principal.user_id and user.role != body.role:
            raise HTTPException(409, {
                "error": "SELF_ROLE_CHANGE_BLOCKED",
                "message": "Enterprise admins cannot change their own role.",
            })
        if user.role == "ENTERPRISE_ADMIN" and body.role != "ENTERPRISE_ADMIN":
            _assert_not_last_enterprise_admin(db, user, x_tenant_id)
        before = _role_snapshot(user)
        action = "ASSIGN_TENANT_ROLE" if not user.tenant_id else "CHANGE_TENANT_ROLE"
        user.tenant_id = x_tenant_id
        user.role = body.role
        user.is_active = True
        user.updated_at = datetime.now(timezone.utc)
        if body.display_name is not None:
            user.display_name = body.display_name
    after = _role_snapshot(user)
    _record_access_audit(
        db,
        principal=principal,
        target_user_id=user.id,
        action=action,
        before=before,
        after=after,
        reason=body.reason,
    )
    db.commit()
    db.refresh(user)
    return {
        "created": created,
        "user": _user_payload(db, user, x_tenant_id),
    }


@router.delete("/users/{user_id}")
def revoke_tenant_admin_access(
    user_id: uuid.UUID,
    body: AccessRevokeRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.MANAGE_USERS)),
):
    user = _tenant_user(db, user_id, x_tenant_id)
    if user.id == principal.user_id:
        raise HTTPException(409, {
            "error": "SELF_REVOKE_BLOCKED",
            "message": "Enterprise admins cannot revoke their own access.",
        })
    _assert_not_last_enterprise_admin(db, user, x_tenant_id)
    before = _role_snapshot(user)
    project_roles = db.query(ProjectRole).join(Project, Project.id == ProjectRole.project_id).filter(
        ProjectRole.user_id == user.id,
        ProjectRole.is_active == True,
        Project.tenant_id == x_tenant_id,
    ).all()
    for project_role in project_roles:
        project_role.is_active = False
        project_role.updated_at = datetime.now(timezone.utc)
    user.tenant_id = None
    user.role = "FARMER"
    user.updated_at = datetime.now(timezone.utc)
    after = _role_snapshot(user)
    _record_access_audit(
        db,
        principal=principal,
        target_user_id=user.id,
        action="REVOKE_TENANT_ACCESS",
        before=before,
        after=after,
        reason=body.reason,
    )
    db.commit()
    return {"status": "revoked", "user_id": str(user.id)}


@router.put("/users/{user_id}/role")
def change_tenant_admin_role(
    user_id: uuid.UUID,
    body: TenantUserRoleChange,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.MANAGE_USERS)),
):
    user = _tenant_user(db, user_id, x_tenant_id)
    if user.id == principal.user_id and user.role != body.role:
        raise HTTPException(409, {
            "error": "SELF_ROLE_CHANGE_BLOCKED",
            "message": "Enterprise admins cannot change their own role.",
        })
    if user.role == "ENTERPRISE_ADMIN" and body.role != "ENTERPRISE_ADMIN":
        _assert_not_last_enterprise_admin(db, user, x_tenant_id)
    before = _role_snapshot(user)
    user.role = body.role
    user.updated_at = datetime.now(timezone.utc)
    if body.display_name is not None:
        user.display_name = body.display_name
    after = _role_snapshot(user)
    _record_access_audit(
        db,
        principal=principal,
        target_user_id=user.id,
        action="CHANGE_TENANT_ROLE",
        before=before,
        after=after,
        reason=body.reason,
    )
    db.commit()
    return {"user": _user_payload(db, user, x_tenant_id)}


@router.put("/users/{user_id}/projects/{project_id}")
def assign_project_access(
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    body: ProjectAccessUpdate,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.MANAGE_USERS)),
):
    user = _tenant_user(db, user_id, x_tenant_id)
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.tenant_id == x_tenant_id,
        Project.is_active == True,
    ).first()
    if not project:
        raise HTTPException(404, "Project not found")
    role = db.query(ProjectRole).filter(
        ProjectRole.project_id == project_id,
        ProjectRole.user_id == user.id,
    ).first()
    before = _project_role_snapshot(role)
    if not role:
        role = ProjectRole(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=user.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(role)
    role.role = body.role
    role.territory_scope = body.territory_scope
    role.is_active = True
    role.updated_at = datetime.now(timezone.utc)
    db.flush()
    after = _project_role_snapshot(role)
    _record_access_audit(
        db,
        principal=principal,
        target_user_id=user.id,
        project_id=project_id,
        action="ASSIGN_PROJECT_ACCESS" if before is None else "CHANGE_PROJECT_ACCESS",
        before=before,
        after=after,
        reason=body.reason,
    )
    db.commit()
    return {"user": _user_payload(db, user, x_tenant_id)}


@router.delete("/users/{user_id}/projects/{project_id}")
def revoke_project_access(
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    body: AccessRevokeRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.MANAGE_USERS)),
):
    user = _tenant_user(db, user_id, x_tenant_id)
    role = db.query(ProjectRole).join(Project, Project.id == ProjectRole.project_id).filter(
        ProjectRole.project_id == project_id,
        ProjectRole.user_id == user.id,
        ProjectRole.is_active == True,
        Project.tenant_id == x_tenant_id,
    ).first()
    if not role:
        raise HTTPException(404, "Active project access not found")
    before = _project_role_snapshot(role)
    role.is_active = False
    role.updated_at = datetime.now(timezone.utc)
    after = _project_role_snapshot(role)
    _record_access_audit(
        db,
        principal=principal,
        target_user_id=user.id,
        project_id=project_id,
        action="REVOKE_PROJECT_ACCESS",
        before=before,
        after=after,
        reason=body.reason,
    )
    db.commit()
    return {"user": _user_payload(db, user, x_tenant_id)}


@router.get("/user-access-audit")
def list_user_access_audit(
    user_id: Optional[uuid.UUID] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    principal: AdminPrincipal = Depends(require_admin_permission(AdminPermission.MANAGE_USERS)),
):
    query = db.query(TenantUserAccessAuditEvent).filter(
        TenantUserAccessAuditEvent.tenant_id == x_tenant_id,
    )
    if user_id:
        query = query.filter(TenantUserAccessAuditEvent.target_user_id == user_id)
    if action:
        query = query.filter(TenantUserAccessAuditEvent.action == action.upper())
    events = query.order_by(TenantUserAccessAuditEvent.created_at.desc()).limit(limit).all()
    return {
        "schema_version": "tenant_user_access_audit.v1",
        "tenant_id": x_tenant_id,
        "count": len(events),
        "events": [
            {
                "id": str(event.id),
                "target_user_id": str(event.target_user_id),
                "actor_id": str(event.actor_id),
                "project_id": str(event.project_id) if event.project_id else None,
                "action": event.action,
                "before": event.before_payload,
                "after": event.after_payload,
                "reason": event.reason,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
    }
