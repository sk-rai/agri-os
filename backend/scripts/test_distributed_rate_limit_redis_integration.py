#!/usr/bin/env python3
"""Real-Redis concurrency regression for customer-tier lookup limits."""

from __future__ import annotations

import argparse
import multiprocessing
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from redis import Redis


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.admin_auth import AdminPrincipal
from app.core.config import settings
from app.core.distributed_rate_limit import (
    RateLimitPolicy,
    evaluate_rate_limit,
)


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redis-url",
        default="redis://127.0.0.1:6379/0",
    )
    return parser.parse_args()


def check(condition, label, evidence=None):
    if not condition:
        raise AssertionError(
            f"{label}: {evidence!r}"
        )
    print(f"PASS {label}")


def delete_namespace(client, namespace):
    keys = list(client.scan_iter(
        match=f"{namespace}:*",
        count=1000,
    ))
    if keys:
        client.delete(*keys)
    return len(keys)


def attempt(client, policy, principal, now_seconds):
    decision = evaluate_rate_limit(
        client,
        policy,
        principal,
        now_seconds=now_seconds,
    )
    return {
        "allowed": decision.allowed,
        "dimension": decision.dimension,
        "tier": decision.tier,
        "remaining": decision.remaining,
    }


def process_worker(
    redis_url,
    namespace,
    actor_id,
    tenant_id,
    actor_limit,
    request_count,
    now_seconds,
    output,
):
    from redis import Redis

    from app.core.admin_auth import AdminPrincipal
    from app.core.config import settings
    from app.core.distributed_rate_limit import (
        RateLimitPolicy,
        evaluate_rate_limit,
    )

    settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
        namespace
    )

    client = Redis.from_url(
        redis_url,
        decode_responses=True,
    )
    principal = AdminPrincipal(
        user_id=uuid.UUID(actor_id),
        tenant_id=tenant_id,
        role="ADMIN_VIEWER",
    )
    policy = RateLimitPolicy(
        tier="STANDARD",
        window_seconds=60,
        actor_requests=actor_limit,
        tenant_requests=10_000,
        global_requests=10_000,
    )

    allowed = 0
    rejected = 0
    dimensions = []

    for _ in range(request_count):
        decision = evaluate_rate_limit(
            client,
            policy,
            principal,
            now_seconds=now_seconds,
        )
        if decision.allowed:
            allowed += 1
        else:
            rejected += 1
            dimensions.append(decision.dimension)

    client.close()
    output.put({
        "allowed": allowed,
        "rejected": rejected,
        "dimensions": dimensions,
    })


def main():
    options = arguments()
    client = Redis.from_url(
        options.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=2,
    )

    original_namespace = (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE
    )
    base_namespace = (
        "agrios:test:nwdp-rate-limit:"
        + uuid.uuid4().hex
    )

    try:
        check(
            client.ping() is True,
            "Real Redis server responds",
        )
        check(
            "redis_version" in client.info("server"),
            "Redis server metadata is available",
        )

        # Threaded atomicity test.
        thread_namespace = base_namespace + ":threads"
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
            thread_namespace
        )
        thread_principal = AdminPrincipal(
            user_id=uuid.UUID(
                "11111111-1111-4111-8111-111111111111"
            ),
            tenant_id="thread-tenant",
            role="ADMIN_VIEWER",
        )
        thread_policy = RateLimitPolicy(
            tier="STANDARD",
            window_seconds=60,
            actor_requests=17,
            tenant_requests=1000,
            global_requests=1000,
        )
        fixed_time = 1_800_000_000

        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(
                lambda _: attempt(
                    client,
                    thread_policy,
                    thread_principal,
                    fixed_time,
                ),
                range(80),
            ))

        allowed = sum(row["allowed"] for row in results)
        rejected = len(results) - allowed
        check(
            allowed == 17,
            "Threaded actor budget is exact",
            {"allowed": allowed, "rejected": rejected},
        )
        check(
            rejected == 63,
            "Threaded excess requests are rejected",
            rejected,
        )
        check(
            all(
                row["dimension"] == "actor"
                for row in results
                if not row["allowed"]
            ),
            "Threaded rejection dimension is actor",
        )

        # Separate-process shared-budget test.
        process_namespace = base_namespace + ":processes"
        actor_id = "22222222-2222-4222-8222-222222222222"
        actor_limit = 23
        process_count = 4
        requests_per_process = 20

        context = multiprocessing.get_context("spawn")
        output = context.Queue()
        processes = [
            context.Process(
                target=process_worker,
                args=(
                    options.redis_url,
                    process_namespace,
                    actor_id,
                    "process-tenant",
                    actor_limit,
                    requests_per_process,
                    fixed_time + 60,
                    output,
                ),
            )
            for _ in range(process_count)
        ]

        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
            check(
                process.exitcode == 0,
                "Worker process exits cleanly",
                process.exitcode,
            )

        process_results = [
            output.get(timeout=5)
            for _ in processes
        ]
        process_allowed = sum(
            row["allowed"]
            for row in process_results
        )
        process_rejected = sum(
            row["rejected"]
            for row in process_results
        )

        check(
            process_allowed == actor_limit,
            "Multi-process shared actor budget is exact",
            process_results,
        )
        check(
            process_rejected
            == (
                process_count * requests_per_process
                - actor_limit
            ),
            "Multi-process excess requests are rejected",
            process_results,
        )
        check(
            all(
                dimension == "actor"
                for row in process_results
                for dimension in row["dimensions"]
            ),
            "Multi-process rejection dimension is actor",
            process_results,
        )

        # Tenant dimension across distinct actors.
        tenant_namespace = base_namespace + ":tenant"
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
            tenant_namespace
        )
        tenant_policy = RateLimitPolicy(
            tier="PRO",
            window_seconds=60,
            actor_requests=100,
            tenant_requests=11,
            global_requests=1000,
        )
        tenant_results = []
        for position in range(30):
            principal = AdminPrincipal(
                user_id=uuid.UUID(
                    f"33333333-3333-4333-8333-"
                    f"{position + 1:012d}"
                ),
                tenant_id="shared-paying-tenant",
                role="ADMIN_VIEWER",
            )
            tenant_results.append(
                attempt(
                    client,
                    tenant_policy,
                    principal,
                    fixed_time + 120,
                )
            )

        tenant_allowed = sum(
            row["allowed"]
            for row in tenant_results
        )
        check(
            tenant_allowed == 11,
            "Tenant budget is shared across actors",
            tenant_results,
        )
        check(
            all(
                row["dimension"] == "tenant"
                for row in tenant_results
                if not row["allowed"]
            ),
            "Tenant exhaustion is distinguished",
            tenant_results,
        )

        # Global dimension across tenants.
        global_namespace = base_namespace + ":global"
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
            global_namespace
        )
        global_policy = RateLimitPolicy(
            tier="ENTERPRISE",
            window_seconds=60,
            actor_requests=100,
            tenant_requests=100,
            global_requests=9,
        )
        global_results = []
        for position in range(20):
            principal = AdminPrincipal(
                user_id=uuid.UUID(
                    f"44444444-4444-4444-8444-"
                    f"{position + 1:012d}"
                ),
                tenant_id=f"tenant-{position + 1}",
                role="ADMIN_VIEWER",
            )
            global_results.append(
                attempt(
                    client,
                    global_policy,
                    principal,
                    fixed_time + 180,
                )
            )

        check(
            sum(row["allowed"] for row in global_results)
            == 9,
            "Global budget is exact across tenants",
            global_results,
        )
        check(
            all(
                row["dimension"] == "global"
                for row in global_results
                if not row["allowed"]
            ),
            "Global exhaustion is distinguished",
            global_results,
        )

        # Tier quota differentiation.
        tier_namespace = base_namespace + ":tiers"
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
            tier_namespace
        )
        tier_limits = {
            "FREE": 2,
            "STANDARD": 4,
            "PRO": 6,
            "ENTERPRISE": 8,
        }
        tier_allowed = {}

        for index, (tier, limit) in enumerate(
            tier_limits.items(),
            start=1,
        ):
            principal = AdminPrincipal(
                user_id=uuid.UUID(
                    f"55555555-5555-4555-8555-"
                    f"{index:012d}"
                ),
                tenant_id=f"{tier.lower()}-tenant",
                role="ADMIN_VIEWER",
            )
            policy = RateLimitPolicy(
                tier=tier,
                window_seconds=60,
                actor_requests=limit,
                tenant_requests=100,
                global_requests=1000,
            )
            decisions = [
                attempt(
                    client,
                    policy,
                    principal,
                    fixed_time + 240,
                )
                for _ in range(10)
            ]
            tier_allowed[tier] = sum(
                row["allowed"]
                for row in decisions
            )

        check(
            tier_allowed == tier_limits,
            "Paying tiers receive distinct exact quotas",
            tier_allowed,
        )

        # TTL and window reset against real wall time.
        ttl_namespace = base_namespace + ":ttl"
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
            ttl_namespace
        )
        ttl_principal = AdminPrincipal(
            user_id=uuid.UUID(
                "66666666-6666-4666-8666-666666666666"
            ),
            tenant_id="ttl-tenant",
            role="ADMIN_VIEWER",
        )
        ttl_policy = RateLimitPolicy(
            tier="FREE",
            window_seconds=2,
            actor_requests=1,
            tenant_requests=10,
            global_requests=10,
        )

        first = evaluate_rate_limit(
            client,
            ttl_policy,
            ttl_principal,
        )
        second = evaluate_rate_limit(
            client,
            ttl_policy,
            ttl_principal,
        )
        check(
            first.allowed and not second.allowed,
            "Real Redis enforces current window",
            {
                "first": first,
                "second": second,
            },
        )

        ttl_keys = list(client.scan_iter(
            match=f"{ttl_namespace}:*",
        ))
        check(
            len(ttl_keys) == 3,
            "Actor tenant and global keys exist",
            ttl_keys,
        )
        ttl_values = [
            client.ttl(key)
            for key in ttl_keys
        ]
        check(
            all(0 < value <= 3 for value in ttl_values),
            "All budget keys have bounded TTL",
            ttl_values,
        )

        time.sleep(3)

        after_expiry = evaluate_rate_limit(
            client,
            ttl_policy,
            ttl_principal,
        )
        check(
            after_expiry.allowed,
            "Budget resets after window expiry",
            after_expiry,
        )

        # Namespace isolation.
        isolated_namespace = (
            base_namespace + ":isolated-project"
        )
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
            isolated_namespace
        )
        isolated = evaluate_rate_limit(
            client,
            RateLimitPolicy(
                tier="FREE",
                window_seconds=60,
                actor_requests=1,
                tenant_requests=1,
                global_requests=1,
            ),
            ttl_principal,
            now_seconds=fixed_time + 300,
        )
        check(
            isolated.allowed,
            "Separate project namespace is isolated",
            isolated,
        )

        print({
            "redis_url": options.redis_url,
            "thread_allowed": allowed,
            "thread_rejected": rejected,
            "process_allowed": process_allowed,
            "process_rejected": process_rejected,
            "tenant_allowed": tenant_allowed,
            "global_allowed": sum(
                row["allowed"]
                for row in global_results
            ),
            "tier_allowed": tier_allowed,
            "ttl_values": ttl_values,
        })
        print(
            "DISTRIBUTED RATE LIMIT REAL REDIS "
            "INTEGRATION PASSED"
        )
        return 0
    finally:
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
            original_namespace
        )
        removed = delete_namespace(
            client,
            base_namespace,
        )
        print(f"cleaned Redis test keys: {removed}")
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
