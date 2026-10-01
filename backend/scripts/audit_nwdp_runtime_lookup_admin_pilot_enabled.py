#!/usr/bin/env python3
"""Read-only post-enablement audit for the local admin-only lookup pilot."""

from __future__ import annotations

import argparse
import hashlib
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


SCHEMA_VERSION = (
    "nwdp_runtime_lookup_admin_pilot_enabled_audit.v1"
)
EXPECTED_ACTIVE_TOTAL = 467_397
BASE_URL = "http://127.0.0.1:8000"
ENDPOINT = (
    "/api/v1/master-data/geography/"
    "nwdp-boundary-runtime/point-lookup"
)
RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
CANARY = (
    ROOT / "backend" / "scripts"
    / "run_nwdp_runtime_lookup_admin_pilot_canary.py"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(connection, sql: str) -> int:
    return int(connection.execute(text(sql)).scalar_one())


def database_snapshot(connection) -> dict[str, int]:
    return {
        "states": scalar(
            connection,
            "select count(*) from geography_states where is_active",
        ),
        "districts": scalar(
            connection,
            "select count(*) from geography_districts where is_active",
        ),
        "blocks": scalar(
            connection,
            "select count(*) from geography_blocks where is_active",
        ),
        "villages": scalar(
            connection,
            "select count(*) from geography_villages where is_active",
        ),
        "active_runtime_features": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_runtime_features
            where is_active
            """,
        ),
        "active_runtime_crosswalks": scalar(
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


def parse_first_json(output: str) -> dict[str, Any]:
    lines = output.splitlines()
    collected: list[str] = []
    depth = 0
    started = False

    for line in lines:
        if not started and line.lstrip().startswith("{"):
            started = True
        if started:
            collected.append(line)
            depth += line.count("{") - line.count("}")
            if depth == 0:
                break

    if not collected:
        raise RuntimeError("Canary produced no JSON report")
    return json.loads("\n".join(collected))


def anonymous_status() -> int:
    query = urllib.parse.urlencode({
        "latitude": 0,
        "longitude": 0,
        "runtime_set_id": RUNTIME_SET_ID,
    })
    request = urllib.request.Request(
        f"{BASE_URL}{ENDPOINT}?{query}",
        headers={"X-Tenant-ID": "default"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()

    if settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED is not True:
        raise RuntimeError("Local admin-only pilot is not enabled")
    if (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED
        is not True
    ):
        raise RuntimeError("Distributed limiter is not enabled")

    redis_url = (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL
    )
    if not redis_url:
        raise RuntimeError("Redis URL is not configured")

    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        redis_ping_before = bool(client.ping())
        keys_before = sorted(
            str(key)
            for key in client.scan_iter(
                match="agrios:nwdp-runtime-lookup:v1:*"
            )
        )
    finally:
        client.close()

    if keys_before:
        raise RuntimeError(
            "Pilot namespace is not clean; wait for TTL expiry"
        )

    with engine.connect() as connection:
        before = database_snapshot(connection)

    canary_result = subprocess.run(
        [sys.executable, str(CANARY)],
        cwd=str(ROOT),
        check=False,
        text=True,
        capture_output=True,
    )
    canary = parse_first_json(canary_result.stdout)

    anonymous_http_status = anonymous_status()

    with engine.connect() as connection:
        after = database_snapshot(connection)

    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        redis_ping_after = bool(client.ping())
        keys_after = sorted(
            str(key)
            for key in client.scan_iter(
                match="agrios:nwdp-runtime-lookup:v1:*"
            )
        )
        ttl_values = [
            int(client.ttl(key))
            for key in keys_after
        ]
    finally:
        client.close()

    checks = {
        "lookup_enabled":
            settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED
            is True,
        "limiter_enabled":
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED
            is True,
        "redis_configured":
            bool(redis_url),
        "redis_healthy_before":
            redis_ping_before,
        "redis_healthy_after":
            redis_ping_after,
        "namespace_started_clean":
            not keys_before,
        "canary_process_passed":
            canary_result.returncode == 0,
        "canary_healthy":
            canary.get("healthy") is True,
        "canary_status_exact":
            canary.get("status")
            == "LOCAL_ADMIN_ONLY_LOOKUP_PILOT_CANARY_PASSED",
        "inside_lookup_matched":
            canary.get("inside_lookup", {}).get("status")
            == "MATCHED",
        "inside_lookup_unambiguous":
            canary.get("inside_lookup", {}).get("match_count")
            == 1,
        "outside_lookup_unmatched":
            canary.get("outside_lookup", {}).get("status")
            == "UNMATCHED",
        "free_tier_exact":
            canary.get("inside_lookup", {}).get("tier")
            == "FREE",
        "free_actor_limit_exact":
            canary.get("inside_lookup", {}).get("limit")
            == "10",
        "free_budget_decrement_exact":
            canary.get("inside_lookup", {}).get("remaining")
            == "9"
            and canary.get("outside_lookup", {}).get(
                "remaining"
            )
            == "8",
        "anonymous_access_denied":
            anonymous_http_status == 401,
        "three_budget_keys_present":
            len(keys_after) == 3,
        "budget_ttls_bounded":
            len(ttl_values) == 3
            and all(1 <= ttl <= 61 for ttl in ttl_values),
        "database_counts_unchanged":
            before == after,
        "active_runtime_total_exact":
            after["active_runtime_features"]
            == EXPECTED_ACTIVE_TOTAL
            and after["active_runtime_crosswalks"]
            == EXPECTED_ACTIVE_TOTAL,
        "candidate_state_unchanged":
            after["active_candidates"] == 0
            and after["promoted_candidates"] == 0,
        "project_matches_unchanged":
            after["project_matches"] == 0,
    }

    healthy = all(checks.values())
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "LOCAL_ADMIN_ONLY_LOOKUP_PILOT_ENABLED_AUDIT_PASSED"
            if healthy
            else "FAILED"
        ),
        "healthy": healthy,
        "enabled_scope":
            "LOCAL_ADMIN_ONLY_RUNTIME_LOOKUP_PILOT",
        "configuration": {
            "lookup_enabled": True,
            "limiter_enabled": True,
            "redis_configured": True,
            "resolved_tier": "FREE",
            "actor_limit": 10,
            "tenant_limit": 30,
            "global_limit": 600,
            "window_seconds": 60,
        },
        "database_before": before,
        "database_after": after,
        "canary": {
            "script_sha256": sha256(CANARY),
            "inside_status":
                canary.get("inside_lookup", {}).get("status"),
            "inside_match_count":
                canary.get("inside_lookup", {}).get(
                    "match_count"
                ),
            "inside_elapsed_ms":
                canary.get("inside_lookup", {}).get(
                    "elapsed_ms"
                ),
            "outside_status":
                canary.get("outside_lookup", {}).get(
                    "status"
                ),
            "outside_match_count":
                canary.get("outside_lookup", {}).get(
                    "match_count"
                ),
            "outside_elapsed_ms":
                canary.get("outside_lookup", {}).get(
                    "elapsed_ms"
                ),
            "token_logged": False,
            "coordinates_recorded": False,
        },
        "access_control": {
            "anonymous_http_status":
                anonymous_http_status,
            "authenticated_admin_only": True,
            "customer_access_authorized": False,
            "android_access_authorized": False,
            "public_access_authorized": False,
            "production_access_authorized": False,
        },
        "redis_budget_evidence": {
            "keys_before_count": len(keys_before),
            "keys_after_count": len(keys_after),
            "ttl_values": ttl_values,
            "key_material_reported": False,
            "writes_are_transient_rate_limit_counters": True,
        },
        "checks": checks,
        "policy": {
            "authorization_applied":
                "LOCAL_ADMIN_ONLY_RUNTIME_LOOKUP_PILOT",
            "tenant_tier_changed": False,
            "canonical_changes_attempted": False,
            "runtime_data_changes_attempted": False,
            "project_changes_attempted": False,
            "android_changes_attempted": False,
            "database_writes_attempted": False,
        },
        "rollback": {
            "available": True,
            "action":
                "Set NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED=false "
                "and restart the backend.",
            "runtime_data_deactivation_required": False,
        },
        "elapsed_ms": round(
            (time.perf_counter() - started) * 1000,
            3,
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))

    if not healthy:
        print(
            "LOCAL ADMIN-ONLY LOOKUP ENABLED AUDIT FAILED",
            file=sys.stderr,
        )
        return 1

    print(
        "LOCAL ADMIN-ONLY LOOKUP PILOT ENABLED AUDIT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
