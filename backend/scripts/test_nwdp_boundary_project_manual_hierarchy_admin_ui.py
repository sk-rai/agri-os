#!/usr/bin/env python3
"""Static contract for project-only manual hierarchy controls in admin UI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = (
    ROOT
    / "web"
    / "src"
    / "app"
    / "(admin)"
    / "nwdp-boundary-review"
    / "page.tsx"
)


def require(text: str, fragment: str, label: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{label}: missing {fragment!r}")
    print(f"PASS {label}")


def main() -> int:
    text = PAGE.read_text(encoding="utf-8")

    require(
        text,
        "ManualHierarchyCandidatesResponse",
        "Manual hierarchy response is typed",
    )
    require(
        text,
        "/manual-hierarchy-candidates",
        "Project-scoped read endpoint is called",
    )
    require(
        text,
        '"MANUAL_HIERARCHY"',
        "Manual hierarchy assignment path is explicit",
    )
    require(
        text,
        "Use for this project",
        "Admin action states project scope",
    )
    require(
        text,
        "Project override active",
        "Active project override is distinguished",
    )
    require(
        text,
        "The global candidate remains blocked and inactive",
        "Confirmation preserves global status boundary",
    )
    require(
        text,
        "does not change canonical LGD",
        "UI states canonical guardrail",
    )
    require(
        text,
        "create a global equivalence",
        "UI states global-equivalence guardrail",
    )
    require(
        text,
        "unassignProjectBoundary(assignment)",
        "Manual override reuses guarded rollback",
    )
    require(
        text,
        "const BACKEND_GEOGRAPHY_VILLAGES = 600_647;",
        "Current canonical village count is displayed",
    )
    require(
        text,
        "const BACKEND_GEOGRAPHY_VILLAGES_WITH_LGD = 600_647;",
        "Current LGD village count is displayed",
    )

    forbidden = [
        "candidate_is_active = true",
        "promotion_status = 'PROMOTED'",
        "ready_for_project_manual_apply: true",
    ]
    for fragment in forbidden:
        if fragment in text:
            raise AssertionError(
                f"Forbidden global/runtime UI claim found: {fragment}"
            )

    print("PASS UI makes no global activation or promotion claim")
    print(
        "NWDP PROJECT MANUAL HIERARCHY ADMIN UI "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
