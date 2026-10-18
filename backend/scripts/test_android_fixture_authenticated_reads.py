#!/usr/bin/env python3
"""Token-safe authenticated-read preflight for persisted Android fixtures.

The optional OTP path uses the normal OTP verification endpoint, retains all
credentials in memory, and removes the one-time OTP/device records it creates.
No token, OTP, device key, secret, or full authentication response is printed.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from jose import jwt

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth import service
from app.modules.auth.models import OTPRecord, User, UserDevice


TENANT_ID = "android-dynamic-test"
DYNAMIC_PROJECT_ID = "0f7e0a6b-8472-5d6d-8a14-a9d000000001"
FIXTURES = {
    "dynamic": {
        "mobile": "+919900000002",
        "reads": [
            ("/api/v1/soil-profiles", {}),
            (
                "/api/v1/profile/land-intelligence-context",
                {"pin_code": "560001", "project_id": DYNAMIC_PROJECT_ID},
            ),
            (
                "/api/v1/profile/land-intelligence-summary",
                {
                    "pin_code": "560001",
                    "project_id": DYNAMIC_PROJECT_ID,
                    "language_code": "en",
                },
            ),
        ],
    },
    "crop": {
        "mobile": "+919900000003",
        "farmer_id": "4df387e8-114f-5c44-a129-a9d000000003",
        "reads": [
            ("/api/v1/crop-cycles", {"status": "ACTIVE"}),
            (
                "/api/v1/crop-cycles/eligible-parcels",
                {
                    "farmer_id": "4df387e8-114f-5c44-a129-a9d000000003",
                    "season": "KHARIF",
                },
            ),
        ],
    },
}


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def direct_fixture_token(user: User, device_id: str) -> str:
    token, _ = service.create_jwt(user, device_id)
    return token


def otp_fixture_token(client: TestClient, db, user: User, device_id: str) -> tuple[str, uuid.UUID, list[uuid.UUID]]:
    """Exercise normal OTP verify without exposing credentials or retaining test auth rows."""
    prior_unused_ids = [
        row.id
        for row in db.query(OTPRecord).filter(
            OTPRecord.mobile_number == user.mobile_number,
            OTPRecord.is_used == False,
        ).all()
    ]
    otp = service.request_otp(db, user.mobile_number)
    created_otp = db.query(OTPRecord).filter(
        OTPRecord.mobile_number == user.mobile_number,
    ).order_by(OTPRecord.created_at.desc()).first()
    response = client.post(
        "/api/v1/auth/otp/verify",
        json={
            "mobile_number": user.mobile_number,
            "otp_code": otp,
            "device_id": device_id,
            "device_name": "backend fixture auth preflight",
        },
    )
    check(response.status_code == 200, "normal OTP verification issues credentials")
    payload = response.json()
    check(str(payload.get("user_id")) == str(user.id), "OTP response user matches persisted fixture user")
    check(payload.get("tenant_id") == TENANT_ID, "OTP response tenant matches fixture tenant")
    token = str(payload.get("access_token") or "")
    check(bool(token), "OTP response contains an in-memory bearer credential")
    return token, created_otp.id, prior_unused_ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", choices=sorted(FIXTURES))
    parser.add_argument(
        "--exercise-otp",
        action="store_true",
        help="Exercise normal OTP verification and clean its temporary auth rows.",
    )
    args = parser.parse_args()
    fixture = FIXTURES[args.fixture]
    device_id = f"fixture-auth-preflight-{args.fixture}-{uuid.uuid4()}"
    client = TestClient(app)
    db = SessionLocal()
    created_otp_id = None
    prior_unused_ids = []
    try:
        user = db.query(User).filter(User.mobile_number == fixture["mobile"]).first()
        check(user is not None, "fixture user exists")
        check(user.is_active is True, "fixture user is active")
        check(user.role == "FARMER", "fixture user role is FARMER")
        check(user.tenant_id == TENANT_ID, "persisted user tenant matches fixture tenant")

        if args.exercise_otp:
            token, created_otp_id, prior_unused_ids = otp_fixture_token(
                client, db, user, device_id
            )
        else:
            token = direct_fixture_token(user, device_id)
        claims = jwt.decode(token, service.JWT_SECRET, algorithms=[service.JWT_ALGORITHM])
        check(claims.get("sub") == str(user.id), "JWT subject matches persisted fixture user")
        check(claims.get("tenant_id") == TENANT_ID, "JWT tenant matches fixture tenant")

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": TENANT_ID,
            "X-Actor-ID": str(user.id),
        }
        for path, params in fixture["reads"]:
            response = client.get(path, params=params, headers=headers)
            check(response.status_code == 200, f"protected GET accepts compatible headers: {path}")
            if path.endswith("land-intelligence-context"):
                check(
                    response.json().get("schema_version")
                    == "land_intelligence_context.v1",
                    "project-scoped land context schema is stable",
                )
            elif path.endswith("land-intelligence-summary"):
                payload = response.json()
                check(
                    payload.get("schema_version")
                    == "land_intelligence_summary.v1",
                    "project-scoped land summary schema is stable",
                )
                check(
                    payload.get("tenant_id") == TENANT_ID,
                    "project-scoped land summary reports verified tenant",
                )
                contract = payload.get("android_contract") or {}
                check(
                    contract.get("display_as_informational_only") is True
                    and contract.get("do_not_block_onboarding") is True,
                    "project-scoped land summary remains informational",
                )
    finally:
        if args.exercise_otp:
            db.query(UserDevice).filter(UserDevice.device_id == device_id).delete(
                synchronize_session=False
            )
            if created_otp_id:
                db.query(OTPRecord).filter(OTPRecord.id == created_otp_id).delete(
                    synchronize_session=False
                )
            if prior_unused_ids:
                db.query(OTPRecord).filter(OTPRecord.id.in_(prior_unused_ids)).update(
                    {"is_used": False}, synchronize_session=False
                )
            db.commit()
        db.close()

    print("ANDROID FIXTURE AUTHENTICATED-READ PREFLIGHT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
