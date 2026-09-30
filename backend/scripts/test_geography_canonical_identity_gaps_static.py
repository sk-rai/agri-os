#!/usr/bin/env python3
"""Static contract for canonical geography identity-gap audit."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT / "backend/scripts/"
    "audit_geography_canonical_identity_gaps.py"
)


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        ("476380", source, "Duplicate LGD code is pinned"),
        (
            "CHANDIGARH_LGD_CODE = \"4\"",
            source,
            "Chandigarh LGD identity is pinned",
        ),
        (
            "pg_constraint",
            source,
            "Foreign-key references are discovered",
        ),
        (
            "geography_villages",
            source,
            "Canonical villages are audited",
        ),
        (
            "geography_scope",
            source,
            "Project code references are audited",
        ),
        (
            "geography_climate_region_mappings",
            source,
            "Climate code references are audited",
        ),
        (
            "CANONICAL_STATE_GAP_REVIEW",
            source,
            "Chandigarh held rows are audited",
        ),
        (
            "duplicate_hierarchy_conflict_present",
            source,
            "Duplicate hierarchy conflict is required",
        ),
        (
            "chandigarh_review_count_exact",
            source,
            "Twelve Chandigarh rows are required",
        ),
        (
            "database_counts_unchanged",
            source,
            "Database counts are compared",
        ),
        (
            '"canonical_merge_authorized": False',
            normalized,
            "Canonical merge remains unauthorized",
        ),
        (
            '"canonical_reparent_authorized": False',
            normalized,
            "Canonical reparent remains unauthorized",
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
        needle for needle in prohibited
        if needle in normalized.lower()
    ]
    if present:
        raise AssertionError(
            f"Audit contains mutations: {present}"
        )

    print("PASS Audit contains no database mutations")
    print(
        "GEOGRAPHY CANONICAL IDENTITY GAP "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
