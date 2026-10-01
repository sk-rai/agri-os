#!/usr/bin/env python3
"""Audit local Redis operations while NWDP runtime lookup stays disabled."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "nwdp_runtime_lookup_local_redis_audit.v1"
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
BASE_URL = os.environ.get(
    "FARMINT_BACKEND_URL",
    "http://127.0.0.1:8000",
).rstrip("/")
LOOKUP_PATH = (
    "/api/v1/master-data/geography/"
    "nwdp-boundary-runtime/point-lookup"
)
RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
REDIS_PATTERN = "agrios:nwdp-runtime-lookup:v1:*"

sys.path.insert(0, str(BACKEND))
from app.core.config import settings  # noqa: E402


def run(
    command: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(ROOT),
        check=check,
        text=True,
        capture_output=True,
    )


def redis_cli(*arguments: str) -> str:
    return run([
        "redis-cli",
        "-h",
        "127.0.0.1",
        "-p",
        "6379",
        "--raw",
        *arguments,
    ]).stdout.strip()


def redis_keys() -> list[str]:
    output = run([
        "redis-cli",
        "-h",
        "127.0.0.1",
        "-p",
        "6379",
        "--scan",
        "--pattern",
        REDIS_PATTERN,
    ]).stdout
    return sorted(
        line.strip()
        for line in output.splitlines()
        if line.strip()
    )


def http_json(
    path: str,
    *,
    headers: dict[str, str] | None = None,
    expected_status: int = 200,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers=headers or {},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read()

    payload = json.loads(body.decode("utf-8"))
    if status != expected_status:
        raise AssertionError(
            f"Expected HTTP {expected_status}, got {status}: {payload}"
        )
    return status, payload


def create_smoke_session() -> dict[str, str]:
    matches = sorted(
        candidate
        for candidate in ROOT.rglob(
            "create_web_ui_smoke_session.py"
        )
        if ".git" not in candidate.parts
    )
    if len(matches) != 1:
        raise RuntimeError(
            "Expected one smoke-session creator; found "
            f"{[str(item) for item in matches]}"
        )

    result = run([
        sys.executable,
        str(matches[0]),
        "--tenant-id",
        "default",
        "--role",
        "ENTERPRISE_ADMIN",
        "--format",
        "json",
    ])
    payload = json.loads(result.stdout)

    token = (
        payload.get("access_token")
        or payload.get("token")
        or payload.get("bearer_token")
    )
    actor_id = payload.get("actor_id")
    if not token or not actor_id:
        raise RuntimeError(
            "Smoke-session output lacks token or actor identity"
        )

    return {
        "token": str(token),
        "actor_id": str(actor_id),
        "tenant_id": str(
            payload.get("tenant_id") or "default"
        ),
        "role": str(
            payload.get("role") or "ENTERPRISE_ADMIN"
        ),
    }


def main() -> int:
    started = time.perf_counter()

    service_active = run([
        "systemctl",
        "is-active",
        "redis-server",
    ]).stdout.strip()
    service_enabled = run([
        "systemctl",
        "is-enabled",
        "redis-server",
    ]).stdout.strip()

    ping = redis_cli("PING")
    server_info = redis_cli("INFO", "server")
    bind = redis_cli(
        "CONFIG",
        "GET",
        "bind",
    ).splitlines()
    protected = redis_cli(
        "CONFIG",
        "GET",
        "protected-mode",
    ).splitlines()
    port = redis_cli(
        "CONFIG",
        "GET",
        "port",
    ).splitlines()
    sockets = run(["ss", "-ltn"]).stdout

    _, health = http_json("/health")
    _, openapi = http_json("/openapi.json")

    keys_before = redis_keys()
    session = create_smoke_session()

    query = urllib.parse.urlencode({
        "latitude": "28.6139",
        "longitude": "77.2090",
        "runtime_set_id": RUNTIME_SET_ID,
    })
    status, disabled = http_json(
        f"{LOOKUP_PATH}?{query}",
        headers={
            "Authorization": f"Bearer {session['token']}",
            "X-Tenant-ID": session["tenant_id"],
        },
        expected_status=503,
    )
    keys_after = redis_keys()

    detail = disabled.get("detail", {})
    disabled_code = (
        detail.get("code")
        if isinstance(detail, dict)
        else None
    )

    checks = {
        "redis_service_active":
            service_active == "active",
        "redis_service_enabled":
            service_enabled == "enabled",
        "redis_ping":
            ping == "PONG",
        "redis_metadata_present":
            "redis_version:" in server_info,
        "redis_loopback_bind":
            (
                "127.0.0.1 ::1" in bind
                or (
                    "127.0.0.1" in bind
                    and "::1" in bind
                )
            ),
        "redis_protected_mode":
            "yes" in protected,
        "redis_port_exact":
            "6379" in port,
        "no_wildcard_listener":
            "0.0.0.0:6379" not in sockets
            and "[::]:6379" not in sockets,
        "lookup_flag_disabled":
            settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED
            is False,
        "limiter_flag_enabled":
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED
            is True,
        "redis_url_exact":
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL
            == "redis://127.0.0.1:6379/0",
        "namespace_exact":
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE
            == "agrios:nwdp-runtime-lookup:v1",
        "backend_health":
            health.get("status") == "ok",
        "lookup_route_present":
            LOOKUP_PATH in openapi.get("paths", {}),
        "authenticated_session_created":
            bool(session["actor_id"]),
        "disabled_lookup_status":
            status == 503,
        "disabled_lookup_code":
            disabled_code
            == "NWDP_RUNTIME_LOOKUP_DISABLED",
        "redis_keys_unchanged":
            keys_before == keys_after,
        "no_budget_consumption":
            len(keys_before) == len(keys_after),
    }

    healthy = all(checks.values())
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "LOCAL_REDIS_OPERATIONAL_AUDIT_PASSED_LOOKUP_DISABLED"
            if healthy
            else "FAILED"
        ),
        "healthy": healthy,
        "configuration": {
            "lookup_enabled":
                settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED,
            "rate_limiter_enabled":
                settings
                .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED,
            "redis_url_configured": bool(
                settings
                .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL
            ),
            "redis_endpoint": "127.0.0.1:6379",
            "namespace":
                settings
                .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE,
        },
        "redis_service": {
            "active": service_active,
            "enabled": service_enabled,
            "ping": ping,
            "loopback_only":
                checks["redis_loopback_bind"]
                and checks["no_wildcard_listener"],
            "protected_mode":
                checks["redis_protected_mode"],
        },
        "live_backend": {
            "base_url": BASE_URL,
            "health_status": health.get("status"),
            "lookup_route_present":
                checks["lookup_route_present"],
            "authenticated_lookup_status": status,
            "authenticated_lookup_code": disabled_code,
        },
        "redis_budget_keys": {
            "pattern": REDIS_PATTERN,
            "before_count": len(keys_before),
            "after_count": len(keys_after),
            "unchanged": keys_before == keys_after,
        },
        "authentication": {
            "tenant_id": session["tenant_id"],
            "actor_id": session["actor_id"],
            "role": session["role"],
            "token_logged": False,
        },
        "checks": checks,
        "policy": {
            "lookup_enablement_authorized": False,
            "lookup_exposure_changed": False,
            "redis_service_stopped": False,
            "redis_configuration_changed": False,
            "geography_database_writes_attempted": False,
            "runtime_boundary_changes_attempted": False,
            "project_changes_attempted": False,
            "android_changes_attempted": False,
            "temporary_authentication_session_created": True,
        },
        "remaining_production_gates": [
            "production Redis secret and TLS configuration",
            "multi-replica shared-budget and failover testing",
            "monitoring and alerts",
            "separate lookup-enablement authorization",
        ],
        "elapsed_ms": round(
            (time.perf_counter() - started) * 1000,
            3,
        ),
    }

    print(json.dumps(report, indent=2, sort_keys=True))

    if not healthy:
        print(
            "NWDP LOCAL REDIS OPERATIONAL AUDIT FAILED",
            file=sys.stderr,
        )
        return 1

    print(
        "NWDP LOCAL REDIS OPERATIONAL AUDIT PASSED; "
        "LOOKUP REMAINS DISABLED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
