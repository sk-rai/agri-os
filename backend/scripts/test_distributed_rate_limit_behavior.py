#!/usr/bin/env python3
"""Behavioral regression for the Redis-backed customer-tier limiter."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException, Response
from redis.exceptions import ConnectionError as RedisConnectionError


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.admin_auth import AdminPrincipal
from app.core.config import settings
import app.core.distributed_rate_limit as limiter


class FakeRedis:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def eval(self, *args):
        self.calls.append(args)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeQuery:
    def __init__(self, tenant):
        self.tenant = tenant
        self.filters = []

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def first(self):
        return self.tenant


class FakeDb:
    def __init__(self, tenant):
        self.tenant = tenant

    def query(self, model):
        return FakeQuery(self.tenant)


def check(condition, label, evidence=None):
    if not condition:
        raise AssertionError(
            f"{label}: {evidence!r}"
        )
    print(f"PASS {label}")


def expect_http(status_code, code, callback, label):
    try:
        callback()
    except HTTPException as exc:
        check(
            exc.status_code == status_code,
            f"{label} status",
            exc.status_code,
        )
        detail = exc.detail
        check(
            isinstance(detail, dict)
            and detail.get("code") == code,
            f"{label} code",
            detail,
        )
        return exc
    raise AssertionError(f"{label}: HTTPException not raised")


def main():
    original = {
        name: getattr(settings, name)
        for name in (
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED",
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL",
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE",
        )
    }

    principal = AdminPrincipal(
        user_id=uuid.UUID(
            "11111111-1111-4111-8111-111111111111"
        ),
        tenant_id="paid-tenant",
        role="ENTERPRISE_ADMIN",
    )

    try:
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
            "test:nwdp"
        )

        free = limiter.policy_for_tier("FREE")
        standard = limiter.policy_for_tier("STANDARD")
        pro = limiter.policy_for_tier("PRO")
        enterprise = limiter.policy_for_tier("ENTERPRISE")

        check(
            free.actor_requests
            < standard.actor_requests
            < pro.actor_requests
            < enterprise.actor_requests,
            "Actor quotas increase by customer tier",
        )
        check(
            free.tenant_requests
            < standard.tenant_requests
            < pro.tenant_requests
            < enterprise.tenant_requests,
            "Tenant quotas increase by customer tier",
        )

        for tier in limiter.SUPPORTED_TIERS:
            tenant = SimpleNamespace(
                config={
                    "nwdp_runtime_lookup_tier": tier
                }
            )
            resolved = (
                limiter.resolve_tenant_rate_limit_tier(
                    FakeDb(tenant),
                    "paid-tenant",
                )
            )
            check(
                resolved == tier,
                f"{tier} persisted tier resolves",
                resolved,
            )

        default_tier = (
            limiter.resolve_tenant_rate_limit_tier(
                FakeDb(SimpleNamespace(config={})),
                "paid-tenant",
            )
        )
        check(
            default_tier == "FREE",
            "Missing tier defaults to FREE",
            default_tier,
        )

        expect_http(
            503,
            "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_INVALID_TIER",
            lambda: (
                limiter.resolve_tenant_rate_limit_tier(
                    FakeDb(SimpleNamespace(
                        config={
                            "nwdp_runtime_lookup_tier":
                                "UNLIMITED"
                        }
                    )),
                    "paid-tenant",
                )
            ),
            "Unsupported persisted tier fails closed",
        )

        expect_http(
            403,
            "NWDP_RUNTIME_LOOKUP_TENANT_NOT_FOUND",
            lambda: (
                limiter.resolve_tenant_rate_limit_tier(
                    FakeDb(None),
                    "missing-tenant",
                )
            ),
            "Missing tenant fails closed",
        )

        allowed_client = FakeRedis([1, 0, 1, 1, 1])
        allowed = limiter.evaluate_rate_limit(
            allowed_client,
            standard,
            principal,
            now_seconds=120,
        )
        check(allowed.allowed, "Allowed decision passes")
        check(
            allowed.dimension is None,
            "Allowed decision has no rejection dimension",
            allowed,
        )
        check(
            allowed.remaining
            == standard.actor_requests - 1,
            "Allowed decision reports actor remainder",
            allowed,
        )

        call = allowed_client.calls[0]
        keys = call[2:5]
        check(
            any(
                str(principal.user_id) in str(key)
                for key in keys
            ),
            "Actor identity is present in Redis key",
            keys,
        )
        check(
            any(
                principal.tenant_id in str(key)
                for key in keys
            ),
            "Tenant identity is present in Redis key",
            keys,
        )
        check(
            not any(
                value in str(keys)
                for value in (
                    "latitude",
                    "longitude",
                    "Bearer",
                )
            ),
            "Sensitive request material is absent from keys",
            keys,
        )

        actor_rejection = limiter.evaluate_rate_limit(
            FakeRedis([
                0,
                1,
                standard.actor_requests,
                1,
                1,
            ]),
            standard,
            principal,
            now_seconds=121,
        )
        check(
            not actor_rejection.allowed
            and actor_rejection.dimension == "actor",
            "Actor exhaustion is distinguished",
            actor_rejection,
        )

        tenant_rejection = limiter.evaluate_rate_limit(
            FakeRedis([
                0,
                2,
                1,
                standard.tenant_requests,
                1,
            ]),
            standard,
            principal,
            now_seconds=121,
        )
        check(
            not tenant_rejection.allowed
            and tenant_rejection.dimension == "tenant",
            "Tenant exhaustion is distinguished",
            tenant_rejection,
        )

        global_rejection = limiter.evaluate_rate_limit(
            FakeRedis([
                0,
                3,
                1,
                1,
                standard.global_requests,
            ]),
            standard,
            principal,
            now_seconds=121,
        )
        check(
            not global_rejection.allowed
            and global_rejection.dimension == "global",
            "Global exhaustion is distinguished",
            global_rejection,
        )

        expect_http(
            503,
            "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
            lambda: limiter.evaluate_rate_limit(
                FakeRedis(
                    RedisConnectionError("unavailable")
                ),
                standard,
                principal,
                now_seconds=121,
            ),
            "Redis failure fails closed",
        )

        expect_http(
            503,
            "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_INVALID_RESPONSE",
            lambda: limiter.evaluate_rate_limit(
                FakeRedis(["bad"]),
                standard,
                principal,
                now_seconds=121,
            ),
            "Malformed Redis response fails closed",
        )

        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED = (
            False
        )
        disabled_response = Response()
        disabled = (
            limiter.enforce_nwdp_runtime_lookup_rate_limit(
                principal,
                FakeDb(None),
                disabled_response,
            )
        )
        check(
            disabled is None,
            "Disabled limiter performs no tenant or Redis work",
            disabled,
        )
        check(
            not disabled_response.headers.get(
                "X-RateLimit-Tier"
            ),
            "Disabled limiter emits no tier header",
        )

        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED = (
            True
        )
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL = (
            "redis://test.invalid:6379/0"
        )

        original_client = limiter._redis_client
        try:
            limiter._redis_client = lambda: FakeRedis(
                [1, 0, 1, 1, 1]
            )
            response = Response()
            decision = (
                limiter.enforce_nwdp_runtime_lookup_rate_limit(
                    principal,
                    FakeDb(SimpleNamespace(
                        config={
                            "nwdp_runtime_lookup_tier":
                                "PRO"
                        }
                    )),
                    response,
                )
            )
            check(
                decision is not None
                and decision.allowed
                and decision.tier == "PRO",
                "Enabled limiter applies persisted PRO tier",
                decision,
            )
            check(
                response.headers["X-RateLimit-Tier"]
                == "PRO",
                "Allowed response exposes resolved tier",
                dict(response.headers),
            )
            check(
                response.headers["RateLimit-Limit"]
                == str(pro.actor_requests),
                "Allowed response exposes actor limit",
                dict(response.headers),
            )

            limiter._redis_client = lambda: FakeRedis([
                0,
                1,
                pro.actor_requests,
                1,
                1,
            ])
            rejected = expect_http(
                429,
                "NWDP_RUNTIME_LOOKUP_RATE_LIMITED",
                lambda: (
                    limiter.enforce_nwdp_runtime_lookup_rate_limit(
                        principal,
                        FakeDb(SimpleNamespace(
                            config={
                                "nwdp_runtime_lookup_tier":
                                    "PRO"
                            }
                        )),
                        Response(),
                    )
                ),
                "Exhausted enabled limiter returns 429",
            )
            check(
                rejected.headers.get("Retry-After"),
                "Rejected response includes Retry-After",
                rejected.headers,
            )
            check(
                rejected.detail.get("dimension") == "actor",
                "Rejected response identifies dimension",
                rejected.detail,
            )
            check(
                rejected.detail.get("tier") == "PRO",
                "Rejected response identifies server tier",
                rejected.detail,
            )
        finally:
            limiter._redis_client = original_client

        print(
            "DISTRIBUTED CUSTOMER-TIER RATE LIMIT "
            "BEHAVIOR REGRESSION PASSED"
        )
        return 0
    finally:
        for name, value in original.items():
            setattr(settings, name, value)
        limiter.reset_rate_limit_client()


if __name__ == "__main__":
    raise SystemExit(main())
