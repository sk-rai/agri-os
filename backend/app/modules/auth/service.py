"""Auth service: OTP generation, verification, JWT issuance, device-key auth.

Per governance:
- Twilio for OTP in dev/test
- Device-key eliminates SMS after first login
- JWT includes: user_id, role, tenant_id, device_id
- Offline grace: farmer=3 days, dealer=5 days, agent=7 days
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.auth.models import User, UserDevice, OTPRecord

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
JWT_SECRET = "agrios-dev-secret-change-in-production"  # TODO: move to env
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72  # 3 days for farmers (offline grace)

# OTP settings
OTP_LENGTH = 6
OTP_EXPIRE_MINUTES = 5
OTP_MAX_ATTEMPTS = 3

# Offline grace periods per role (hours)
OFFLINE_GRACE = {
    "FARMER": 72,
    "DEALER": 120,
    "FIELD_AGENT": 168,
    "AGRONOMIST": 168,
    "ENTERPRISE_ADMIN": 24,
}


def generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return "".join([str(secrets.randbelow(10)) for _ in range(OTP_LENGTH)])


def hash_otp(otp: str) -> str:
    """Hash OTP for storage."""
    return pwd_context.hash(otp)


def verify_otp_hash(plain_otp: str, hashed: str) -> bool:
    """Verify OTP against hash."""
    return pwd_context.verify(plain_otp, hashed)


def generate_device_key() -> str:
    """Generate a secure device key for SMS-free login."""
    return secrets.token_urlsafe(48)


def create_jwt(user: User, device_id: str) -> tuple[str, int]:
    """Create JWT token for a user.

    Returns (token, expires_in_seconds).
    """
    grace_hours = OFFLINE_GRACE.get(user.role, 72)
    expire = datetime.now(timezone.utc) + timedelta(hours=grace_hours)

    payload = {
        "sub": str(user.id),
        "role": user.role,
        "tenant_id": user.tenant_id or "",
        "device_id": device_id,
        "mobile": user.mobile_number[-4:],  # Last 4 digits only (PII masking)
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    expires_in = int((expire - datetime.now(timezone.utc)).total_seconds())
    return token, expires_in


def request_otp(db: Session, mobile_number: str) -> str:
    """Generate and store OTP. Returns the OTP (for dev/test — in prod, send via Twilio)."""
    otp = generate_otp()

    # Invalidate any existing OTPs for this number
    db.query(OTPRecord).filter(
        OTPRecord.mobile_number == mobile_number,
        OTPRecord.is_used == False,
    ).update({"is_used": True})

    # Create new OTP record
    record = OTPRecord(
        id=uuid.uuid4(),
        mobile_number=mobile_number,
        otp_hash=hash_otp(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES),
    )
    db.add(record)
    db.commit()

    # TODO: Send via Twilio in production
    # For dev: return OTP directly (will be logged, not sent)
    return otp


def verify_otp(db: Session, mobile_number: str, otp_code: str) -> bool:
    """Verify OTP code. Returns True if valid."""
    record = (
        db.query(OTPRecord)
        .filter(
            OTPRecord.mobile_number == mobile_number,
            OTPRecord.is_used == False,
            OTPRecord.expires_at > datetime.now(timezone.utc),
        )
        .order_by(OTPRecord.created_at.desc())
        .first()
    )

    if not record:
        return False

    if record.attempts >= OTP_MAX_ATTEMPTS:
        record.is_used = True
        db.commit()
        return False

    record.attempts += 1

    if verify_otp_hash(otp_code, record.otp_hash):
        record.is_used = True
        db.commit()
        return True

    db.commit()
    return False


def get_or_create_user(db: Session, mobile_number: str) -> User:
    """Get existing user or create new one (progressive enrollment)."""
    user = db.query(User).filter(User.mobile_number == mobile_number).first()
    if user:
        return user

    # Create minimal user (progressive enrollment — just mobile for now)
    user = User(
        id=uuid.uuid4(),
        mobile_number=mobile_number,
        role="FARMER",  # Default role
        language_preference="hi",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def register_device(db: Session, user: User, device_id: str, device_name: str = None) -> str:
    """Register a device for SMS-free login. Returns device_key."""
    # Check if device already registered
    existing = (
        db.query(UserDevice)
        .filter(
            UserDevice.user_id == user.id,
            UserDevice.device_id == device_id,
            UserDevice.is_active == True,
        )
        .first()
    )
    if existing:
        existing.last_used_at = datetime.now(timezone.utc)
        db.commit()
        return existing.device_key

    # Create new device registration
    device_key = generate_device_key()
    device = UserDevice(
        id=uuid.uuid4(),
        user_id=user.id,
        device_id=device_id,
        device_key=device_key,
        device_name=device_name,
        last_used_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(device)
    db.commit()
    return device_key


def authenticate_device(db: Session, device_key: str, device_id: str) -> User | None:
    """Authenticate using device_key. Returns user if valid."""
    device = (
        db.query(UserDevice)
        .filter(
            UserDevice.device_key == device_key,
            UserDevice.device_id == device_id,
            UserDevice.is_active == True,
        )
        .first()
    )
    if not device:
        return None

    device.last_used_at = datetime.now(timezone.utc)
    user = device.user
    user.last_login_at = datetime.now(timezone.utc)
    user.login_count = (user.login_count or 0) + 1
    db.commit()
    return user
