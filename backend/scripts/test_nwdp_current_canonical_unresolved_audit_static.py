#!/usr/bin/env python3
"""Static contract for current-canonical unresolved NWDP re-audit."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "audit_nwdp_current_canonical_unresolved.py"
)


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        (
            "audit_nwdp_post_lgd_reconciliation.py",
            source,
            "Existing post-LGD audit is reused",
        ),
        (
            "build_nwdp_legacy_held_resolution_coverage_manifest.py",
            source,
            "Existing legacy coverage verifier is reused",
        ),
        (
            "geography_boundary_crosswalk_candidates",
            source,
            "Correct candidate table is measured",
        ),
        (
            "geography_boundary_source_features",
            source,
            "Source-feature table is measured",
        ),
        (
            '"villages": 600_647',
            source,
            "Current village baseline is pinned",
        ),
        (
            '"districts": 779',
            source,
            "Current district baseline is pinned",
        ),
        (
            '"combined_unresolved": 14_773',
            source,
            "Combined unresolved count is pinned",
        ),
        (
            '"post_unresolved": 4_721',
            source,
            "Post-LGD unresolved count is pinned",
        ),
        (
            '"legacy_unresolved": 10_052',
            source,
            "Legacy unresolved count is pinned",
        ),
        (
            "candidate_populations_disjoint",
            source,
            "Candidate populations must be disjoint",
        ),
        (
            "database_counts_unchanged",
            source,
            "Database before and after counts are compared",
        ),
        (
            '"database_writes_attempted": False',
            source,
            "Read-only behavior is explicit",
        ),
        (
            '"automatic_resolution_authorized": False',
            normalized,
            "Automatic resolution remains unauthorized",
        ),
        (
            '"canonical_geography_changes_authorized": False',
            normalized,
            "Canonical changes remain unauthorized",
        ),
        (
            '"runtime_activation_authorized": False',
            normalized,
            "Runtime activation remains unauthorized",
        ),
        (
            '"android_changes_authorized": False',
            normalized,
            "Android changes remain unauthorized",
        ),
    ]

    for needle, body, label in checks:
        if needle not in body:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    prohibited = [
        "insert into",
        "update geography_",
        "delete from",
        "alter table",
        "drop table",
        "create table",
        ".commit(",
    ]
    present = [
        needle
        for needle in prohibited
        if needle in normalized.lower()
    ]
    if present:
        raise AssertionError(
            "Audit contains forbidden database "
            f"mutations: {present}"
        )

    print("PASS Audit contains no database mutations")
    print(
        "NWDP CURRENT CANONICAL UNRESOLVED "
        "AUDIT STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
