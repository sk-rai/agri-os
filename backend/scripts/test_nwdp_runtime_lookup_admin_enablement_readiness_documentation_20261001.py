#!/usr/bin/env python3
"""Documentation contract for admin-only lookup readiness."""

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
            "## Admin-only lookup enablement readiness — 2026-10-01",
            "Readiness milestone is dated",
        ),
        (
            "runbook",
            "Commit `3257c35`",
            "Readiness commit is recorded",
        ),
        (
            "runbook",
            "READY_FOR_SEPARATE_ADMIN_ONLY_AUTHORIZATION",
            "Readiness status is recorded",
        ),
        (
            "runbook",
            "`authorized` remains false",
            "Authorization remains false",
        ),
        (
            "runbook",
            "`467,397` active runtime features",
            "Runtime baseline is retained",
        ),
        (
            "runbook",
            "AdminPermission.VIEW",
            "Admin-only permission is recorded",
        ),
        (
            "runbook",
            "limiter-before-SQL\n  ordering",
            "Limiter ordering is recorded",
        ),
        (
            "runbook",
            "resolves to\n  `FREE`",
            "Default tenant tier is documented",
        ),
        (
            "runbook",
            "10 actor requests, 30 tenant requests",
            "Free-tier quotas are documented",
        ),
        (
            "runbook",
            "LOCAL_ADMIN_ONLY_RUNTIME_LOOKUP_PILOT",
            "Proposed scope is explicit",
        ),
        (
            "runbook",
            "requires a separate explicit authorization",
            "Enablement remains separately gated",
        ),
        (
            "tracker",
            "authorization remains false",
            "Tracker distinguishes readiness from authorization",
        ),
        (
            "tracker",
            "audit_nwdp_runtime_lookup_admin_enablement_readiness.py",
            "Audit evidence is linked",
        ),
        (
            "roadmap",
            "### Admin-only lookup enablement readiness — 2026-10-01",
            "Roadmap records readiness",
        ),
        (
            "roadmap",
            "not authorization",
            "Roadmap preserves claim boundary",
        ),
        (
            "roadmap",
            "Lookup\nremains disabled",
            "Lookup remains disabled",
        ),
        (
            "roadmap",
            "Customer, Android, public, and production exposure",
            "Wider exposure remains excluded",
        ),
    ]

    for document, needle, label in contracts:
        if needle not in content[document]:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    print(
        "NWDP ADMIN-ONLY LOOKUP ENABLEMENT READINESS "
        "DOCUMENTATION CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
