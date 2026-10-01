#!/usr/bin/env python3
"""Endpoint regression for guarded distributed NWDP lookup limits."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
import app.modules.master_data.api.geography as geography
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)


ENDPOINT = (
    "/api/v1/master-data/geography/"
    "nwdp-boundary-runtime/point-lookup"
)
RUNTIME_SET_ID = (
    "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
)


def check(condition, label, evidence=None):
    if not condition:
        raise AssertionError(
            f"{label}: {evidence!r}"
        )
    print(f"PASS {label}")


def request(client, headers):
    return client.get(
        ENDPOINT,
        params={
            "latitude": 0,
            "longitude": 0,
            "runtime_set_id": RUNTIME_SET_ID,
        },
        headers=headers,
    )


def main():
    client = TestClient(app)
    db = SessionLocal()
    admin = None

    original_lookup = (
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED
    )
    original_limiter = (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED
    )
    original_enforce = (
        geography
        .enforce_nwdp_runtime_lookup_rate_limit
    )

    calls = []

    try:
        admin, headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id="default",
        )

        def should_not_run(principal, session, response):
            calls.append("unexpected")
            raise AssertionError(
                "Limiter ran while lookup was disabled"
            )

        geography.enforce_nwdp_runtime_lookup_rate_limit = (
            should_not_run
        )
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED = False
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED = (
            True
        )

        disabled = request(client, headers)
        check(
            disabled.status_code == 503,
            "Disabled lookup returns 503",
            disabled.text,
        )
        check(
            disabled.json()["detail"]["code"]
            == "NWDP_RUNTIME_LOOKUP_DISABLED",
            "Disabled lookup keeps stable code",
            disabled.text,
        )
        check(
            calls == [],
            "Disabled lookup never contacts limiter",
            calls,
        )

        def allow(principal, session, response):
            calls.append({
                "actor": str(principal.user_id),
                "tenant": principal.tenant_id,
            })
            response.headers["RateLimit-Limit"] = "120"
            response.headers["RateLimit-Remaining"] = "119"
            response.headers["RateLimit-Reset"] = "60"
            response.headers["X-RateLimit-Tier"] = "PRO"

        geography.enforce_nwdp_runtime_lookup_rate_limit = allow
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED = True
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED = (
            True
        )

        allowed = request(client, headers)
        check(
            allowed.status_code == 200,
            "Allowed request reaches spatial lookup",
            allowed.text,
        )
        check(
            allowed.json()["status"] == "UNMATCHED",
            "Outside point remains unmatched",
            allowed.json(),
        )
        check(
            len(calls) == 1,
            "Limiter runs exactly once before lookup",
            calls,
        )
        check(
            calls[0]["tenant"] == "default",
            "Limiter receives authenticated tenant",
            calls,
        )
        check(
            calls[0]["actor"] == str(admin.id),
            "Limiter receives authenticated actor",
            calls,
        )
        check(
            allowed.headers["X-RateLimit-Tier"] == "PRO",
            "Allowed response returns resolved tier",
            dict(allowed.headers),
        )
        check(
            allowed.headers["RateLimit-Remaining"] == "119",
            "Allowed response returns remaining budget",
            dict(allowed.headers),
        )

        def reject(principal, session, response):
            raise HTTPException(
                status_code=429,
                detail={
                    "code":
                        "NWDP_RUNTIME_LOOKUP_RATE_LIMITED",
                    "message":
                        "Runtime geography lookup quota exceeded",
                    "dimension": "tenant",
                    "tier": "STANDARD",
                },
                headers={
                    "Retry-After": "45",
                    "RateLimit-Limit": "120",
                    "RateLimit-Remaining": "0",
                    "RateLimit-Reset": "45",
                    "X-RateLimit-Tier": "STANDARD",
                },
            )

        geography.enforce_nwdp_runtime_lookup_rate_limit = reject
        rejected = request(client, headers)
        check(
            rejected.status_code == 429,
            "Exhausted request returns 429",
            rejected.text,
        )
        check(
            rejected.json()["detail"]["code"]
            == "NWDP_RUNTIME_LOOKUP_RATE_LIMITED",
            "Exhausted response has stable code",
            rejected.text,
        )
        check(
            rejected.json()["detail"]["dimension"] == "tenant",
            "Exhausted response identifies tenant dimension",
            rejected.json(),
        )
        check(
            rejected.json()["detail"]["tier"] == "STANDARD",
            "Exhausted response identifies customer tier",
            rejected.json(),
        )
        check(
            rejected.headers["Retry-After"] == "45",
            "Exhausted response includes Retry-After",
            dict(rejected.headers),
        )

        def unavailable(principal, session, response):
            raise HTTPException(
                status_code=503,
                detail={
                    "code":
                        "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
                    "message":
                        "Distributed rate-limit backend "
                        "is unavailable",
                },
            )

        geography.enforce_nwdp_runtime_lookup_rate_limit = (
            unavailable
        )
        unavailable_response = request(client, headers)
        check(
            unavailable_response.status_code == 503,
            "Limiter backend failure returns 503",
            unavailable_response.text,
        )
        check(
            unavailable_response.json()["detail"]["code"]
            == "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
            "Limiter failure has stable code",
            unavailable_response.text,
        )

        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED = True
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED = (
            False
        )

        calls.clear()

        def disabled_limiter(principal, session, response):
            calls.append("disabled-path")
            return None

        geography.enforce_nwdp_runtime_lookup_rate_limit = (
            disabled_limiter
        )
        limiter_disabled = request(client, headers)
        check(
            limiter_disabled.status_code == 200,
            "Disabled limiter preserves guarded lookup behavior",
            limiter_disabled.text,
        )
        check(
            calls == ["disabled-path"],
            "Endpoint consistently invokes limiter boundary",
            calls,
        )
        check(
            "X-RateLimit-Tier"
            not in limiter_disabled.headers,
            "Disabled limiter exposes no customer tier",
            dict(limiter_disabled.headers),
        )

        print(
            "NWDP RUNTIME LOOKUP RATE-LIMIT "
            "ENDPOINT REGRESSION PASSED"
        )
        return 0
    finally:
        geography.enforce_nwdp_runtime_lookup_rate_limit = (
            original_enforce
        )
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED = (
            original_lookup
        )
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED = (
            original_limiter
        )
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
