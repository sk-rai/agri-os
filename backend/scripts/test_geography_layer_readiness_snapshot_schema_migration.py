#!/usr/bin/env python3
"""Static contract for geography readiness snapshot migration."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "backend/alembic/versions/"
    "061_add_geography_layer_readiness_snapshots.py"
)


def main() -> int:
    source = MIGRATION.read_text(encoding="utf-8")

    checks = [
        ('revision = "061"', "Revision is 061"),
        ('down_revision = "060"', "Migration follows revision 060"),
        (
            '"geography_layer_readiness_snapshots"',
            "Dedicated snapshot table is created",
        ),
        (
            'sa.ForeignKey("geography_states.id")',
            "Canonical state foreign key is required",
        ),
        (
            'sa.ForeignKey("geography_districts.id")',
            "Canonical district foreign key is required",
        ),
        (
            '"state_lgd_code"',
            "State LGD identity is retained",
        ),
        (
            '"district_lgd_code"',
            "District LGD identity is retained",
        ),
        (
            '"snapshot_schema_version"',
            "Snapshot schema version is explicit",
        ),
        (
            '"readiness_payload"',
            "Precomputed readiness payload is retained",
        ),
        (
            '"source_versions"',
            "Source versions are retained",
        ),
        (
            '"evidence_metadata"',
            "Evidence metadata is retained",
        ),
        (
            '"computed_at"',
            "Snapshot calculation time is retained",
        ),
        (
            '"refresh_run_id"',
            "Offline refresh run is traceable",
        ),
        (
            '"failure_reason"',
            "Failed refresh evidence can be retained",
        ),
        (
            "calculation_status in "
            "('READY', 'STALE', 'FAILED')",
            "Snapshot lifecycle is constrained",
        ),
        (
            "is_active = false or "
            "calculation_status = 'READY'",
            "Only ready snapshots may be active",
        ),
        (
            '"state_id", "district_id"',
            "Active uniqueness is district scoped",
        ),
        (
            'postgresql_where=sa.text("is_active = true")',
            "Active uniqueness uses a partial index",
        ),
        (
            '"calculation_status", "computed_at"',
            "Freshness lookup is indexed",
        ),
        (
            'op.drop_table("geography_layer_readiness_snapshots")',
            "Downgrade removes only the snapshot table",
        ),
    ]

    for needle, label in checks:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    forbidden = [
        "geography_boundary_crosswalk_candidates",
        "geography_boundary_source_features",
        "st_intersection",
        "st_area",
        "st_union",
        "runtime_lookup_enabled",
        "android_behavior_changed",
    ]
    present = [needle for needle in forbidden if needle in source.lower()]
    if present:
        raise AssertionError(
            "Migration contains runtime computation or behavior changes: "
            f"{present}"
        )

    print("PASS Migration performs no geometry computation")
    print("PASS Migration changes no runtime or Android behavior")
    print(
        "GEOGRAPHY LAYER READINESS SNAPSHOT "
        "SCHEMA MIGRATION CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
