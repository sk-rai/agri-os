#!/usr/bin/env python3
"""Behavior regression for distributed limiter observability."""

from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException, Response


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import distributed_rate_limit as limiter  # noqa: E402
from app.core.config import settings  # noqa: E402


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main() -> int:
    original_enabled = (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED
    )
    original_resolver = limiter.resolve_tenant_rate_limit_tier
    original_policy = limiter.policy_for_tier
    original_client = limiter._redis_client
    original_evaluate = limiter.evaluate_rate_limit

    principal = SimpleNamespace(
        user_id="actor-secret-do-not-log",
        tenant_id="tenant-secret-do-not-log",
    )
    policy = limiter.RateLimitPolicy(
        tier="PRO",
        window_seconds=60,
        actor_requests=120,
        tenant_requests=600,
        global_requests=600,
    )

    log_buffer = io.StringIO()
    handler = logging.StreamHandler(log_buffer)
    limiter.logger.addHandler(handler)
    limiter.logger.setLevel(logging.INFO)

    try:
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED = True
        limiter.reset_rate_limit_observability()
        limiter.resolve_tenant_rate_limit_tier = (
            lambda db, tenant_id: "PRO"
        )
        limiter.policy_for_tier = lambda tier: policy
        limiter._redis_client = lambda: object()

        limiter.evaluate_rate_limit = (
            lambda client, selected_policy, selected_principal:
            limiter.RateLimitDecision(
                allowed=True,
                tier="PRO",
                dimension=None,
                limit=120,
                remaining=119,
                reset_seconds=60,
            )
        )
        allowed = limiter.enforce_nwdp_runtime_lookup_rate_limit(
            principal,
            object(),
            Response(),
        )
        check(allowed is not None and allowed.allowed, "Allowed decision passes")

        limiter.evaluate_rate_limit = (
            lambda client, selected_policy, selected_principal:
            limiter.RateLimitDecision(
                allowed=False,
                tier="PRO",
                dimension="tenant",
                limit=600,
                remaining=0,
                reset_seconds=45,
            )
        )
        try:
            limiter.enforce_nwdp_runtime_lookup_rate_limit(
                principal,
                object(),
                Response(),
            )
            raise AssertionError("Rejected decision did not raise")
        except HTTPException as exc:
            check(exc.status_code == 429, "Rejected decision returns 429")

        def unavailable(*args, **kwargs):
            raise HTTPException(
                status_code=503,
                detail={
                    "code":
                        "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
                    "message": "unavailable",
                },
            )

        limiter.evaluate_rate_limit = unavailable
        try:
            limiter.enforce_nwdp_runtime_lookup_rate_limit(
                principal,
                object(),
                Response(),
            )
            raise AssertionError("Backend failure did not raise")
        except HTTPException as exc:
            check(exc.status_code == 503, "Backend failure remains fail closed")

        snapshot = limiter.rate_limit_observability_snapshot()
        serialized = json.dumps(snapshot, sort_keys=True)
        logs = log_buffer.getvalue()

        counters = {
            (
                row["outcome"],
                row["tier"],
                row["dimension"],
                row["error_code"],
            ): row["count"]
            for row in snapshot["decision_counters"]
        }

        check(
            counters[("allowed", "PRO", "none", "none")] == 1,
            "Allowed counter is exact",
        )
        check(
            counters[("rejected", "PRO", "tenant", "none")] == 1,
            "Tenant rejection counter is exact",
        )
        check(
            counters[
                (
                    "error",
                    "PRO",
                    "none",
                    "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
                )
            ] == 1,
            "Redis failure counter is exact",
        )
        check(
            snapshot["latency_ms"]["count"] == 3,
            "Every limiter evaluation records latency",
        )
        check(
            snapshot["remaining_budget"]["count"] == 2,
            "Decisions record remaining budget",
        )
        check(
            snapshot["remaining_budget"]["min"] == 0,
            "Remaining-budget minimum is exact",
        )
        check(
            snapshot["remaining_budget"]["max"] == 119,
            "Remaining-budget maximum is exact",
        )
        check(
            snapshot["scope"] == "PROCESS_LOCAL",
            "Process-local metric scope is explicit",
        )
        check(
            "Aggregate structured logs" in
            snapshot["aggregation_guidance"],
            "Cross-worker aggregation guidance is explicit",
        )

        forbidden_values = [
            principal.user_id,
            principal.tenant_id,
            "28.6139",
            "77.2090",
            "Bearer",
            "redis://",
            "actor:",
            "tenant:",
        ]
        for value in forbidden_values:
            check(
                value not in serialized and value not in logs,
                f"Sensitive value is excluded: {value}",
            )

        check(
            logs.count("nwdp_runtime_lookup_rate_limit ") == 3,
            "Each evaluation emits one structured log event",
        )
        check(
            "outcome=allowed tier=PRO" in logs,
            "Allowed log is structured",
        )
        check(
            "outcome=rejected tier=PRO dimension=tenant" in logs,
            "Rejected log is structured",
        )
        check(
            "error_code=NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE"
            in logs,
            "Failure log exposes stable error code",
        )

        limiter.reset_rate_limit_observability()
        empty = limiter.rate_limit_observability_snapshot()
        check(
            empty["latency_ms"]["count"] == 0,
            "Observability reset is deterministic",
        )
    finally:
        limiter.logger.removeHandler(handler)
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED = (
            original_enabled
        )
        limiter.resolve_tenant_rate_limit_tier = original_resolver
        limiter.policy_for_tier = original_policy
        limiter._redis_client = original_client
        limiter.evaluate_rate_limit = original_evaluate
        limiter.reset_rate_limit_observability()

    print(
        "DISTRIBUTED RATE LIMIT OBSERVABILITY "
        "BEHAVIOR REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
