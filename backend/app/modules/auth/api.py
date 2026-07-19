"""Auth API endpoints.

POST /api/v1/auth/otp/request  — Request OTP (sends SMS via Twilio)
POST /api/v1/auth/otp/verify   — Verify OTP → JWT + device_key
POST /api/v1/auth/device       — Device-key login (no SMS)
"""

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.schemas import (
    OTPRequestSchema,
    OTPVerifySchema,
    DeviceAuthSchema,
    TokenResponse,
    OTPRequestResponse,
)
from app.modules.auth import service
from app.modules.auth.models import AgentProfile, User
from app.modules.auth.service import JWT_ALGORITHM, JWT_SECRET
from app.modules.farmer.models import Farmer, Project, ProjectRole

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/otp/request", response_model=OTPRequestResponse)
def request_otp(
    body: OTPRequestSchema,
    db: Session = Depends(get_db),
):
    """Request OTP for registration or phone change.

    In development: OTP is returned in response headers (X-Dev-OTP).
    In production: OTP is sent via Twilio SMS.
    """
    otp = service.request_otp(db, body.mobile_number)

    response = OTPRequestResponse()
    # DEV ONLY: include OTP in response for testing
    # TODO: Remove in production, send via Twilio instead
    response.message = f"OTP sent to {body.mobile_number[-4:]}. Dev OTP: {otp}"
    response.dev_otp = otp
    return response


@router.post("/otp/verify", response_model=TokenResponse)
def verify_otp(
    body: OTPVerifySchema,
    db: Session = Depends(get_db),
):
    """Verify OTP and issue JWT + device_key.

    Creates user if first time (progressive enrollment).
    Registers device for future SMS-free login.
    """
    if not service.verify_otp(db, body.mobile_number, body.otp_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        )

    # Get or create user
    user = service.get_or_create_user(db, body.mobile_number)

    # Register device
    device_key = service.register_device(db, user, body.device_id, body.device_name)

    # Issue JWT
    token, expires_in = service.create_jwt(user, body.device_id)

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        device_key=device_key,
        user_id=user.id,
        role=user.role,
        tenant_id=user.tenant_id or "default",
    )


@router.post("/device", response_model=TokenResponse)
def device_login(
    body: DeviceAuthSchema,
    db: Session = Depends(get_db),
):
    """Login using device_key (no SMS needed).

    This is the primary auth method after first OTP verification.
    Eliminates ongoing SMS costs.
    """
    user = service.authenticate_device(db, body.device_key, body.device_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device key or device not registered",
        )

    token, expires_in = service.create_jwt(user, body.device_id)

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user_id=user.id,
        role=user.role,
        tenant_id=user.tenant_id or "default",
    )


def _resolve_bootstrap_user(
    db: Session,
    *,
    authorization: Optional[str],
    user_id: Optional[uuid.UUID],
) -> User:
    resolved_user_id = user_id
    if authorization and authorization.startswith("Bearer "):
        try:
            claims = jwt.decode(authorization[7:].strip(), JWT_SECRET, algorithms=[JWT_ALGORITHM])
            resolved_user_id = uuid.UUID(str(claims.get("sub")))
        except (JWTError, TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if not resolved_user_id:
        raise HTTPException(status_code=400, detail="Authorization bearer token or user_id query parameter is required")
    user = db.query(User).filter(User.id == resolved_user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _masked_mobile(value: str) -> str:
    return f"******{value[-4:]}" if value else ""


def _bootstrap_project_access(db: Session, *, tenant_id: str, user_id: uuid.UUID) -> list[dict]:
    rows = (
        db.query(ProjectRole, Project)
        .join(Project, Project.id == ProjectRole.project_id)
        .filter(
            Project.tenant_id == tenant_id,
            Project.is_active == True,
            ProjectRole.user_id == user_id,
            ProjectRole.is_active == True,
        )
        .order_by(Project.name)
        .all()
    )
    return [
        {
            "project_id": str(project.id),
            "project_name": project.name,
            "project_status": project.status,
            "role": role.role,
            "territory_scope": role.territory_scope or {},
        }
        for role, project in rows
    ]


def _bootstrap_agent_profile(db: Session, *, tenant_id: str, user_id: uuid.UUID) -> Optional[dict]:
    profile = db.query(AgentProfile).filter(
        AgentProfile.tenant_id == tenant_id,
        AgentProfile.user_id == user_id,
        AgentProfile.is_active == True,
    ).first()
    if not profile:
        return None
    return {
        "id": str(profile.id),
        "tenant_id": profile.tenant_id,
        "user_id": str(profile.user_id),
        "farmer_id": str(profile.farmer_id) if profile.farmer_id else None,
        "agent_code": profile.agent_code,
        "role_type": profile.role_type,
        "display_name": profile.display_name,
        "status": profile.status,
        "skills": profile.skills or [],
        "languages": profile.languages or [],
        "territory_scope": profile.territory_scope or {},
        "availability": profile.availability or {},
        "can_also_act_as_farmer": profile.farmer_id is not None,
    }


def _bootstrap_farmer_profile(db: Session, *, tenant_id: str, user_id: uuid.UUID, mobile_number: str, linked_farmer_id: Optional[uuid.UUID]) -> Optional[dict]:
    query = db.query(Farmer).filter(Farmer.tenant_id == tenant_id, Farmer.status != "ARCHIVED")
    farmer = None
    if linked_farmer_id:
        farmer = query.filter(Farmer.id == linked_farmer_id).first()
    if not farmer:
        farmer = query.filter(Farmer.user_id == user_id).first()
    if not farmer and mobile_number:
        farmer = query.filter(Farmer.mobile_number == mobile_number).first()
    if not farmer:
        return None
    return {
        "id": str(farmer.id),
        "tenant_id": farmer.tenant_id,
        "project_id": str(farmer.project_id) if farmer.project_id else None,
        "user_id": str(farmer.user_id) if farmer.user_id else None,
        "display_name": farmer.display_name,
        "mobile_number_masked": _masked_mobile(farmer.mobile_number),
        "village_name_manual": farmer.village_name_manual,
        "pin_code": farmer.pin_code,
        "language_preference": farmer.language_preference,
        "status": farmer.status,
    }


@router.get("/mode-bootstrap")
def get_mode_bootstrap(
    user_id: Optional[uuid.UUID] = Query(None),
    project_id: Optional[uuid.UUID] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    """Return Android's post-login mode decision in one backend-owned payload."""
    user = _resolve_bootstrap_user(db, authorization=authorization, user_id=user_id)
    tenant_id = x_tenant_id or user.tenant_id or "default"
    if user.tenant_id and user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="User is not assigned to this tenant")

    agent_profile = None if tenant_id == "default" else _bootstrap_agent_profile(db, tenant_id=tenant_id, user_id=user.id)
    linked_farmer_uuid = uuid.UUID(agent_profile["farmer_id"]) if agent_profile and agent_profile.get("farmer_id") else None
    farmer_profile = None if tenant_id == "default" else _bootstrap_farmer_profile(db, tenant_id=tenant_id, user_id=user.id, mobile_number=user.mobile_number, linked_farmer_id=linked_farmer_uuid)
    project_access = [] if tenant_id == "default" else _bootstrap_project_access(db, tenant_id=tenant_id, user_id=user.id)

    has_farmer_mode = farmer_profile is not None or str(user.role or "").upper() == "FARMER"
    has_agent_mode = bool(agent_profile and agent_profile.get("status") == "ACTIVE")
    if has_agent_mode and has_farmer_mode:
        first_screen = "MODE_CHOOSER"
    elif has_agent_mode:
        first_screen = "AGENT_WORKLIST"
    else:
        first_screen = "FARMER_HOME"

    primary_project_id = str(project_id) if project_id else None
    if not primary_project_id and project_access:
        primary_project_id = project_access[0]["project_id"]
    if not primary_project_id and farmer_profile and farmer_profile.get("project_id"):
        primary_project_id = farmer_profile["project_id"]

    return {
        "schema_version": "auth_mode_bootstrap.v1",
        "tenant_id": tenant_id,
        "user": {
            "id": str(user.id),
            "mobile_number_masked": _masked_mobile(user.mobile_number),
            "display_name": user.display_name,
            "role": user.role,
            "language_preference": user.language_preference,
        },
        "modes": {
            "farmer": {
                "available": has_farmer_mode,
                "farmer_id": farmer_profile["id"] if farmer_profile else None,
            },
            "agent": {
                "available": has_agent_mode,
                "agent_profile_id": agent_profile["id"] if agent_profile else None,
                "role_type": agent_profile["role_type"] if agent_profile else None,
            },
        },
        "first_screen_hint": first_screen,
        "primary_project_id": primary_project_id,
        "farmer_profile": farmer_profile,
        "agent_profile": agent_profile,
        "project_access": project_access,
        "endpoints": {
            "farmer_home": f"/api/v1/farmers/{farmer_profile['id']}" if farmer_profile else None,
            "agent_worklist": f"/api/v1/field-agent/worklist?project_id={primary_project_id}&assigned_only=true" if has_agent_mode and primary_project_id else None,
            "profile_contract": f"/api/v1/forms/profile-contract?project_id={primary_project_id}" if primary_project_id else "/api/v1/forms/profile-contract",
        },
    }
