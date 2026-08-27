#!/usr/bin/env python3
"""Regression for reusing the NWDP boundary review UI for project matching read model."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web/src/app/(admin)/nwdp-boundary-review/page.tsx"


def check(condition: bool, label: str, detail: str = ""):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail:
        print("   ", detail[:1000])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    text = PAGE.read_text(encoding="utf-8")

    check("Karnataka village-boundary" not in text, "UI is no longer Karnataka-only")
    check("across staged states and UTs" in text, "UI describes all staged states/UTs")
    check("nwdp-boundary-state-wise-match-summary" in text, "UI uses state-wise summary endpoint")
    check("nwdp-boundary-project-matching/eligible-candidates" in text, "UI uses eligible candidates endpoint")
    check("Project matching read model" in text, "UI exposes project matching read model section")
    check("DIRECT_VLCODE_MATCH / AUTO_CANDIDATE" in text, "UI documents eligible direct-code predicate")
    check("excludes manual-review or blocked candidates" in text, "UI excludes unresolved/manual candidates")
    check("Apply / runtime matching: disabled" in text, "UI preserves runtime matching guardrail")
    check("api<ReviewResponse>" in text, "Existing review metadata workflow is retained")
    check("runtime point-in-polygon matching here" in text, "Existing no-runtime guardrail remains")

    check("projectsApi" in text, "UI reuses existing projects API")
    check("nwdp-boundary-project-matching/project-preview" in text, "UI uses project preview endpoint")
    check("Project coverage preview" in text, "UI exposes project coverage preview section")
    check("Project villages" in text, "UI shows project village count")
    check("Villages with boundary" in text, "UI shows covered village count")
    check("Manual / blocked excluded" in text, "UI shows excluded manual/blocked counts")
    check("inspection-only" in text, "UI labels project preview as inspection-only")

    print("=" * 72)
    print("NWDP BOUNDARY REVIEW UI PROJECT MATCHING REUSE REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
