#!/usr/bin/env python3
"""Read-only audit for web UI authenticated smoke-test readiness."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal


def _model(name: str):
    import app.modules.auth.models as auth_models
    import app.modules.farmer.models as farmer_models

    return getattr(auth_models, name, None) or getattr(farmer_models, name, None)


def _safe_obj(row: Any, fields: list[str]) -> dict[str, Any]:
    result = {}
    for field in fields:
        if hasattr(row, field):
            value = getattr(row, field)
            result[field] = str(value) if value is not None else None
    return result


def _count(db, model) -> int | None:
    if model is None:
        return None
    return db.query(model).count()


def main() -> int:
    Tenant = _model("Tenant")
    User = _model("User")
    AdminProfile = _model("AdminProfile")
    UserRole = _model("UserRole")
    Role = _model("Role")

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).limit(20).all() if Tenant is not None else []
        users = db.query(User).limit(20).all() if User is not None else []
        admin_profiles = db.query(AdminProfile).limit(20).all() if AdminProfile is not None else []
        roles = db.query(Role).limit(30).all() if Role is not None else []
        user_roles = db.query(UserRole).limit(30).all() if UserRole is not None else []

        result = {
            "schema_version": "web_ui_auth_readiness_audit.v1",
            "counts": {
                "tenants": _count(db, Tenant),
                "users": _count(db, User),
                "admin_profiles": _count(db, AdminProfile),
                "roles": _count(db, Role),
                "user_roles": _count(db, UserRole),
            },
            "tenants": [_safe_obj(row, ["id", "name", "slug", "status", "tenant_type", "type"]) for row in tenants],
            "sample_users": [_safe_obj(row, ["id", "tenant_id", "mobile_number", "email", "display_name", "status", "user_type", "role"]) for row in users],
            "sample_admin_profiles": [_safe_obj(row, ["id", "tenant_id", "user_id", "role", "status", "display_name", "email"]) for row in admin_profiles],
            "sample_roles": [_safe_obj(row, ["id", "tenant_id", "code", "name", "role", "status"]) for row in roles],
            "sample_user_roles": [_safe_obj(row, ["id", "tenant_id", "user_id", "role_id", "role", "status"]) for row in user_roles],
            "recommended_next_actions": [
                "If an active admin/backoffice user exists, generate or reuse a safe local dev token for Playwright localStorage.",
                "If no suitable admin exists, create an idempotent local-only UI smoke admin seed script.",
                "Do not print secrets or committed tokens; pass token through WEB_SWEEP_TOKEN or --token only.",
            ],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
