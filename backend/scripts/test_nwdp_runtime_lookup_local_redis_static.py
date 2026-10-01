#!/usr/bin/env python3
"""Static contract for the local Redis operational audit."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    ROOT
    / "backend"
    / "scripts"
    / "audit_nwdp_runtime_lookup_local_redis.py"
)


def main() -> int:
    source = AUDIT.read_text(encoding="utf-8")

    contracts = [
        (
            'SCHEMA_VERSION = "nwdp_runtime_lookup_local_redis_audit.v1"',
            "Audit schema is pinned",
        ),
        (
            '"http://127.0.0.1:8000"',
            "Local backend endpoint is explicit",
        ),
        (
            '"agrios:nwdp-runtime-lookup:v1:*"',
            "Farmint Redis namespace is explicit",
        ),
        (
            '"e5f93e27-a0bd-5c8b-bef3-d97986e14c55"',
            "Runtime set identity is pinned",
        ),
        (
            '"create_web_ui_smoke_session.py"',
            "Existing authenticated session creator is reused",
        ),
        (
            '"ENTERPRISE_ADMIN"',
            "Authenticated admin boundary is exercised",
        ),
        (
            '"NWDP_RUNTIME_LOOKUP_DISABLED"',
            "Stable disabled lookup code is required",
        ),
        (
            '"lookup_flag_disabled"',
            "Lookup must remain disabled",
        ),
        (
            '"limiter_flag_enabled"',
            "Configured limiter is verified",
        ),
        (
            '"redis_service_active"',
            "Redis active state is verified",
        ),
        (
            '"redis_service_enabled"',
            "Redis restart persistence is verified",
        ),
        (
            '"redis_loopback_bind"',
            "Loopback binding is verified",
        ),
        (
            '"redis_protected_mode"',
            "Protected mode is verified",
        ),
        (
            '"no_wildcard_listener"',
            "Wildcard listeners are rejected",
        ),
        (
            '"redis_keys_unchanged"',
            "Redis budget keys are compared",
        ),
        (
            '"no_budget_consumption"',
            "Disabled lookup cannot consume a budget",
        ),
        (
            '"token_logged": False',
            "Credential token is not reported",
        ),
        (
            '"lookup_enablement_authorized": False',
            "Lookup enablement remains unauthorized",
        ),
        (
            '"lookup_exposure_changed": False',
            "Lookup exposure remains unchanged",
        ),
        (
            '"redis_service_stopped": False',
            "Audit never stops Redis",
        ),
        (
            '"redis_configuration_changed": False',
            "Audit does not change Redis configuration",
        ),
        (
            '"geography_database_writes_attempted": False',
            "Geography audit remains read-only",
        ),
        (
            '"runtime_boundary_changes_attempted": False',
            "Runtime boundaries remain unchanged",
        ),
        (
            '"project_changes_attempted": False',
            "Projects remain unchanged",
        ),
        (
            '"android_changes_attempted": False',
            "Android remains unchanged",
        ),
        (
            '"LOCAL_REDIS_OPERATIONAL_AUDIT_PASSED_LOOKUP_DISABLED"',
            "Success status retains disabled lookup",
        ),
    ]

    for needle, label in contracts:
        if needle not in source:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    forbidden = [
        "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED = True",
        "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED=true",
        "systemctl stop",
        "systemctl restart",
        "redis-cli FLUSH",
        "flushdb(",
        "flushall(",
        "delete from ",
        "insert into ",
        "update geography_",
        "alter table ",
        "drop table ",
    ]

    lowered = source.lower()
    for token in forbidden:
        if token.lower() in lowered:
            raise AssertionError(
                f"Forbidden mutation or enablement token: {token}"
            )

    print("PASS Audit contains no lookup enablement")
    print("PASS Audit contains no Redis service mutation")
    print("PASS Audit contains no geography database mutation")
    print(
        "NWDP LOCAL REDIS OPERATIONAL AUDIT "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
