"""Shared authenticated admin identities for backend regression scripts."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.service import create_jwt


def create_test_admin(
    db: Session,
    *,
    role: str = "ENTERPRISE_ADMIN",
    tenant_id: str = "default",
) -> tuple[User, dict[str, str]]:
    user = User(
        id=uuid.uuid4(),
        mobile_number=f"+9198{uuid.uuid4().int % 100000000:08d}",
        role=role,
        display_name=f"{role} regression user",
        tenant_id=tenant_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    token, _ = create_jwt(user, "backend-regression")
    return user, {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": tenant_id,
        "X-Actor-ID": str(user.id),
    }


def delete_test_admin(db: Session, user_id: uuid.UUID) -> None:
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()
