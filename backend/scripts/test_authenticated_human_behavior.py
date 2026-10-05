#!/usr/bin/env python3
from __future__ import annotations

import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.human_auth import (
    AuthenticatedPrincipal,
    require_authenticated_human,
)
from app.modules.auth.models import User
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


app = FastAPI()


@app.get("/authenticated-human-probe")
def authenticated_human_probe(
    principal: AuthenticatedPrincipal = Depends(
        require_authenticated_human()
    ),
):
    return {
        "user_id": str(principal.user_id),
        "tenant_id": principal.tenant_id,
        "role": principal.role,
        "device_id": principal.device_id,
    }


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main() -> int:
    tenant_id = f"human-auth-{uuid.uuid4().hex[:8]}"
    created_user_ids: list[uuid.UUID] = []
    client = TestClient(app)

    db = SessionLocal()
    try:
        farmer, farmer_headers = create_test_admin(
            db,
            role="FARMER",
            tenant_id=tenant_id,
        )
        farmer_id = farmer.id
        created_user_ids.append(farmer_id)

        stale_user, stale_headers = create_test_admin(
            db,
            role="FIELD_AGENT",
            tenant_id=tenant_id,
        )
        stale_user_id = stale_user.id
        created_user_ids.append(stale_user_id)
    finally:
        db.close()

    try:
        missing = client.get("/authenticated-human-probe")
        require(missing.status_code == 401, "Missing bearer is rejected")

        invalid = client.get(
            "/authenticated-human-probe",
            headers={
                "Authorization": "Bearer invalid-token",
                "X-Tenant-ID": tenant_id,
            },
        )
        require(invalid.status_code == 401, "Invalid bearer is rejected")

        valid = client.get(
            "/authenticated-human-probe",
            headers=farmer_headers,
        )
        require(valid.status_code == 200, "Farmer bearer is accepted")
        require(
            valid.json()["user_id"] == str(farmer_id),
            "Principal uses authenticated subject",
        )
        require(
            valid.json()["role"] == "FARMER",
            "Non-admin role is preserved",
        )
        require(
            valid.json()["tenant_id"] == tenant_id,
            "Verified tenant is returned",
        )
        require(
            valid.json()["device_id"] == "backend-regression",
            "JWT device identity is retained",
        )

        actor_headers = {
            **farmer_headers,
            "X-Actor-ID": str(uuid.uuid4()),
        }
        actor_mismatch = client.get(
            "/authenticated-human-probe",
            headers=actor_headers,
        )
        require(
            actor_mismatch.status_code == 403,
            "Actor mismatch is rejected",
        )

        tenant_headers = {
            **farmer_headers,
            "X-Tenant-ID": f"{tenant_id}-other",
        }
        tenant_mismatch = client.get(
            "/authenticated-human-probe",
            headers=tenant_headers,
        )
        require(
            tenant_mismatch.status_code == 403,
            "Token/header tenant mismatch is rejected",
        )

        db = SessionLocal()
        try:
            stale = db.query(User).filter(User.id == stale_user_id).one()
            stale.tenant_id = f"{tenant_id}-moved"
            db.commit()
        finally:
            db.close()

        persisted_tenant_mismatch = client.get(
            "/authenticated-human-probe",
            headers=stale_headers,
        )
        require(
            persisted_tenant_mismatch.status_code == 403,
            "Persisted-user tenant mismatch is rejected",
        )

        db = SessionLocal()
        try:
            farmer = db.query(User).filter(User.id == farmer_id).one()
            farmer.is_active = False
            db.commit()
        finally:
            db.close()

        inactive = client.get(
            "/authenticated-human-probe",
            headers=farmer_headers,
        )
        require(
            inactive.status_code == 401,
            "Inactive user is rejected",
        )

        print("AUTHENTICATED HUMAN BEHAVIOR PASSED")
        return 0
    finally:
        db = SessionLocal()
        try:
            for user_id in created_user_ids:
                delete_test_admin(db, user_id)
        finally:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
