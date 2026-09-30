#!/usr/bin/env python3
"""Audit duplicate village identity and Chandigarh hierarchy gaps.

Database behavior: read-only.

No canonical merge, reparenting, insertion, deletion, project-scope change,
mapping change, runtime activation, or Android change is authorized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import settings


SCHEMA_VERSION = (
    "geography_canonical_identity_gap_audit.v1"
)
DUPLICATE_LGD_CODE = "476380"
CHANDIGARH_LGD_CODE = "4"

DEFAULT_LEGACY_ROWS = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260925-lgd-priority-state-reconciliation-v1"
    / "nwdp_legacy_held_review_queue_rows.jsonl"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260930-canonical-identity-gap-audit-v1"
    / "geography_canonical_identity_gap_audit.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--legacy-rows",
        type=Path,
        default=DEFAULT_LEGACY_ROWS,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--database-url",
        default=settings.DATABASE_URL,
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def database_baseline(connection) -> dict[str, int]:
    queries = {
        "states": """
            select count(*) from geography_states
            where is_active
        """,
        "districts": """
            select count(*) from geography_districts
            where is_active
        """,
        "blocks": """
            select count(*) from geography_blocks
            where is_active
        """,
        "villages": """
            select count(*) from geography_villages
            where is_active
        """,
        "boundary_candidates": """
            select count(*)
            from geography_boundary_crosswalk_candidates
        """,
        "boundary_source_features": """
            select count(*)
            from geography_boundary_source_features
        """,
        "snapshots": """
            select count(*)
            from geography_layer_readiness_snapshots
        """,
        "active_snapshots": """
            select count(*)
            from geography_layer_readiness_snapshots
            where is_active
        """,
    }
    return {
        name: int(
            connection.execute(
                text(sql)
            ).scalar_one()
        )
        for name, sql in queries.items()
    }


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def main() -> int:
    args = parse_args()
    engine = create_engine(
        args.database_url,
        pool_pre_ping=True,
    )

    legacy_rows = [
        json.loads(line)
        for line in args.legacy_rows.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    chandigarh_review_rows = [
        row
        for row in legacy_rows
        if row.get("review_queue")
        == "CANONICAL_STATE_GAP_REVIEW"
    ]

    with engine.connect() as connection:
        before = database_baseline(connection)

        duplicate_rows = [
            dict(row)
            for row in connection.execute(
                text("""
                    select
                      village.id::text as village_id,
                      village.lgd_code::text
                        as village_lgd_code,
                      village.canonical_name
                        as village_name,
                      village.is_active,
                      block.id::text as block_id,
                      block.lgd_code::text as block_lgd_code,
                      block.canonical_name as block_name,
                      district.id::text as district_id,
                      district.lgd_code::text
                        as district_lgd_code,
                      district.canonical_name
                        as district_name,
                      state.id::text as state_id,
                      state.lgd_code::text as state_lgd_code,
                      state.canonical_name as state_name
                    from geography_villages village
                    join geography_blocks block
                      on block.id = village.block_id
                    join geography_districts district
                      on district.id = village.district_id
                    join geography_states state
                      on state.id = district.state_id
                    where village.lgd_code::text = :code
                    order by state.lgd_code,
                             district.lgd_code,
                             block.lgd_code,
                             village.id
                """),
                {"code": DUPLICATE_LGD_CODE},
            ).mappings()
        ]

        duplicate_ids = [
            row["village_id"]
            for row in duplicate_rows
        ]

        foreign_keys = [
            dict(row)
            for row in connection.execute(text("""
                select
                  child_ns.nspname as child_schema,
                  child.relname as child_table,
                  child_col.attname as child_column,
                  constraint_row.conname
                    as constraint_name
                from pg_constraint constraint_row
                join pg_class child
                  on child.oid = constraint_row.conrelid
                join pg_namespace child_ns
                  on child_ns.oid = child.relnamespace
                join pg_class parent
                  on parent.oid = constraint_row.confrelid
                join pg_namespace parent_ns
                  on parent_ns.oid = parent.relnamespace
                join unnest(
                  constraint_row.conkey
                ) with ordinality child_key(
                  attnum,
                  ordinal
                ) on true
                join unnest(
                  constraint_row.confkey
                ) with ordinality parent_key(
                  attnum,
                  ordinal
                )
                  on parent_key.ordinal = child_key.ordinal
                join pg_attribute child_col
                  on child_col.attrelid = child.oid
                 and child_col.attnum = child_key.attnum
                join pg_attribute parent_col
                  on parent_col.attrelid = parent.oid
                 and parent_col.attnum = parent_key.attnum
                where constraint_row.contype = 'f'
                  and parent_ns.nspname = 'public'
                  and parent.relname = 'geography_villages'
                  and parent_col.attname = 'id'
                order by child.relname,
                         child_col.attname
            """)).mappings()
        ]

        reference_counts: list[dict[str, Any]] = []
        for foreign_key in foreign_keys:
            schema = quote_identifier(
                foreign_key["child_schema"]
            )
            table = quote_identifier(
                foreign_key["child_table"]
            )
            column = quote_identifier(
                foreign_key["child_column"]
            )
            sql = text(
                f"""
                select
                  {column}::text as village_id,
                  count(*)::bigint as reference_count
                from {schema}.{table}
                where {column}::text = any(:village_ids)
                group by {column}
                order by {column}::text
                """
            )
            rows = [
                dict(row)
                for row in connection.execute(
                    sql,
                    {"village_ids": duplicate_ids},
                ).mappings()
            ]
            reference_counts.append({
                **foreign_key,
                "references": rows,
                "total_reference_count": sum(
                    int(row["reference_count"])
                    for row in rows
                ),
            })

        project_scope_rows = [
            dict(row)
            for row in connection.execute(
                text("""
                    select
                      project.id::text as project_id,
                      project.tenant_id,
                      project.name,
                      project.status,
                      project.is_active
                    from projects project
                    where exists (
                      select 1
                      from jsonb_array_elements_text(
                        coalesce(
                          project.geography_scope
                            -> 'village_lgd_codes',
                          '[]'::jsonb
                        )
                      ) as code(value)
                      where code.value = :code
                    )
                    order by project.tenant_id,
                             project.id
                """),
                {"code": DUPLICATE_LGD_CODE},
            ).mappings()
        ]

        climate_code_references = int(
            connection.execute(
                text("""
                    select count(*)
                    from geography_climate_region_mappings
                    where village_lgd_code = :code
                """),
                {"code": DUPLICATE_LGD_CODE},
            ).scalar_one()
        )

        chandigarh_states = [
            dict(row)
            for row in connection.execute(
                text("""
                    select
                      id::text,
                      lgd_code::text,
                      canonical_name,
                      is_active
                    from geography_states
                    where lgd_code::text = :code
                       or lower(canonical_name)
                          = 'chandigarh'
                    order by id
                """),
                {"code": CHANDIGARH_LGD_CODE},
            ).mappings()
        ]

        chandigarh_hierarchy = dict(
            connection.execute(
                text("""
                    select
                      count(distinct state.id)::bigint
                        as state_count,
                      count(distinct district.id)::bigint
                        as district_count,
                      count(distinct block.id)::bigint
                        as block_count,
                      count(distinct village.id)::bigint
                        as village_count
                    from geography_states state
                    left join geography_districts district
                      on district.state_id = state.id
                     and district.is_active
                    left join geography_blocks block
                      on block.district_id = district.id
                     and block.is_active
                    left join geography_villages village
                      on village.district_id = district.id
                     and village.is_active
                    where (
                      state.lgd_code::text = :code
                      or lower(state.canonical_name)
                         = 'chandigarh'
                    )
                      and state.is_active
                """),
                {"code": CHANDIGARH_LGD_CODE},
            ).mappings().one()
        )

        after = database_baseline(connection)

    distinct_hierarchies = {
        (
            row["state_lgd_code"],
            row["district_lgd_code"],
            row["block_lgd_code"],
        )
        for row in duplicate_rows
    }

    chandigarh_candidate_ids = {
        row["candidate_id"]
        for row in chandigarh_review_rows
    }
    chandigarh_source_ids = {
        row["source_feature_id"]
        for row in chandigarh_review_rows
    }

    checks = {
        "duplicate_village_count_is_two":
            len(duplicate_rows) == 2,
        "duplicate_village_ids_distinct":
            len(duplicate_ids)
            == len(set(duplicate_ids))
            == 2,
        "duplicate_hierarchy_conflict_present":
            len(distinct_hierarchies) > 1,
        "foreign_key_inventory_present":
            len(foreign_keys) > 0,
        "all_foreign_keys_measured":
            len(reference_counts)
            == len(foreign_keys),
        "project_code_references_measured":
            isinstance(project_scope_rows, list),
        "climate_code_references_measured":
            climate_code_references >= 0,
        "chandigarh_canonical_state_absent":
            len(chandigarh_states) == 0,
        "chandigarh_hierarchy_empty":
            all(
                int(value) == 0
                for value in
                chandigarh_hierarchy.values()
            ),
        "chandigarh_review_count_exact":
            len(chandigarh_review_rows) == 12,
        "chandigarh_candidate_identity_unique":
            len(chandigarh_candidate_ids) == 12,
        "chandigarh_source_identity_unique":
            len(chandigarh_source_ids) == 12,
        "database_counts_unchanged":
            before == after,
        "canonical_changes_unauthorized": True,
        "automatic_merge_unauthorized": True,
        "automatic_reparent_unauthorized": True,
        "runtime_activation_unauthorized": True,
        "android_changes_unauthorized": True,
    }

    summary_core = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "AUDITED_NOT_AUTHORIZED"
            if all(checks.values())
            else "AUDIT_FAILED"
        ),
        "healthy": all(checks.values()),
        "authorized": False,
        "database_writes_attempted": False,
        "duplicate_village": {
            "lgd_code": DUPLICATE_LGD_CODE,
            "row_count": len(duplicate_rows),
            "rows": duplicate_rows,
            "hierarchy_conflict":
                len(distinct_hierarchies) > 1,
            "foreign_key_references":
                reference_counts,
            "project_geography_scope_references":
                project_scope_rows,
            "climate_mapping_code_references":
                climate_code_references,
        },
        "chandigarh_gap": {
            "state_lgd_code": CHANDIGARH_LGD_CODE,
            "canonical_state_rows":
                chandigarh_states,
            "active_hierarchy_counts":
                chandigarh_hierarchy,
            "review_row_count":
                len(chandigarh_review_rows),
            "review_candidate_ids":
                sorted(chandigarh_candidate_ids),
            "review_source_feature_ids":
                sorted(chandigarh_source_ids),
            "legacy_rows_sha256":
                sha256(args.legacy_rows),
        },
        "database_before": before,
        "database_after": after,
        "checks": checks,
        "policy": {
            "canonical_insert_authorized": False,
            "canonical_merge_authorized": False,
            "canonical_reparent_authorized": False,
            "reference_rewrite_authorized": False,
            "boundary_candidate_changes_authorized":
                False,
            "runtime_activation_authorized": False,
            "project_scope_changes_authorized": False,
            "android_changes_authorized": False,
        },
        "recommended_next_actions": [
            (
                "Determine the authoritative hierarchy for "
                "both 476380 rows before selecting any "
                "survivor."
            ),
            (
                "Review every ID-based and code-based "
                "reference before designing a merge."
            ),
            (
                "Obtain authoritative Chandigarh state, "
                "district, block, and village hierarchy "
                "evidence before additive import planning."
            ),
            (
                "Keep all 12 Chandigarh boundary rows held "
                "until canonical hierarchy exists."
            ),
        ],
    }

    checksum = hashlib.sha256(
        json.dumps(
            summary_core,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    summary = {
        **summary_core,
        "summary_checksum": checksum,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )

    if not summary["healthy"]:
        raise SystemExit(
            "CANONICAL IDENTITY GAP AUDIT FAILED"
        )

    print(
        "CANONICAL IDENTITY GAP AUDIT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
