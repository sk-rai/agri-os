#!/usr/bin/env python3
"""Static regression for project-scoped NWDP boundary assignment controls."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web/src/app/(admin)/nwdp-boundary-review/page.tsx"


def check(condition: bool, label: str) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if not condition:
        raise AssertionError(label)


def main() -> int:
    text = PAGE.read_text(encoding="utf-8")

    check("ProjectBoundaryAssignment" in text, "UI models project assignments")
    check("/assignments`" in text, "UI loads existing assignments")
    check("assignProjectBoundary" in text, "UI provides assignment action")
    check("unassignProjectBoundary" in text, "UI provides unassignment action")
    check('method: "PUT"' in text, "Assignment uses guarded PUT")
    check('method: "DELETE"' in text, "Unassignment uses guarded DELETE")
    check("rollback_token: rollbackToken" in text, "Assignment records rollback token")
    check(
        "assignment.rollback_token" in text,
        "Unassignment uses recorded rollback token",
    )
    check("PROJECT_EDIT permission" in text, "UI states permission requirement")
    check(
        "Only VALIDATED direct-code candidates" in text,
        "UI states validation requirement",
    )
    check("Candidate promotion" in text, "Candidate promotion remains unchanged")
    check("runtime eligibility" in text, "Runtime eligibility remains unchanged")
    check("global lookup" in text, "Global lookup remains unchanged")
    check("Android behavior remain unchanged" in text, "Android remains unchanged")
    check('"Assign"' in text, "UI renders Assign control")
    check('"Unassign"' in text, "UI renders Unassign control")
    check('method: "POST"' not in text, "UI does not invoke broad apply")

    print("=" * 72)
    print("NWDP PROJECT BOUNDARY ASSIGNMENT UI REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
