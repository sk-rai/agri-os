"""Provision an existing authenticated user for admin access.

Usage:
  PYTHONPATH=. ../venv/bin/python scripts/provision_admin.py \
    --mobile +919876543210 --tenant default --role ENTERPRISE_ADMIN
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.admin_auth import ROLE_PERMISSIONS
from app.core.database import SessionLocal
from app.modules.auth.models import User


def normalize_mobile(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    raise ValueError("Mobile must be a valid 10-digit Indian number.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Assign a tenant admin role to an existing user.")
    parser.add_argument("--mobile", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--role", choices=sorted(ROLE_PERMISSIONS), default="ENTERPRISE_ADMIN")
    args = parser.parse_args()

    mobile = normalize_mobile(args.mobile)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.mobile_number == mobile, User.is_active == True).first()
        if not user:
            raise SystemExit(f"No active user exists for {mobile}. Log in once before provisioning.")
        user.role = args.role
        user.tenant_id = args.tenant
        db.commit()
        print(f"Provisioned user {user.id} as {args.role} for tenant {args.tenant}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
