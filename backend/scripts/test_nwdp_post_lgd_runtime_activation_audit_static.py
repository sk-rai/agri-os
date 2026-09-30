#!/usr/bin/env python3
"""Static contract for the post-LGD runtime activation audit."""

from pathlib import Path


SCRIPT = Path(__file__).with_name(
    "audit_nwdp_post_lgd_runtime_activation.py"
)


def main():
    source = SCRIPT.read_text(encoding="utf-8")

    contracts = [
        (
            "EXPECTED_COHORT = 17_498",
            "Exact activated cohort is pinned",
        ),
        (
            "EXPECTED_TOTAL = 467_397",
            "Active runtime total is pinned",
        ),
        (
            "EXPECTED_INACTIVE_REHABILITATION = 65_005",
            "Remaining inactive rehabilitation count is pinned",
        ),
        (
            "21492ba7580dba2af0f4083dd6e9c564",
            "Completed apply checkpoint is pinned",
        ),
        (
            'checkpoint.get("mode") == "APPLY"',
            "Apply checkpoint mode is required",
        ),
        (
            'checkpoint.get("status") == "COMPLETED"',
            "Completed checkpoint is required",
        ),
        (
            "checkpoint_checksum(checkpoint)",
            "Checkpoint checksum is validated",
        ),
        (
            "native_geometry_count",
            "Native geometry coverage is measured",
        ),
        (
            "ST_SRID(rf.geometry_wgs84_geom) = 4326",
            "Geometry SRID is validated",
        ),
        (
            "ST_IsValid(rf.geometry_wgs84_geom)",
            "Geometry validity is checked",
        ),
        (
            "active_hierarchy_count",
            "Canonical hierarchy activity is checked",
        ),
        (
            "feature_identity_count",
            "Feature identities are checked",
        ),
        (
            "crosswalk_identity_count",
            "Crosswalk identities are checked",
        ),
        (
            "village_identity_count",
            "Village identities are checked",
        ),
        (
            "ST_Covers(rf.geometry_wgs84_geom, point.geom)",
            "Production spatial predicate is reused",
        ),
        (
            "limit 2",
            "Ambiguity probe is bounded",
        ),
        (
            "sampled_lookup_expected_match",
            "Expected sampled matches are required",
        ),
        (
            "sampled_lookup_unambiguous",
            "Sample ambiguity is rejected",
        ),
        (
            "sampled_lookup_latency_bounded",
            "Sample lookup latency is bounded",
        ),
        (
            "before == after",
            "Database counts are compared",
        ),
        (
            '"lookup_exposure_changed": False',
            "Lookup exposure remains unchanged",
        ),
        (
            '"database_writes_attempted": False',
            "Read-only policy is explicit",
        ),
        (
            '"no_database_writes": True',
            "Successful no-write check is explicit",
        ),
        (
            '"candidate_changes_authorized": False',
            "Candidate changes remain unauthorized",
        ),
        (
            '"canonical_changes_authorized": False',
            "Canonical changes remain unauthorized",
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

    for needle, label in contracts:
        if needle not in source:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    lowered = source.lower()
    forbidden = (
        "insert into ",
        "update geography_",
        "delete from ",
        ".commit()",
    )
    for needle in forbidden:
        if needle in lowered:
            raise AssertionError(
                f"Database mutation found: {needle!r}"
            )

    print("PASS Audit contains no database mutations")
    print(
        "NWDP POST-LGD RUNTIME ACTIVATION AUDIT "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
