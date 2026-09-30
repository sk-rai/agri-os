#!/usr/bin/env python3
"""Static documentation contract for post-LGD activation status."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

DOCUMENTS = {
    "roadmap": ROOT / "docs/geography-layer-readiness-2026-09-04.md",
    "reconciliation":
        ROOT / "docs/geography-coverage-reconciliation-2026-09-24.md",
    "tracker": ROOT / "docs/backend-gap-closure-tracker.md",
    "global": ROOT / "docs/global-geography-model-roadmap.md",
}


def main():
    text = {
        name: path.read_text(encoding="utf-8")
        for name, path in DOCUMENTS.items()
    }

    contracts = [
        (
            "roadmap",
            "### Post-LGD runtime activation milestone",
            "Runtime activation milestone is recorded",
        ),
        (
            "roadmap",
            "active runtime totals increased from `449,899` to `467,397`",
            "Runtime total transition is recorded",
        ),
        (
            "roadmap",
            "`65,005` inactive rehabilitation rows remain",
            "Remaining inactive total is recorded",
        ),
        (
            "roadmap",
            "`14,773` unresolved rows remain held",
            "Unresolved population is retained",
        ),
        (
            "roadmap",
            "### Progress against the current sequence — 2026-09-30",
            "Implementation sequence progress is current",
        ),
        (
            "reconciliation",
            "## Post-LGD runtime activation status — 2026-09-30",
            "Reconciliation has a dated activation addendum",
        ),
        (
            "reconciliation",
            "active runtime features: `467,397`",
            "Reconciliation records active features",
        ),
        (
            "reconciliation",
            "remaining inactive rehabilitation rows: `65,005`",
            "Reconciliation records remaining inactive rows",
        ),
        (
            "tracker",
            "The runtime set now contains 467,397 active rows",
            "Backend tracker has the current runtime total",
        ),
        (
            "tracker",
            "Post-LGD cohort activated",
            "Backend campaign status is current",
        ),
        (
            "global",
            "### India runtime-boundary status — 2026-09-30",
            "Global roadmap has India runtime status",
        ),
        (
            "global",
            "India now has `467,397` active runtime boundary",
            "Global roadmap records India active coverage",
        ),
    ]

    for document, needle, label in contracts:
        if needle not in text[document]:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    combined = "\n".join(text.values())
    guardrails = [
        (
            "External/public/Android spatial lookup exposure remains",
            "Lookup exposure remains separately gated",
        ),
        (
            "shared gateway or distributed rate limiting",
            "Distributed rate-limit blocker remains explicit",
        ),
        (
            "Candidate rows remain inactive",
            "Candidate state distinction is retained",
        ),
    ]

    for needle, label in guardrails:
        if needle not in combined:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    print(
        "GEOGRAPHY POST-LGD ACTIVATION DOCUMENTATION "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
