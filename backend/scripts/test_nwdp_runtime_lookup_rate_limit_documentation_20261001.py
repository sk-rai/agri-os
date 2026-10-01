#!/usr/bin/env python3
"""Documentation contract for tiered distributed NWDP lookup limits."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

DOCUMENTS = {
    "runbook":
        ROOT / "docs/nwdp-runtime-point-lookup-pilot-runbook.md",
    "tracker":
        ROOT / "docs/backend-gap-closure-tracker.md",
    "roadmap":
        ROOT / "docs/geography-layer-readiness-2026-09-04.md",
}


def main():
    text = {
        name: path.read_text(encoding="utf-8")
        for name, path in DOCUMENTS.items()
    }

    contracts = [
        (
            "runbook",
            "`467,397` active runtime features",
            "Current active runtime total is documented",
        ),
        (
            "runbook",
            "## Distributed rate-limit implementation — 2026-10-01",
            "Rate-limit milestone is dated",
        ),
        (
            "runbook",
            "`FREE`, `STANDARD`, `PRO`, and `ENTERPRISE`",
            "Customer tiers are documented",
        ),
        (
            "runbook",
            "atomic actor, tenant, and global budgets",
            "Atomic budget dimensions are documented",
        ),
        (
            "runbook",
            "tier resolution from persisted `tenants.config`",
            "Server-owned tier source is documented",
        ),
        (
            "runbook",
            "fail-closed `503` behavior",
            "Fail-closed behavior is documented",
        ),
        (
            "runbook",
            "Commit `bd07091` also validated the limiter",
            "Real Redis integration evidence is recorded",
        ),
        (
            "tracker",
            "Local admin-only pilot enabled; wider exposure pending",
            "Tracker status distinguishes local pilot from wider exposure",
        ),
        (
            "tracker",
            "Both lookup and limiter flags remain false",
            "Tracker records safe defaults",
        ),
        (
            "roadmap",
            "### Distributed lookup rate-limit milestone — 2026-10-01",
            "Roadmap records the milestone",
        ),
        (
            "roadmap",
            "no Redis dependency while the lookup feature flag is disabled",
            "Disabled lookup independence is documented",
        ),
        (
            "roadmap",
            "four independent worker processes",
            "Multi-process Redis evidence is documented",
        ),
        (
            "roadmap",
            "no lookup, Android, customer, or public exposure is",
            "Exposure remains unauthorized",
        ),
    ]

    for document, needle, label in contracts:
        if needle not in text[document]:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    combined = "\n".join(text.values())
    for stale in (
        "The runtime set now contains 449,899 active rows",
        "It currently contains 449,899 active runtime",
    ):
        if stale in combined:
            raise AssertionError(
                f"Stale active baseline remains: {stale!r}"
            )

    print("PASS Stale runtime totals are not current")
    print(
        "NWDP LOOKUP RATE-LIMIT DOCUMENTATION "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
