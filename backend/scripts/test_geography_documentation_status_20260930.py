#!/usr/bin/env python3
"""Static contract for the 2026-09-30 geography documentation baseline."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "docs/geography-layer-readiness-2026-09-04.md"
RECONCILIATION = (
    ROOT / "docs/geography-coverage-reconciliation-2026-09-24.md"
)
IMPORT_PLAN = ROOT / "docs/all-india-geography-import-plan.md"
GLOBAL_ROADMAP = ROOT / "docs/global-geography-model-roadmap.md"


def require(source: str, needle: str, label: str) -> None:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")


def main() -> int:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    reconciliation = RECONCILIATION.read_text(encoding="utf-8")
    import_plan = IMPORT_PLAN.read_text(encoding="utf-8")
    global_roadmap = GLOBAL_ROADMAP.read_text(encoding="utf-8")

    checks = [
        (
            roadmap,
            "Status date: 2026-09-30",
            "Roadmap status date is current",
        ),
        (
            roadmap,
            "Superseding implementation status — 2026-09-30",
            "Superseding status is explicit",
        ),
        (
            roadmap,
            "active districts: `779`",
            "Current district count is recorded",
        ),
        (
            roadmap,
            "active villages: `600,647`",
            "Current village count is recorded",
        ),
        (
            roadmap,
            "active district snapshots: `779`",
            "National snapshot coverage is recorded",
        ),
        (
            roadmap,
            "Alembic revision: `061`",
            "Snapshot schema revision is recorded",
        ),
        (
            roadmap,
            "READ_ONLY_PRECOMPUTED_DISTRICT_SNAPSHOT",
            "Interactive snapshot mode is recorded",
        ),
        (
            roadmap,
            "Project-specific Core-layer milestone",
            "Project override milestone is recorded",
        ),
        (
            roadmap,
            "District readiness snapshot milestone",
            "Snapshot milestone is recorded",
        ),
        (
            roadmap,
            "approximately `8–21 ms` backend read time",
            "Backend read evidence is recorded",
        ),
        (
            roadmap,
            "`64–109 ms` end-to-end",
            "Diverse browser evidence is recorded",
        ),
        (
            roadmap,
            "Prioritized next implementation sequence — 2026-09-30",
            "Current next sequence is explicit",
        ),
        (
            roadmap,
            "Earlier recommended implementation sequence",
            "Older sequence is labelled historical",
        ),
        (
            roadmap,
            "2026-09-30 conclusion",
            "Current conclusion is explicit",
        ),
        (
            reconciliation,
            "Subsequent status — 2026-09-30",
            "Reconciliation has a dated addendum",
        ),
        (
            reconciliation,
            "must be re-audited",
            "Historical unresolved counts are not treated as current",
        ),
        (
            import_plan,
            "Current implementation addendum — 2026-09-30",
            "Import plan has a current addendum",
        ),
        (
            global_roadmap,
            "India implementation status — 2026-09-30",
            "Global roadmap has India implementation status",
        ),
        (
            global_roadmap,
            "not a replacement for the canonical global model",
            "India snapshots remain profile-specific",
        ),
    ]

    for source, needle, label in checks:
        require(source, needle, label)

    if roadmap.count(
        "## Superseding implementation status — 2026-09-30"
    ) != 1:
        raise AssertionError("Superseding roadmap status is duplicated")

    if reconciliation.count(
        "## Subsequent status — 2026-09-30"
    ) != 1:
        raise AssertionError("Reconciliation addendum is duplicated")

    print("PASS Documentation update is idempotently anchored")
    print(
        "GEOGRAPHY DOCUMENTATION STATUS 2026-09-30 "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
