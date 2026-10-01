#!/usr/bin/env python3
"""Documentation contract for the enabled local admin-only pilot."""

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
            "## Local admin-only lookup pilot enabled — 2026-10-01",
            "Enabled-pilot milestone is dated",
        ),
        (
            "runbook",
            "Commit `60b1eab`",
            "Canary commit is recorded",
        ),
        (
            "runbook",
            "Commit\n`2e7e4b3`",
            "Post-enablement audit commit is recorded",
        ),
        (
            "runbook",
            "LOCAL_ADMIN_ONLY_LOOKUP_PILOT_ENABLED_AUDIT_PASSED",
            "Enabled audit status is recorded",
        ),
        (
            "runbook",
            "anonymous access returns `401`",
            "Anonymous denial is recorded",
        ),
        (
            "runbook",
            "decremented exactly from `10` to `9` to `8`",
            "FREE budget evidence is recorded",
        ),
        (
            "runbook",
            "remained exactly `467,397`",
            "Runtime baseline is retained",
        ),
        (
            "runbook",
            "does not authorize customer, Android",
            "Wider access remains unauthorized",
        ),
        (
            "runbook",
            "Repository defaults remain fail-closed",
            "Repository defaults remain safe",
        ),
        (
            "runbook",
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED=false",
            "Rollback flag is explicit",
        ),
        (
            "tracker",
            "lookup is true only for the separately authorized "
            "authenticated-admin pilot",
            "Tracker records exact local scope",
        ),
        (
            "tracker",
            "Commits `60b1eab` and `2e7e4b3`",
            "Tracker records live evidence",
        ),
        (
            "tracker",
            "audit_nwdp_runtime_lookup_admin_pilot_enabled.py",
            "Post-enablement audit is linked",
        ),
        (
            "roadmap",
            "### Local admin-only lookup pilot enabled — 2026-10-01",
            "Roadmap records enabled pilot",
        ),
        (
            "roadmap",
            "denied anonymous access with `401`",
            "Roadmap records access control",
        ),
        (
            "roadmap",
            "Repository defaults remain disabled",
            "Roadmap distinguishes defaults",
        ),
        (
            "roadmap",
            "does not authorize customer, Android, public, or production",
            "Production claim boundary is retained",
        ),
    ]

    for document, needle, label in contracts:
        if needle not in content[document]:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    print(
        "NWDP LOCAL ADMIN-ONLY LOOKUP PILOT ENABLED "
        "DOCUMENTATION CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
