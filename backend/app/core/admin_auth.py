"""Authentication and role-based authorization for admin mutations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import uuid

from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.models import User
from app.modules.auth.service import JWT_ALGORITHM, JWT_SECRET


class AdminPermission(str, Enum):
    VIEW = "VIEW"
    EDIT = "EDIT"
    PUBLISH = "PUBLISH"
    PROJECT_EDIT = "PROJECT_EDIT"
    MANAGE_USERS = "MANAGE_USERS"


ROLE_PERMISSIONS: dict[str, set[AdminPermission]] = {
    "ENTERPRISE_ADMIN": {
        AdminPermission.VIEW,
        AdminPermission.EDIT,
        AdminPermission.PUBLISH,
        AdminPermission.PROJECT_EDIT,
        AdminPermission.MANAGE_USERS,
    },
    "MANAGER": {
        AdminPermission.VIEW,
        AdminPermission.EDIT,
        AdminPermission.PUBLISH,
        AdminPermission.PROJECT_EDIT,
    },
    "AGRONOMIST": {
        AdminPermission.VIEW,
        AdminPermission.EDIT,
        AdminPermission.PROJECT_EDIT,
    },
    "ADMIN_EDITOR": {
        AdminPermission.VIEW,
        AdminPermission.EDIT,
    },
    "ADMIN_PUBLISHER": {
        AdminPermission.VIEW,
        AdminPermission.EDIT,
        AdminPermission.PUBLISH,
    },
    "ADMIN_VIEWER": {AdminPermission.VIEW},
    "VIEWER": {AdminPermission.VIEW},
}


@dataclass(frozen=True)
class AdminPrincipal:
    user_id: uuid.UUID
    tenant_id: str
    role: str
    project_id: Optional[uuid.UUID] = None
    project_role: Optional[str] = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": "ADMIN_AUTHENTICATION_REQUIRED", "message": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(permission: AdminPermission, detail: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "error": "ADMIN_PERMISSION_DENIED",
            "required_permission": permission.value,
            "message": detail,
        },
    )


def optional_admin_viewer(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
) -> Optional[AdminPrincipal]:
    """Resolve an admin viewer when present without blocking normal runtime reads."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        claims = jwt.decode(authorization[7:].strip(), JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = uuid.UUID(str(claims.get("sub")))
    except (JWTError, TypeError, ValueError):
        return None
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        return None
    tenant_id = x_tenant_id or str(claims.get("tenant_id") or "") or user.tenant_id
    role = str(user.role or "").upper()
    if not tenant_id or (user.tenant_id and user.tenant_id != tenant_id):
        return None
    if AdminPermission.VIEW not in ROLE_PERMISSIONS.get(role, set()):
        return None
    return AdminPrincipal(user_id=user.id, tenant_id=tenant_id, role=role)


def require_admin_permission(permission: AdminPermission, *, project_scoped: bool = False):
    """Require a persisted user role and, when relevant, project membership."""

    def dependency(
        project_id: Optional[uuid.UUID] = None,
        authorization: Optional[str] = Header(None, alias="Authorization"),
        x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
        x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
        db: Session = Depends(get_db),
    ) -> AdminPrincipal:
        from app.modules.farmer.models import Project, ProjectRole

        if not authorization or not authorization.startswith("Bearer "):
            raise _unauthorized("Bearer token is required for admin mutations.")
        token = authorization[7:].strip()
        if not token:
            raise _unauthorized("Bearer token is required for admin mutations.")
        try:
            claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = uuid.UUID(str(claims.get("sub")))
        except (JWTError, TypeError, ValueError):
            raise _unauthorized("Bearer token is invalid or expired.")

        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
        if not user:
            raise _unauthorized("Authenticated user no longer exists or is inactive.")
        if x_actor_id and x_actor_id != str(user.id):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "ACTOR_ID_MISMATCH",
                    "message": "X-Actor-ID must match the authenticated user.",
                },
            )

        token_tenant = str(claims.get("tenant_id") or "")
        tenant_id = x_tenant_id or token_tenant or user.tenant_id
        if not tenant_id:
            raise _forbidden(permission, "Admin user is not assigned to a tenant.")
        if token_tenant and token_tenant != tenant_id:
            raise _forbidden(permission, "Token tenant does not match X-Tenant-ID.")
        if user.tenant_id and user.tenant_id != tenant_id:
            raise _forbidden(permission, "User is not assigned to this tenant.")

        role = str(user.role or "").upper()
        effective_role = role
        project_role_name: Optional[str] = None
        if project_scoped:
            if not project_id:
                raise HTTPException(400, "Project-scoped permission requires project_id.")
            project = db.query(Project).filter(
                Project.id == project_id,
                Project.tenant_id == tenant_id,
                Project.is_active == True,
            ).first()
            if not project:
                raise HTTPException(404, "Project not found")
            if role != "ENTERPRISE_ADMIN":
                project_role = db.query(ProjectRole).filter(
                    ProjectRole.project_id == project_id,
                    ProjectRole.user_id == user.id,
                    ProjectRole.is_active == True,
                ).first()
                if not project_role:
                    raise _forbidden(permission, "User is not assigned to this project.")
                project_role_name = str(project_role.role or "").upper()
                effective_role = project_role_name

        if permission not in ROLE_PERMISSIONS.get(effective_role, set()):
            raise _forbidden(
                permission,
                f"Role {effective_role or 'UNASSIGNED'} does not grant {permission.value}.",
            )
        return AdminPrincipal(
            user_id=user.id,
            tenant_id=tenant_id,
            role=role,
            project_id=project_id if project_scoped else None,
            project_role=project_role_name,
        )

    return dependency
