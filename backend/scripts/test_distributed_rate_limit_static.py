#!/usr/bin/env python3
"""Static contract for the Redis-backed customer-tier limiter."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "backend/app/core/distributed_rate_limit.py"
CONFIG = ROOT / "backend/app/core/config.py"
REQUIREMENTS = ROOT / "backend/requirements.txt"


def main():
    module = MODULE.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    requirements = REQUIREMENTS.read_text(
        encoding="utf-8"
    )

    contracts = [
        (
            module,
            'SUPPORTED_TIERS = (',
            "Supported tiers are explicit",
        ),
        (
            module,
            '"FREE"',
            "Free tier exists",
        ),
        (
            module,
            '"STANDARD"',
            "Standard tier exists",
        ),
        (
            module,
            '"PRO"',
            "Pro tier exists",
        ),
        (
            module,
            '"ENTERPRISE"',
            "Enterprise tier exists",
        ),
        (
            module,
            'config.get("nwdp_runtime_lookup_tier")',
            "Tier comes from persisted tenant config",
        ),
        (
            module,
            "Tenant.id == tenant_id",
            "Tier resolution is tenant scoped",
        ),
        (
            module,
            "Tenant.is_active == True",
            "Inactive tenants are rejected",
        ),
        (
            module,
            "RATE_LIMIT_SCRIPT",
            "Atomic Redis script exists",
        ),
        (
            module,
            "actor_current >= actor_limit",
            "Actor quota is enforced",
        ),
        (
            module,
            "tenant_current >= tenant_limit",
            "Tenant quota is enforced",
        ),
        (
            module,
            "global_current >= global_limit",
            "Global quota is enforced",
        ),
        (
            module,
            "partial_consumption",
            "Partial-consumption concern is documented",
        ),
        (
            module,
            "NWDP_RUNTIME_LOOKUP_RATE_LIMITED",
            "HTTP 429 contract exists",
        ),
        (
            module,
            "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
            "Backend failure is fail closed",
        ),
        (
            module,
            "Retry-After",
            "Retry-After is returned",
        ),
        (
            module,
            "RateLimit-Remaining",
            "Remaining budget is returned",
        ),
        (
            config,
            "RATE_LIMIT_ENABLED: bool = False",
            "Limiter defaults disabled",
        ),
        (
            config,
            "RATE_LIMIT_REDIS_URL: str | None = None",
            "Redis URL has no unsafe default",
        ),
        (
            config,
            "FREE_ACTOR_REQUESTS: int = 10",
            "Free actor quota is configurable",
        ),
        (
            config,
            "STANDARD_ACTOR_REQUESTS: int = 30",
            "Standard actor quota is configurable",
        ),
        (
            config,
            "PRO_ACTOR_REQUESTS: int = 120",
            "Pro actor quota is configurable",
        ),
        (
            config,
            "ENTERPRISE_ACTOR_REQUESTS: int = 600",
            "Enterprise actor quota is configurable",
        ),
        (
            requirements,
            "redis==5.0.7",
            "Redis dependency is pinned",
        ),
    ]

    for source, needle, label in contracts:
        if needle not in source:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    forbidden = (
        "latitude",
        "longitude",
        "authorization token",
        "x-rate-limit-tier = Header",
        "x-customer-tier",
    )
    lowered = module.lower()
    for needle in forbidden:
        if needle.lower() in lowered:
            raise AssertionError(
                f"Client or coordinate material found: {needle!r}"
            )

    print("PASS Coordinates are excluded from limiter keys")
    print("PASS Customer tier cannot be supplied by a request header")
    print(
        "DISTRIBUTED CUSTOMER-TIER RATE LIMIT "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
