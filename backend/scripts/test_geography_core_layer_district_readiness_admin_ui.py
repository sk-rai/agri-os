#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web/src/app/(admin)/geography-layer-readiness/page.tsx"


def check(source: str, needle: str, label: str) -> None:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")


def main() -> int:
    source = PAGE.read_text(encoding="utf-8")
    checks = [
        ("CORE_DISTRICT_REVIEW_BASELINE", "Reviewed baseline is explicit"),
        ('asOf: "2026-09-28"', "Baseline date is pinned"),
        ("totalDistricts: 779", "Canonical district count is displayed"),
        ("mappedDistricts: 186", "Mapped district count is displayed"),
        ("remainingDistricts: 593", "Remaining district count is displayed"),
        ("overlayBackedDistricts: 570", "Overlay-backed route count is displayed"),
        ("authoritativeSourceDistricts: 23", "Authoritative-source route count is displayed"),
        ("readyForNormalReviewDistricts: 515", "Normal review district count is displayed"),
        ("lowOverlapReviewDistricts: 42", "Low-overlap district count is displayed"),
        ("staleHierarchyDistricts: 2", "Stale hierarchy count is displayed"),
        ("missingCurrentGeometryDistricts: 11", "Missing current geometry count is displayed"),
        ('href="/core-lgd-review"', "Existing Core LGD review page is linked"),
        ("inactive review routes", "Review rows are distinguished from live mappings"),
        ("do not authorize", "Database apply remains unauthorized"),
        ("runtime activation", "Runtime activation guardrail is explicit"),
        ("canonical LGD changes", "Canonical LGD guardrail is explicit"),
        ("Android behavior changes", "Android guardrail is explicit"),
    ]
    for needle, label in checks:
        check(source, needle, label)

    print("GEOGRAPHY CORE LAYER DISTRICT READINESS ADMIN UI STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
