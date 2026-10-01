"""Redis-backed distributed rate limiting for guarded endpoints."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Response
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminPrincipal
from app.core.config import settings
from app.modules.farmer.models import Tenant


SUPPORTED_TIERS = (
    "FREE",
    "STANDARD",
    "PRO",
    "ENTERPRISE",
)

# All three budgets are checked before any increment. This guarantees
# partial_consumption_on_rejection is false.
RATE_LIMIT_SCRIPT = """
local actor_current = tonumber(redis.call('GET', KEYS[1]) or '0')
local tenant_current = tonumber(redis.call('GET', KEYS[2]) or '0')
local global_current = tonumber(redis.call('GET', KEYS[3]) or '0')

local actor_limit = tonumber(ARGV[1])
local tenant_limit = tonumber(ARGV[2])
local global_limit = tonumber(ARGV[3])
local ttl_seconds = tonumber(ARGV[4])

if actor_current >= actor_limit then
  return {0, 1, actor_current, tenant_current, global_current}
end
if tenant_current >= tenant_limit then
  return {0, 2, actor_current, tenant_current, global_current}
end
if global_current >= global_limit then
  return {0, 3, actor_current, tenant_current, global_current}
end

local actor_after = redis.call('INCR', KEYS[1])
local tenant_after = redis.call('INCR', KEYS[2])
local global_after = redis.call('INCR', KEYS[3])

if actor_after == 1 then
  redis.call('EXPIRE', KEYS[1], ttl_seconds)
end
if tenant_after == 1 then
  redis.call('EXPIRE', KEYS[2], ttl_seconds)
end
if global_after == 1 then
  redis.call('EXPIRE', KEYS[3], ttl_seconds)
end

return {1, 0, actor_after, tenant_after, global_after}
"""


@dataclass(frozen=True)
class RateLimitPolicy:
    tier: str
    window_seconds: int
    actor_requests: int
    tenant_requests: int
    global_requests: int


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    tier: str
    dimension: str | None
    limit: int
    remaining: int
    reset_seconds: int


_client: Redis | None = None
_client_url: str | None = None


def reset_rate_limit_client() -> None:
    """Reset the cached Redis client, primarily for tests and reloads."""
    global _client, _client_url
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
    _client = None
    _client_url = None


def _redis_client() -> Redis:
    global _client, _client_url

    url = (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL
    )
    if not url:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
                "message":
                    "Distributed rate-limit backend is not configured",
            },
        )

    if _client is None or _client_url != url:
        reset_rate_limit_client()
        _client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            health_check_interval=30,
        )
        _client_url = url

    return _client


def _positive(value: Any, name: str) -> int:
    number = int(value)
    if number <= 0:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_INVALID_CONFIG",
                "message": f"{name} must be greater than zero",
            },
        )
    return number


def resolve_tenant_rate_limit_tier(
    db: Session,
    tenant_id: str,
) -> str:
    """Resolve a server-owned customer tier from persisted tenant config."""
    tenant = (
        db.query(Tenant)
        .filter(
            Tenant.id == tenant_id,
            Tenant.is_active == True,
        )
        .first()
    )
    if tenant is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "NWDP_RUNTIME_LOOKUP_TENANT_NOT_FOUND",
                "message":
                    "Authenticated tenant is unavailable or inactive",
            },
        )

    config = tenant.config if isinstance(tenant.config, dict) else {}
    tier = str(
        config.get("nwdp_runtime_lookup_tier") or "FREE"
    ).strip().upper()

    if tier not in SUPPORTED_TIERS:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_INVALID_TIER",
                "message":
                    "Tenant lookup tier is not supported",
            },
        )

    return tier


def policy_for_tier(tier: str) -> RateLimitPolicy:
    values = {
        "FREE": (
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_FREE_ACTOR_REQUESTS,
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_FREE_TENANT_REQUESTS,
        ),
        "STANDARD": (
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_STANDARD_ACTOR_REQUESTS,
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_STANDARD_TENANT_REQUESTS,
        ),
        "PRO": (
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_PRO_ACTOR_REQUESTS,
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_PRO_TENANT_REQUESTS,
        ),
        "ENTERPRISE": (
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_ENTERPRISE_ACTOR_REQUESTS,
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_ENTERPRISE_TENANT_REQUESTS,
        ),
    }

    if tier not in values:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_INVALID_TIER",
                "message":
                    "Tenant lookup tier is not supported",
            },
        )

    actor_requests, tenant_requests = values[tier]

    return RateLimitPolicy(
        tier=tier,
        window_seconds=_positive(
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_WINDOW_SECONDS,
            "rate-limit window",
        ),
        actor_requests=_positive(
            actor_requests,
            f"{tier} actor limit",
        ),
        tenant_requests=_positive(
            tenant_requests,
            f"{tier} tenant limit",
        ),
        global_requests=_positive(
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_GLOBAL_REQUESTS,
            "global limit",
        ),
    )


def _keys(
    policy: RateLimitPolicy,
    principal: AdminPrincipal,
    now_seconds: int,
) -> tuple[list[str], int]:
    window = now_seconds // policy.window_seconds
    reset_seconds = (
        policy.window_seconds
        - (now_seconds % policy.window_seconds)
    )
    namespace = (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE
        .strip()
    )
    if not namespace:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_INVALID_CONFIG",
                "message":
                    "Rate-limit namespace cannot be empty",
            },
        )

    return [
        (
            f"{namespace}:{window}:"
            f"actor:{principal.user_id}"
        ),
        (
            f"{namespace}:{window}:"
            f"tenant:{principal.tenant_id}"
        ),
        f"{namespace}:{window}:global",
    ], reset_seconds


def evaluate_rate_limit(
    client: Redis,
    policy: RateLimitPolicy,
    principal: AdminPrincipal,
    *,
    now_seconds: int | None = None,
) -> RateLimitDecision:
    """Atomically consume actor, tenant and global budgets."""
    current_time = (
        int(time.time())
        if now_seconds is None
        else int(now_seconds)
    )
    keys, reset_seconds = _keys(
        policy,
        principal,
        current_time,
    )

    try:
        raw = client.eval(
            RATE_LIMIT_SCRIPT,
            len(keys),
            *keys,
            policy.actor_requests,
            policy.tenant_requests,
            policy.global_requests,
            policy.window_seconds + 1,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
                "message":
                    "Distributed rate-limit backend is unavailable",
            },
        ) from exc

    if not isinstance(raw, (list, tuple)) or len(raw) != 5:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_INVALID_RESPONSE",
                "message":
                    "Distributed rate-limit backend returned "
                    "an invalid response",
            },
        )

    allowed = int(raw[0]) == 1
    dimension_index = int(raw[1])
    counts = {
        "actor": int(raw[2]),
        "tenant": int(raw[3]),
        "global": int(raw[4]),
    }
    dimensions = {
        0: None,
        1: "actor",
        2: "tenant",
        3: "global",
    }
    limits = {
        "actor": policy.actor_requests,
        "tenant": policy.tenant_requests,
        "global": policy.global_requests,
    }
    dimension = dimensions.get(dimension_index)

    if dimension_index not in dimensions:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_INVALID_RESPONSE",
                "message":
                    "Distributed rate-limit backend returned "
                    "an invalid rejection dimension",
            },
        )

    if allowed:
        limit = policy.actor_requests
        remaining = max(
            policy.actor_requests - counts["actor"],
            0,
        )
    else:
        limit = limits[dimension]
        remaining = max(
            limit - counts[dimension],
            0,
        )

    return RateLimitDecision(
        allowed=allowed,
        tier=policy.tier,
        dimension=dimension,
        limit=limit,
        remaining=remaining,
        reset_seconds=reset_seconds,
    )


def enforce_nwdp_runtime_lookup_rate_limit(
    principal: AdminPrincipal,
    db: Session,
    response: Response,
) -> RateLimitDecision | None:
    """Apply a shared customer-tier limit or fail closed."""
    if not (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED
    ):
        return None

    tier = resolve_tenant_rate_limit_tier(
        db,
        principal.tenant_id,
    )
    policy = policy_for_tier(tier)
    decision = evaluate_rate_limit(
        _redis_client(),
        policy,
        principal,
    )

    response.headers["RateLimit-Limit"] = str(
        decision.limit
    )
    response.headers["RateLimit-Remaining"] = str(
        decision.remaining
    )
    response.headers["RateLimit-Reset"] = str(
        decision.reset_seconds
    )
    response.headers["X-RateLimit-Tier"] = decision.tier

    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code":
                    "NWDP_RUNTIME_LOOKUP_RATE_LIMITED",
                "message":
                    "Runtime geography lookup quota exceeded",
                "dimension": decision.dimension,
                "tier": decision.tier,
            },
            headers={
                "Retry-After": str(
                    decision.reset_seconds
                ),
                "RateLimit-Limit": str(
                    decision.limit
                ),
                "RateLimit-Remaining": "0",
                "RateLimit-Reset": str(
                    decision.reset_seconds
                ),
                "X-RateLimit-Tier": decision.tier,
            },
        )

    return decision
