"""Auth request/response schemas.

Auth flow (per governance):
1. First login: Twilio OTP → verify → JWT + device_key
2. Subsequent logins: device_key → JWT (no SMS needed)
3. Phone change: re-verify via OTP
"""

from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class OTPRequestSchema(BaseModel):
    """Request OTP for first-time registration or phone change."""
    mobile_number: str = Field(
        ..., pattern=r"^\+91[6-9]\d{9}$",
        description="Indian mobile number with +91 prefix",
    )


class OTPVerifySchema(BaseModel):
    """Verify OTP and get JWT + device_key."""
    mobile_number: str = Field(..., pattern=r"^\+91[6-9]\d{9}$")
    otp_code: str = Field(..., min_length=6, max_length=6)
    device_id: str = Field(..., description="Unique device identifier")
    device_name: Optional[str] = Field(None, description="Human-readable device name")


class DeviceAuthSchema(BaseModel):
    """Authenticate using device_key (no SMS needed)."""
    device_key: str = Field(..., description="Device key issued during OTP verification")
    device_id: str = Field(..., description="Must match the device_id used during registration")


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    device_key: Optional[str] = None  # Only returned on first OTP verify
    user_id: UUID
    role: str


class OTPRequestResponse(BaseModel):
    """Response after OTP request."""
    message: str = "OTP sent successfully"
    expires_in: int = 300  # 5 minutes
