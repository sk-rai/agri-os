#!/usr/bin/env python3
"""Static contract for Core-layer project override migration."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "backend/alembic/versions/"
    "060_add_core_layer_project_overrides.py"
)


def check(source: str, needle: str, label: str) -> None:
    if needle not in source:
        raise AssertionError(
            f"{label}: missing {needle!r}"
        )
    print(f"PASS {label}")


def main() -> int:
    source = MIGRATION.read_text(encoding="utf-8")

    checks = [
        ('revision = "060"', "Revision is 060"),
        (
            'down_revision = "059"',
            "Migration follows revision 059",
        ),
        (
            '"geography_core_layer_project_overrides"',
            "Dedicated override table is created",
        ),
        (
            'sa.ForeignKey("tenants.id")',
            "Tenant foreign key is required",
        ),
        (
            'sa.ForeignKey("projects.id")',
            "Project foreign key is required",
        ),
        (
            'sa.ForeignKey("geography_villages.id")',
            "Village foreign key is required",
        ),
        (
            'sa.ForeignKey("geography_climate_regions.id")',
            "Core region foreign key is required",
        ),
        (
            '"region_system"',
            "Core region system is explicit",
        ),
        (
            '"assignment_status"',
            "Assignment lifecycle is explicit",
        ),
        (
            '"rollback_token"',
            "Rollback token is required",
        ),
        (
            '"dry_run_report"',
            "Dry-run evidence is retained",
        ),
        (
            '"apply_report"',
            "Apply evidence is retained",
        ),
        (
            '"rollback_report"',
            "Rollback evidence is retained",
        ),
        (
            "is_active = false",
            "Inactive rows are allowed",
        ),
        (
            "assignment_status = 'APPLIED'",
            "Only applied rows may be active",
        ),
        (
            '"tenant_id",\n            "project_id",\n'
            '            "village_id",\n'
            '            "region_system",',
            "Active uniqueness is project-village-layer scoped",
        ),
        (
            'postgresql_where=sa.text("is_active = true")',
            "Active uniqueness uses a partial index",
        ),
        (
            "op.drop_table(TABLE)",
            "Downgrade removes only the override table",
        ),
    ]

    for needle, label in checks:
        check(source, needle, label)

    forbidden = [
        "geography_climate_region_mappings",
        "update geography_",
        "delete from geography_",
        "android",
    ]
    lowered = source.lower()
    for needle in forbidden:
        if needle in lowered:
            raise AssertionError(
                f"Migration contains forbidden global/runtime "
                f"operation: {needle}"
            )

    print(
        "CORE LAYER PROJECT OVERRIDE SCHEMA "
        "MIGRATION CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
