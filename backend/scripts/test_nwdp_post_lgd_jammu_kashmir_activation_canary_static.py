#!/usr/bin/env python3
"""Static contract for the post-LGD Jammu & Kashmir canary planner."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "plan_nwdp_post_lgd_jammu_kashmir_activation_canary.py"
)


def main():
    source = SCRIPT.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        ("EXPECTED_ROWS = 821", "Canary count is pinned"),
        (
            'STATE_LGD_CODE = "1"',
            "Jammu and Kashmir scope is pinned",
        ),
        (
            "SOURCE_PROPOSAL",
            "Source proposal is pinned",
        ),
        (
            "SOURCE_MANIFEST",
            "Source manifest is pinned",
        ),
        (
            "EXPECTED_ACTIVE_BASELINE = 449_899",
            "Active baseline is pinned",
        ),
        (
            "ACTIVATE_RUNTIME_FEATURE_AND_CROSSWALK",
            "Activation scope is explicit",
        ),
        (
            "DEACTIVATE_RUNTIME_CROSSWALK_AND_FEATURE",
            "Rollback scope is explicit",
        ),
        (
            "active_village_collision",
            "Village collisions are checked",
        ),
        (
            "native_geometry_valid",
            "Native geometry is checked",
        ),
        (
            "geometry_hash_mismatch",
            "Geometry hashes are checked",
        ),
        (
            "inactive_canonical_hierarchy",
            "Canonical hierarchy is checked",
        ),
        (
            "ordered_row_manifest_sha256",
            "Ordered row manifest is pinned",
        ),
        (
            "deactivate_crosswalks_first",
            "Rollback ordering is explicit",
        ),
        (
            "single state-scoped transaction",
            "Atomic state transaction is required",
        ),
        (
            "PostgreSQL advisory lock",
            "Advisory locking is required",
        ),
        (
            "forced rollback rehearsal",
            "Rollback rehearsal is required",
        ),
        (
            '"activation_authorized": False',
            "Activation remains unauthorized",
        ),
        (
            '"lookup_exposure_authorized": False',
            "Lookup remains unauthorized",
        ),
        (
            '"candidate_changes_authorized": False',
            "Candidate changes remain unauthorized",
        ),
        (
            '"project_changes_authorized": False',
            "Project changes remain unauthorized",
        ),
        (
            '"android_changes_authorized": False',
            "Android changes remain unauthorized",
        ),
    ]

    for needle, label in checks:
        if needle not in normalized:
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
        ".commit(",
    ]
    present = [
        item
        for item in prohibited
        if item in normalized.lower()
    ]
    if present:
        raise AssertionError(
            f"Planner contains database mutations: {present}"
        )

    print("PASS Planner contains no database mutations")
    print(
        "NWDP POST-LGD JAMMU & KASHMIR "
        "ACTIVATION CANARY STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
