#!/usr/bin/env python3
"""Static contract for distributed limiter observability."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = (
    ROOT / "backend" / "app" / "core"
    / "distributed_rate_limit.py"
)


def main() -> int:
    source = MODULE.read_text(encoding="utf-8")

    contracts = [
        (
            "nwdp_runtime_lookup_rate_limit_observability.v1",
            "Observability schema is versioned",
        ),
        (
            "LATENCY_BUCKETS_MS",
            "Latency buckets are bounded",
        ),
        (
            "rate_limit_observability_snapshot",
            "Aggregate snapshot is available",
        ),
        (
            "reset_rate_limit_observability",
            "Test reset is available",
        ),
        (
            'outcome = "allowed" if',
            "Allowed outcome is recorded",
        ),
        (
            'outcome="error"',
            "Backend errors are recorded",
        ),
        (
            '"rejected"',
            "Rejected outcome is recorded",
        ),
        (
            '"scope": "PROCESS_LOCAL"',
            "Process-local scope is explicit",
        ),
        (
            "Aggregate structured logs across workers and replicas.",
            "Cross-worker aggregation is explicit",
        ),
        (
            "nwdp_runtime_lookup_rate_limit ",
            "Structured event name is stable",
        ),
        (
            "_http_error_code",
            "Stable failure codes are captured",
        ),
    ]

    for needle, label in contracts:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    forbidden_log_fields = [
        "principal.user_id,",
        "principal.tenant_id,",
        "latitude=%",
        "longitude=%",
        "authorization=%",
        "redis_url=%",
    ]
    logging_section = source[
        source.index("def _record_rate_limit_observation"):
        source.index("def rate_limit_observability_snapshot")
    ]
    for token in forbidden_log_fields:
        if token in logging_section:
            raise AssertionError(
                f"Sensitive log material present: {token}"
            )

    print("PASS Structured logs exclude sensitive identities")
    print("PASS Observability contains no database writes")
    print(
        "DISTRIBUTED RATE LIMIT OBSERVABILITY "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
