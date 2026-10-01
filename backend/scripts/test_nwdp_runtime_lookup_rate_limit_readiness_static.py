#!/usr/bin/env python3
"""Static contract for the NWDP lookup rate-limit readiness audit."""

from pathlib import Path


SCRIPT = Path(__file__).with_name(
    "audit_nwdp_runtime_lookup_rate_limit_readiness.py"
)


def main():
    source = SCRIPT.read_text(encoding="utf-8")

    contracts = [
        (
            "EXPECTED_ACTIVE_RUNTIME_ROWS = 467_397",
            "Current active runtime total is pinned",
        ),
        (
            "shared_limiter_implemented",
            "Shared limiter implementation is inventoried",
        ),
        (
            "redis_client_dependency_installed",
            "Redis dependency is inventoried",
        ),
        (
            "redis_connection_configured",
            "Redis configuration is inventoried",
        ),
        (
            "lookup_feature_flag_default_off",
            "Lookup feature flag is inspected",
        ),
        (
            "lookup_requires_admin_view",
            "Admin authorization is inspected",
        ),
        (
            "lookup_requires_runtime_set_id",
            "Runtime-set scope is inspected",
        ),
        (
            "lookup_uses_gist_prefilter",
            "GiST prefilter is inspected",
        ),
        (
            "lookup_ambiguity_probe_bounded",
            "Ambiguity bound is inspected",
        ),
        (
            "REDIS_BACKED_AUTHENTICATED_ENDPOINT_LIMITER",
            "Distributed limiter decision is explicit",
        ),
        (
            "actor:<actor_uuid>",
            "Actor limit key is explicit",
        ),
        (
            "tenant:<tenant_id_or_shared-admin>",
            "Tenant limit key is explicit",
        ),
        (
            "namespace:window:global",
            "Global limit key is explicit",
        ),
        (
            "single Redis Lua script",
            "Atomic limiter operation is required",
        ),
        (
            "partial_consumption_on_rejection",
            "Partial budget consumption is forbidden",
        ),
        (
            "NWDP_RUNTIME_LOOKUP_RATE_LIMITED",
            "HTTP 429 contract is explicit",
        ),
        (
            "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
            "Fail-closed backend error is explicit",
        ),
        (
            '"fail_closed": True',
            "Fail-closed behavior is required",
        ),
        (
            '"coordinates_in_rate_limit_keys": False',
            "Coordinates are excluded from keys",
        ),
        (
            '"tokens_logged": False',
            "Credential logging is forbidden",
        ),
        (
            "concurrent multi-worker shared-budget regression",
            "Multi-worker validation is required",
        ),
        (
            '"ready_for_lookup_enablement": False',
            "Lookup remains blocked",
        ),
        (
            '"lookup_enablement_authorized": False',
            "Lookup enablement remains unauthorized",
        ),
        (
            '"android_changes_authorized": False',
            "Android changes remain unauthorized",
        ),
        (
            '"database_writes_attempted": False',
            "Read-only behavior is explicit",
        ),
    ]

    for needle, label in contracts:
        if needle not in source:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    lowered = source.lower()
    forbidden = (
        "insert into ",
        "update geography_",
        "delete from ",
        ".commit()",
        "pip install",
    )
    for needle in forbidden:
        if needle in lowered:
            raise AssertionError(
                f"Mutation or dependency change found: {needle!r}"
            )

    print("PASS Audit contains no database mutations")
    print("PASS Audit installs no dependencies")
    print(
        "NWDP RUNTIME LOOKUP RATE-LIMIT READINESS "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
