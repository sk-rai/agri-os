#!/usr/bin/env python3
"""Static safety contract for post-LGD activation-readiness audit."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "audit_nwdp_post_lgd_activation_readiness.py"
)


def main():
    source = SCRIPT.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        ("EXPECTED_ROWS = 17_498", "Exact cohort is pinned"),
        ("EXPECTED_EVENTS = 8", "Inactive events are pinned"),
        ("RUNTIME_SET_ID", "Runtime set identity is pinned"),
        ("PROPOSAL_CHECKSUM", "Proposal checksum is pinned"),
        ("MANIFEST_CHECKSUM", "Manifest checksum is pinned"),
        ("source_geometry_hash", "Source geometry hash is checked"),
        ("ST_IsValid", "Native geometry is validated"),
        ("ST_SRID", "Geometry SRID is validated"),
        ("eligible_for_runtime_after_promotion", "Runtime eligibility is checked"),
        ("village.is_active", "Canonical village activity is checked"),
        ("block.is_active", "Canonical block activity is checked"),
        ("district.is_active", "Canonical district activity is checked"),
        ("state.is_active", "Canonical state activity is checked"),
        ("active_village_collision_count", "Active collisions are checked"),
        ("database_counts_unchanged", "Database counts are compared"),
        ("state_partition_exact", "State partition is exact"),
        ("Jammu & Kashmir", "Canary state is explicit"),
        ('"activation_authorized": False', "Activation remains unauthorized"),
        ('"lookup_exposure_authorized": False', "Lookup remains unauthorized"),
        ('"project_changes_authorized": False', "Project changes remain unauthorized"),
        ('"android_changes_authorized": False', "Android changes remain unauthorized"),
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
            f"Audit contains database mutations: {present}"
        )

    print("PASS Audit contains no database mutations")
    print(
        "NWDP POST-LGD ACTIVATION READINESS "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
