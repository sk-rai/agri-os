"""Role-neutral bearer authentication for human API callers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional
import uuid

from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.models import User
from app.modules.auth.service import JWT_ALGORITHM, JWT_SECRET


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: uuid.UUID
    tenant_id: str
    role: str
    device_id: Optional[str] = None


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={
            "error": "AUTHENTICATION_REQUIRED",
            "message": message,
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(error: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "error": error,
            "message": message,
        },
    )


@dataclass(frozen=True)
class VerifiedHumanIdentity:
    user: User
    claims: dict[str, Any]


def resolve_authenticated_identity(
    *,
    authorization: Optional[str],
    x_actor_id: Optional[str],
    db: Session,
    unauthorized_handler: Callable[[str], HTTPException] = _unauthorized,
    missing_bearer_message: str = "Bearer token is required.",
) -> VerifiedHumanIdentity:
    """Verify JWT subject, active persisted user and optional actor header."""

    if not authorization or not authorization.startswith("Bearer "):
        raise unauthorized_handler(missing_bearer_message)

    token = authorization[7:].strip()
    if not token:
        raise unauthorized_handler(missing_bearer_message)

    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
        user_id = uuid.UUID(str(claims.get("sub")))
    except (JWTError, TypeError, ValueError):
        raise unauthorized_handler("Bearer token is invalid or expired.")

    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.is_active == True,
        )
        .first()
    )
    if not user:
        raise unauthorized_handler(
            "Authenticated user no longer exists or is inactive."
        )

    if x_actor_id and x_actor_id != str(user.id):
        raise _forbidden(
            "ACTOR_ID_MISMATCH",
            "X-Actor-ID must match the authenticated user.",
        )

    return VerifiedHumanIdentity(user=user, claims=claims)


def require_authenticated_human():
    """Authenticate a persisted active user without imposing an admin role.

    Tenant and actor headers are routing context and must agree with the
    verified token and persisted user whenever they are supplied.
    """

    def dependency(
        authorization: Optional[str] = Header(None, alias="Authorization"),
        x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
        x_actor_id: Optional[str] = Header(None, alias="X-Actor-ID"),
        db: Session = Depends(get_db),
    ) -> AuthenticatedPrincipal:
        identity = resolve_authenticated_identity(
            authorization=authorization,
            x_actor_id=x_actor_id,
            db=db,
        )
        user = identity.user
        claims = identity.claims

        token_tenant = str(claims.get("tenant_id") or "")
        tenant_id = x_tenant_id or token_tenant or user.tenant_id or ""
        if not tenant_id:
            raise _forbidden(
                "TENANT_ID_REQUIRED",
                "Authenticated user is not assigned to a tenant.",
            )
        if token_tenant and token_tenant != tenant_id:
            raise _forbidden(
                "TENANT_ID_MISMATCH",
                "Token tenant does not match X-Tenant-ID.",
            )
        if user.tenant_id and user.tenant_id != tenant_id:
            raise _forbidden(
                "TENANT_ID_MISMATCH",
                "Authenticated user is not assigned to this tenant.",
            )

        return AuthenticatedPrincipal(
            user_id=user.id,
            tenant_id=tenant_id,
            role=str(user.role or "").upper(),
            device_id=str(claims.get("device_id") or "") or None,
        )

    return dependency
