#!/usr/bin/env python3
"""Documentation contract for limiter observability."""

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
            "## Limiter observability — 2026-10-01",
            "Observability milestone is dated",
        ),
        (
            "runbook",
            "Commit `e710753`",
            "Observability commit is recorded",
        ),
        (
            "runbook",
            "bounded counters by outcome",
            "Bounded decision counters are documented",
        ),
        (
            "runbook",
            "cumulative latency buckets",
            "Latency metrics are documented",
        ),
        (
            "runbook",
            "aggregate remaining-budget",
            "Remaining-budget metrics are documented",
        ),
        (
            "runbook",
            "exactly one structured event",
            "Structured event cardinality is documented",
        ),
        (
            "runbook",
            "no actor ID, tenant ID, request coordinates",
            "Sensitive labels are excluded",
        ),
        (
            "runbook",
            "process-local snapshot scope",
            "Process-local scope is explicit",
        ),
        (
            "runbook",
            "cross-worker and cross-replica aggregation boundary",
            "Structured-log aggregation is explicit",
        ),
        (
            "tracker",
            "external log collection and alert routing",
            "Remaining operational monitoring is explicit",
        ),
        (
            "tracker",
            "Repository defaults remain safe",
            "Repository-safe defaults remain explicit",
        ),
        (
            "tracker",
            "current local WSL runtime",
            "Local operational configuration is distinguished",
        ),
        (
            "tracker",
            "lookup is true only for the separately authorized "
            "authenticated-admin pilot",
            "Local pilot state is distinguished from repository defaults",
        ),
        (
            "tracker",
            "loopback-only Redis service at `127.0.0.1:6379`",
            "Local Redis endpoint posture is documented",
        ),
        (
            "tracker",
            "test_distributed_rate_limit_observability.py",
            "Behavior evidence is linked",
        ),
        (
            "roadmap",
            "### Distributed limiter observability milestone — 2026-10-01",
            "Roadmap records observability milestone",
        ),
        (
            "roadmap",
            "does not add a public metrics endpoint",
            "No metrics exposure is claimed",
        ),
        (
            "roadmap",
            "does not add a public metrics endpoint, enable lookup",
            "Lookup remains disabled",
        ),
        (
            "roadmap",
            "production Redis TLS",
            "Production Redis work remains explicit",
        ),
    ]

    for document, needle, label in contracts:
        if needle not in content[document]:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    print(
        "NWDP LOOKUP LIMITER OBSERVABILITY "
        "DOCUMENTATION CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
