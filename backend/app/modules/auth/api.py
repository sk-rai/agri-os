"""Auth API endpoints.

POST /api/v1/auth/otp/request  — Request OTP (sends SMS via Twilio)
POST /api/v1/auth/otp/verify   — Verify OTP → JWT + device_key
POST /api/v1/auth/device       — Device-key login (no SMS)
"""

from fastapi import APIRouter, Depends, HTTPException, status
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
