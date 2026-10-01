#!/usr/bin/env python3
"""Live authenticated canary for the local admin-only lookup pilot."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from redis import Redis
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import settings  # noqa: E402
from app.core.database import engine  # noqa: E402


SCHEMA_VERSION = "nwdp_runtime_lookup_admin_pilot_canary.v1"
BASE_URL = "http://127.0.0.1:8000"
ENDPOINT = (
    "/api/v1/master-data/geography/"
    "nwdp-boundary-runtime/point-lookup"
)
RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
EXPECTED_ACTIVE_TOTAL = 467_397
NAMESPACE = "agrios:nwdp-runtime-lookup:v1"


def scalar(connection, sql: str) -> int:
    return int(connection.execute(text(sql)).scalar_one())


def database_counts(connection) -> dict[str, int]:
    return {
        "active_features": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_runtime_features
            where is_active
            """,
        ),
        "active_crosswalks": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_runtime_crosswalks
            where is_active
            """,
        ),
        "active_candidates": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_crosswalk_candidates
            where is_active
            """,
        ),
        "promoted_candidates": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_crosswalk_candidates
            where promotion_status = 'PROMOTED'
            """,
        ),
        "project_matches": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_project_matches
            """,
        ),
    }


def create_session() -> dict[str, str]:
    matches = sorted(
        candidate
        for candidate in ROOT.rglob(
            "create_web_ui_smoke_session.py"
        )
        if ".git" not in candidate.parts
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one session creator, found {matches}"
        )

    result = subprocess.run(
        [
            sys.executable,
            str(matches[0]),
            "--tenant-id",
            "default",
            "--role",
            "ENTERPRISE_ADMIN",
            "--format",
            "json",
        ],
        cwd=str(ROOT),
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    token = (
        payload.get("access_token")
        or payload.get("token")
        or payload.get("bearer_token")
    )
    if not token or not payload.get("actor_id"):
        raise RuntimeError("Session output is incomplete")

    return {
        "token": str(token),
        "actor_id": str(payload["actor_id"]),
        "tenant_id": str(
            payload.get("tenant_id") or "default"
        ),
        "role": str(
            payload.get("role") or "ENTERPRISE_ADMIN"
        ),
    }


def request_lookup(
    *,
    token: str,
    tenant_id: str,
    latitude: float,
    longitude: float,
) -> tuple[int, dict[str, Any], dict[str, str], float]:
    query = urllib.parse.urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "runtime_set_id": RUNTIME_SET_ID,
    })
    request = urllib.request.Request(
        f"{BASE_URL}{ENDPOINT}?{query}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_id,
        },
        method="GET",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:
            status = response.status
            payload = json.loads(
                response.read().decode("utf-8")
            )
            headers = {
                key.lower(): value
                for key, value in response.headers.items()
            }
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = json.loads(exc.read().decode("utf-8"))
        headers = {
            key.lower(): value
            for key, value in exc.headers.items()
        }

    elapsed_ms = (
        time.perf_counter() - started
    ) * 1000
    return status, payload, headers, elapsed_ms


def scan_keys(client: Redis) -> list[str]:
    return sorted(
        str(key)
        for key in client.scan_iter(
            match=f"{NAMESPACE}:*"
        )
    )


def main() -> int:
    if settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED is not True:
        raise RuntimeError(
            "Pilot canary requires lookup enabled"
        )
    if (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED
        is not True
    ):
        raise RuntimeError(
            "Pilot canary requires limiter enabled"
        )

    redis_url = (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL
    )
    if not redis_url:
        raise RuntimeError("Redis URL is not configured")

    redis_client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )

    with engine.connect() as connection:
        before = database_counts(connection)
        sample = connection.execute(
            text("""
                select
                  rf.id::text as runtime_feature_id,
                  rw.village_id::text as village_id,
                  ST_Y(
                    ST_PointOnSurface(
                      rf.geometry_wgs84_geom
                    )
                  ) as latitude,
                  ST_X(
                    ST_PointOnSurface(
                      rf.geometry_wgs84_geom
                    )
                  ) as longitude
                from geography_boundary_runtime_features rf
                join geography_boundary_runtime_crosswalks rw
                  on rw.runtime_feature_id = rf.id
                 and rw.runtime_set_id = rf.runtime_set_id
                 and rw.is_active
                where rf.runtime_set_id =
                      cast(:runtime_set_id as uuid)
                  and rf.is_active
                  and rf.geometry_wgs84_geom is not null
                order by rf.id
                limit 1
            """),
            {"runtime_set_id": RUNTIME_SET_ID},
        ).mappings().one()

        keys_before = scan_keys(redis_client)
        session = create_session()

        (
            inside_status,
            inside,
            inside_headers,
            inside_ms,
        ) = request_lookup(
            token=session["token"],
            tenant_id=session["tenant_id"],
            latitude=float(sample["latitude"]),
            longitude=float(sample["longitude"]),
        )

        (
            outside_status,
            outside,
            outside_headers,
            outside_ms,
        ) = request_lookup(
            token=session["token"],
            tenant_id=session["tenant_id"],
            latitude=0.0,
            longitude=0.0,
        )

        after = database_counts(connection)
        keys_after = scan_keys(redis_client)

        new_keys = sorted(
            set(keys_after) - set(keys_before)
        )
        ttl_values = [
            int(redis_client.ttl(key))
            for key in new_keys
        ]

    redis_client.close()

    checks = {
        "inside_status_ok":
            inside_status == 200,
        "inside_schema_exact":
            inside.get("schema_version")
            == "nwdp_boundary_runtime_point_lookup.v1",
        "inside_matched":
            inside.get("status") == "MATCHED",
        "inside_unambiguous":
            inside.get("match_count") == 1,
        "expected_feature_returned":
            inside.get("runtime_feature_id")
            == sample["runtime_feature_id"],
        "expected_village_returned":
            inside.get("village_id")
            == sample["village_id"],
        "runtime_set_exact":
            inside.get("runtime_set_id")
            == RUNTIME_SET_ID,
        "outside_status_ok":
            outside_status == 200,
        "outside_unmatched":
            outside.get("status") == "UNMATCHED"
            and outside.get("match_count") == 0,
        "inside_tier_free":
            inside_headers.get("x-ratelimit-tier")
            == "FREE",
        "outside_tier_free":
            outside_headers.get("x-ratelimit-tier")
            == "FREE",
        "inside_actor_limit_exact":
            inside_headers.get("ratelimit-limit")
            == "10",
        "inside_remaining_exact":
            inside_headers.get("ratelimit-remaining")
            == "9",
        "outside_remaining_exact":
            outside_headers.get("ratelimit-remaining")
            == "8",
        "reset_headers_present":
            bool(inside_headers.get("ratelimit-reset"))
            and bool(outside_headers.get("ratelimit-reset")),
        "three_budget_keys_created":
            len(new_keys) == 3,
        "budget_key_ttls_bounded":
            len(ttl_values) == 3
            and all(
                1 <= ttl <= 61
                for ttl in ttl_values
            ),
        "database_counts_unchanged":
            before == after,
        "active_runtime_total_exact":
            after["active_features"]
            == EXPECTED_ACTIVE_TOTAL
            and after["active_crosswalks"]
            == EXPECTED_ACTIVE_TOTAL,
        "candidate_state_unchanged":
            after["active_candidates"] == 0
            and after["promoted_candidates"] == 0,
        "project_matches_unchanged":
            after["project_matches"] == 0,
        "inside_latency_bounded":
            inside_ms < 1000,
        "outside_latency_bounded":
            outside_ms < 1000,
    }

    healthy = all(checks.values())
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "LOCAL_ADMIN_ONLY_LOOKUP_PILOT_CANARY_PASSED"
            if healthy
            else "FAILED"
        ),
        "healthy": healthy,
        "authorized_scope":
            "LOCAL_ADMIN_ONLY_RUNTIME_LOOKUP_PILOT",
        "database_before": before,
        "database_after": after,
        "inside_lookup": {
            "http_status": inside_status,
            "status": inside.get("status"),
            "match_count": inside.get("match_count"),
            "expected_feature_present":
                checks["expected_feature_returned"],
            "expected_village_present":
                checks["expected_village_returned"],
            "elapsed_ms": round(inside_ms, 3),
            "tier": inside_headers.get(
                "x-ratelimit-tier"
            ),
            "limit": inside_headers.get(
                "ratelimit-limit"
            ),
            "remaining": inside_headers.get(
                "ratelimit-remaining"
            ),
        },
        "outside_lookup": {
            "http_status": outside_status,
            "status": outside.get("status"),
            "match_count": outside.get("match_count"),
            "elapsed_ms": round(outside_ms, 3),
            "tier": outside_headers.get(
                "x-ratelimit-tier"
            ),
            "remaining": outside_headers.get(
                "ratelimit-remaining"
            ),
        },
        "redis_budget_evidence": {
            "keys_before_count": len(keys_before),
            "keys_after_count": len(keys_after),
            "new_key_count": len(new_keys),
            "ttl_values": ttl_values,
            "key_material_reported": False,
        },
        "authentication": {
            "tenant_id": session["tenant_id"],
            "actor_id": session["actor_id"],
            "role": session["role"],
            "token_logged": False,
        },
        "checks": checks,
        "policy": {
            "customer_access_authorized": False,
            "android_access_authorized": False,
            "public_access_authorized": False,
            "production_access_authorized": False,
            "tenant_tier_changed": False,
            "canonical_changes_attempted": False,
            "runtime_data_changes_attempted": False,
            "project_changes_attempted": False,
            "database_writes_attempted": False,
        },
        "rollback_command": (
            "Set NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED=false "
            "and restart the backend."
        ),
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    if not healthy:
        print(
            "LOCAL ADMIN-ONLY LOOKUP PILOT CANARY FAILED",
            file=sys.stderr,
        )
        return 1

    print(
        "LOCAL ADMIN-ONLY LOOKUP PILOT CANARY PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
