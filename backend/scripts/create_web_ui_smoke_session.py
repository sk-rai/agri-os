#!/usr/bin/env python3
"""Create a local web UI smoke-test session from an existing admin user.

Prints a short-lived dev JWT for local Playwright/browser smoke testing. It does
not write to the database and should not be used in production.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.auth.service import create_jwt

ADMIN_ROLES = ["ENTERPRISE_ADMIN", "TENANT_ADMIN", "ADMIN_VIEWER"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create local web UI smoke JWT from an existing admin user.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--role", choices=ADMIN_ROLES, default="ENTERPRISE_ADMIN")
    parser.add_argument("--user-id")
    parser.add_argument("--device-id", default="web-ui-smoke")
    parser.add_argument("--format", choices=["json", "exports"], default="json")
    args = parser.parse_args()

    db = SessionLocal()
    try:
      query = db.query(User)
      if args.user_id:
          query = query.filter(User.id == args.user_id)
      else:
          query = query.filter(User.tenant_id == args.tenant_id, User.role == args.role)
      user = query.order_by(User.created_at.desc()).first()

      if not user:
          print(json.dumps({
              "schema_version": "web_ui_smoke_session.v1",
              "status": "NO_USER_FOUND",
              "tenant_id": args.tenant_id,
              "role": args.role,
              "message": "No matching existing user found. Run audit_web_ui_auth_readiness.py to inspect candidates.",
          }, indent=2, sort_keys=True))
          return 1

      token, expires_in = create_jwt(user, args.device_id)
      payload = {
          "schema_version": "web_ui_smoke_session.v1",
          "status": "CREATED",
          "tenant_id": user.tenant_id or args.tenant_id,
          "actor_id": str(user.id),
          "role": user.role,
          "display_name": getattr(user, "display_name", None),
          "mobile_number": getattr(user, "mobile_number", None),
          "expires_in_seconds": expires_in,
          "token": token,
          "usage": {
              "web_sweep_env": "Set WEB_SWEEP_TOKEN, WEB_SWEEP_TENANT_ID, and WEB_SWEEP_ACTOR_ID before running admin_smoke_screenshot_sweep.mjs.",
          },
      }

      if args.format == "exports":
          print(f"export WEB_SWEEP_TOKEN='{token}'")
          print(f"export WEB_SWEEP_TENANT_ID='{payload['tenant_id']}'")
          print(f"export WEB_SWEEP_ACTOR_ID='{payload['actor_id']}'")
      else:
          print(json.dumps(payload, indent=2, sort_keys=True))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
