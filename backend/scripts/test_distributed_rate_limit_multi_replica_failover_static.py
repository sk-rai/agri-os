#!/usr/bin/env python3
"""Static contract for the multi-replica Redis failover gate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GATE = (
    ROOT / "backend" / "scripts"
    / "test_distributed_rate_limit_multi_replica_failover.py"
)


def main() -> int:
    source = GATE.read_text(encoding="utf-8")

    contracts = [
        (
            "nwdp_runtime_lookup_multi_replica_failover_gate.v1",
            "Gate schema is versioned",
        ),
        (
            "WORKER_COUNT = 4",
            "Four independent replicas are required",
        ),
        (
            'get_context("spawn")',
            "Workers use independent spawned processes",
        ),
        (
            "SHARED_LIMIT = 40",
            "Shared budget is pinned",
        ),
        (
            "allowed == SHARED_LIMIT",
            "Exact shared allowance is required",
        ),
        (
            "Temporary Redis uses a non-system port",
            "Temporary Redis is isolated from system Redis",
        ),
        (
            '"127.0.0.1"',
            "Temporary Redis is loopback-only",
        ),
        (
            '"--protected-mode"',
            "Temporary Redis uses protected mode",
        ),
        (
            '"--appendonly"',
            "Temporary Redis persistence posture is explicit",
        ),
        (
            "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
            "Stable fail-closed error is required",
        ),
        (
            "failure_status == 503",
            "Redis outage must fail closed",
        ),
        (
            "Limiter recovers after Redis restart",
            "Recovery is required",
        ),
        (
            "Temporary limiter keys are cleaned",
            "Test keys must be cleaned",
        ),
        (
            "Shared system Redis remains healthy",
            "System Redis health is preserved",
        ),
        (
            "Runtime lookup remains disabled",
            "Lookup remains disabled",
        ),
        (
            '"lookup_enablement_authorized": False',
            "Lookup enablement remains unauthorized",
        ),
        (
            '"shared_redis_stopped": False',
            "Shared Redis cannot be stopped",
        ),
        (
            '"shared_redis_flushed": False',
            "Shared Redis cannot be flushed",
        ),
        (
            '"database_writes_attempted": False',
            "Database remains unchanged",
        ),
        (
            "production persistence and failover policy",
            "Production persistence remains separately gated",
        ),
    ]

    for needle, label in contracts:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    forbidden = [
        "FLUSHALL",
        "FLUSHDB",
        "systemctl stop redis",
        "systemctl restart redis",
        "service redis stop",
        "service redis restart",
        "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED = True",
    ]
    for token in forbidden:
        if token in source:
            raise AssertionError(
                f"Forbidden shared-service action: {token}"
            )

    print("PASS Gate contains no shared Redis destructive action")
    print("PASS Gate contains no lookup enablement")
    print(
        "DISTRIBUTED RATE LIMIT MULTI-REPLICA "
        "FAILOVER STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
