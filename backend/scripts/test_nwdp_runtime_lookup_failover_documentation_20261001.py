#!/usr/bin/env python3
"""Documentation contract for the multi-replica failover gate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FILES = {
    "runbook": (
        ROOT / "docs"
        / "nwdp-runtime-point-lookup-pilot-runbook.md"
    ),
    "tracker": (
        ROOT / "docs" / "backend-gap-closure-tracker.md"
    ),
    "roadmap": (
        ROOT / "docs"
        / "geography-layer-readiness-2026-09-04.md"
    ),
}


def main() -> int:
    content = {
        name: path.read_text(encoding="utf-8")
        for name, path in FILES.items()
    }

    contracts = [
        (
            "runbook",
            "## Multi-replica and failover gate — 2026-10-01",
            "Failover milestone is dated",
        ),
        (
            "runbook",
            "Commit `76a9a88`",
            "Failover commit is recorded",
        ),
        (
            "runbook",
            "four independently spawned worker processes",
            "Four-worker scope is documented",
        ),
        (
            "runbook",
            "exactly `40` of `80` requests were allowed",
            "Exact shared-budget outcome is recorded",
        ),
        (
            "runbook",
            "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
            "Stable outage code is documented",
        ),
        (
            "runbook",
            "limiter recovered",
            "Restart recovery is documented",
        ),
        (
            "runbook",
            "shared system Redis service was neither stopped",
            "System Redis isolation is documented",
        ),
        (
            "runbook",
            "lookup remained disabled",
            "Lookup remained disabled",
        ),
        (
            "runbook",
            "does not prove production persistence",
            "Production claim boundary is explicit",
        ),
        (
            "tracker",
            "persistence/replication/HA policy",
            "Production HA work remains open",
        ),
        (
            "tracker",
            "test_distributed_rate_limit_multi_replica_failover.py",
            "Failover evidence is linked",
        ),
        (
            "roadmap",
            "### Multi-replica limiter and failover milestone — 2026-10-01",
            "Roadmap records failover milestone",
        ),
        (
            "roadmap",
            "no persistence",
            "Temporary persistence posture is explicit",
        ),
        (
            "roadmap",
            "sentinel or cluster failover",
            "Unproven production failover is explicit",
        ),
        (
            "roadmap",
            "separate lookup authorization remain open",
            "Lookup authorization remains separate",
        ),
    ]

    for document, needle, label in contracts:
        if needle not in content[document]:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    print(
        "NWDP LOOKUP MULTI-REPLICA FAILOVER "
        "DOCUMENTATION CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
