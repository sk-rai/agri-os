#!/usr/bin/env python3
"""Reproduce the priority-state additive canonical LGD selection.

Database behavior: read-only.

The selector works both before and after the completed import. Rows are in
campaign scope when they are absent from canonical geography or belong to the
exact completed import batch identified by its pinned creation timestamp.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
SCRIPT_DIR = Path(__file__).resolve().parent

for path in (BACKEND, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.config import settings
from lgd_priority_state_common import (
    DEFAULT_OUTPUT_DIR,
    atomic_write_json,
    atomic_write_jsonl,
    canonical_checksum,
    load_authoritative_hierarchy,
    load_current_villages,
    normalize_code,
    sha256_file,
)

SCHEMA_VERSION = "lgd_additive_canonical_final_selection.v2"

EXPECTED = {
    "selected": 24_564,
    "held_reparent": 1_269,
    "district_inserts": 1,
    "subdistrict_inserts": 5,
}

# This timestamp identifies exactly the 24,564 rows inserted by the completed
# authorized transaction. It makes post-apply reruns equivalent to pre-apply
# selection without treating unrelated canonical rows as campaign-owned.
COMPLETED_IMPORT_CREATED_AT = (
    "2026-09-25T19:05:52.787095+05:30"
)


def db_rows(connection, sql: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(text(sql)).mappings()
    ]


def load_database(database_url: str) -> dict[str, Any]:
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    with engine.connect() as connection:
        states = db_rows(
            connection,
            """
            select
              id::text,
              lgd_code::text,
              canonical_name,
              is_active
            from geography_states
            """,
        )

        districts = db_rows(
            connection,
            """
            select
              district.id::text,
              district.lgd_code::text,
              district.canonical_name,
              district.is_active,
              district.created_at,
              state.lgd_code::text as state_code
            from geography_districts district
            join geography_states state
              on state.id = district.state_id
            """,
        )

        blocks = db_rows(
            connection,
            """
            select
              block.id::text,
              block.lgd_code::text,
              block.canonical_name,
              block.is_active,
              block.created_at,
              district.id::text as district_id,
              district.lgd_code::text as district_code,
              state.lgd_code::text as state_code
            from geography_blocks block
            join geography_districts district
              on district.id = block.district_id
            join geography_states state
              on state.id = district.state_id
            """,
        )

        villages = db_rows(
            connection,
            """
            select
              village.id::text,
              village.lgd_code::text,
              village.canonical_name,
              village.census_village_code,
              village.is_active,
              village.created_at,
              village.block_id::text,
              village.district_id::text,
              block.lgd_code::text as block_code,
              district.lgd_code::text as district_code,
              state.lgd_code::text as state_code
            from geography_villages village
            join geography_blocks block
              on block.id = village.block_id
            join geography_districts district
              on district.id = village.district_id
            join geography_states state
              on state.id = district.state_id
            """,
        )

    return {
        "states": states,
        "districts": districts,
        "blocks": blocks,
        "villages": villages,
    }


def timestamp(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def index_by_code(
    rows: list[dict[str, Any]],
    column: str = "lgd_code",
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(
            normalize_code(row[column]),
            [],
        ).append(row)
    return result


def active(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if bool(row["is_active"])
    ]


def exact_district(
    rows: list[dict[str, Any]],
    state_code: str,
) -> list[dict[str, Any]]:
    return [
        row for row in active(rows)
        if normalize_code(row["state_code"]) == state_code
    ]


def exact_block(
    rows: list[dict[str, Any]],
    state_code: str,
    district_code: str,
) -> list[dict[str, Any]]:
    return [
        row for row in active(rows)
        if (
            normalize_code(row["state_code"]) == state_code
            and normalize_code(row["district_code"])
            == district_code
        )
    ]


def is_campaign_village(row: dict[str, Any]) -> bool:
    return timestamp(row["created_at"]) == (
        COMPLETED_IMPORT_CREATED_AT
    )


def build(args: argparse.Namespace) -> dict[str, Any]:
    source_rows, village_pins = load_current_villages(
        args.raw_villages
    )
    authoritative_districts, authoritative_subdistricts, hierarchy_pins = (
        load_authoritative_hierarchy(
            args.raw_hierarchy
        )
    )
    database = load_database(args.database_url)

    districts_by_code = index_by_code(
        database["districts"]
    )
    blocks_by_code = index_by_code(
        database["blocks"]
    )
    villages_by_code = index_by_code(
        database["villages"]
    )

    selected: list[dict[str, Any]] = []
    held_reparent: list[dict[str, Any]] = []
    held_structural: list[dict[str, Any]] = []

    required_districts: dict[str, dict[str, str]] = {}
    required_subdistricts: dict[str, dict[str, str]] = {}

    for source in source_rows:
        state_code = source["state_code"]
        village_code = source["village_code"]

        canonical_villages = active(
            villages_by_code.get(village_code, [])
        )
        campaign_villages = [
            row for row in canonical_villages
            if is_campaign_village(row)
        ]

        # Pre-apply: no canonical matches.
        # Post-apply: exactly one campaign-owned canonical match.
        if canonical_villages and not campaign_villages:
            continue

        if len(campaign_villages) > 1:
            raise ValueError(
                "DUPLICATE_CAMPAIGN_VILLAGE:"
                f"{state_code}:{village_code}"
            )

        authoritative_subdistrict = (
            authoritative_subdistricts.get(
                source["subdistrict_code"]
            )
        )
        if (
            authoritative_subdistrict is None
            or authoritative_subdistrict["state_code"]
            != state_code
        ):
            held_structural.append({
                **source,
                "final_disposition":
                    "HELD_AUTHORITATIVE_SUBDISTRICT_ABSENT",
            })
            continue

        authoritative_district_code = (
            authoritative_subdistrict["district_code"]
        )
        authoritative_district = (
            authoritative_districts.get(
                authoritative_district_code
            )
        )

        if (
            authoritative_district is None
            or authoritative_district["state_code"]
            != state_code
        ):
            held_structural.append({
                **source,
                "final_disposition":
                    "HELD_AUTHORITATIVE_DISTRICT_ABSENT",
            })
            continue

        # Reconstruct the pre-apply hierarchy. Rows created by the completed
        # campaign are outputs of this selection, not pre-existing parents.
        district_matches = [
            row
            for row in exact_district(
                districts_by_code.get(
                    authoritative_district_code,
                    [],
                ),
                state_code,
            )
            if not is_campaign_village(row)
        ]

        block_code = authoritative_subdistrict[
            "subdistrict_code"
        ]
        all_block_matches = [
            row
            for row in active(
                blocks_by_code.get(block_code, [])
            )
            if not is_campaign_village(row)
        ]
        exact_block_matches = exact_block(
            all_block_matches,
            state_code,
            authoritative_district_code,
        )

        # Existing duplicate block codes are not expanded by this campaign.
        if len(all_block_matches) > 1:
            held_structural.append({
                **source,
                "authoritative_district_code":
                    authoritative_district_code,
                "authoritative_subdistrict_code":
                    block_code,
                "final_disposition":
                    "HELD_OBSOLETE_DUPLICATE_SUBDISTRICT_PRESENT",
            })
            continue

        # Existing block under another current district. If the authoritative
        # district already exists, this needs canonical reparent review and was
        # excluded before the final 25,833-row partition.
        if all_block_matches and not exact_block_matches:
            row = {
                **source,
                "authoritative_district_code":
                    authoritative_district_code,
                "authoritative_district_name":
                    authoritative_district["district_name"],
                "authoritative_subdistrict_code":
                    block_code,
                "authoritative_subdistrict_name":
                    authoritative_subdistrict[
                        "subdistrict_name"
                    ],
            }

            if district_matches:
                row["final_disposition"] = (
                    "HELD_SUBDISTRICT_REPARENT_REQUIRED"
                )
                held_structural.append(row)
            else:
                row["final_disposition"] = (
                    "HELD_CANONICAL_SUBDISTRICT_REPARENT_REQUIRED"
                )
                held_reparent.append(row)
            continue

        if not district_matches:
            required_districts[
                authoritative_district_code
            ] = authoritative_district

        if not exact_block_matches:
            required_subdistricts[
                block_code
            ] = authoritative_subdistrict

        if exact_block_matches:
            disposition = (
                "ADDITIVE_READY_EXISTING_AUTHORITATIVE_PARENT"
            )
        elif district_matches:
            disposition = (
                "ADDITIVE_READY_AFTER_SUBDISTRICT_INSERT"
            )
        else:
            disposition = (
                "ADDITIVE_READY_AFTER_DISTRICT_AND_"
                "SUBDISTRICT_INSERT"
            )

        selected.append({
            **source,
            "authoritative_district_code":
                authoritative_district_code,
            "authoritative_district_name":
                authoritative_district["district_name"],
            "authoritative_district_census_2011_code":
                authoritative_district[
                    "district_census_2011_code"
                ],
            "authoritative_subdistrict_code":
                block_code,
            "authoritative_subdistrict_name":
                authoritative_subdistrict[
                    "subdistrict_name"
                ],
            "authoritative_subdistrict_census_2011_code":
                authoritative_subdistrict[
                    "subdistrict_census_2011_code"
                ],
            "final_additive_disposition": disposition,
        })

    sort_key = lambda row: (
        int(row["state_code"]),
        int(row["village_code"]),
    )
    selected.sort(key=sort_key)
    held_reparent.sort(key=sort_key)
    held_structural.sort(key=sort_key)

    output = args.output.resolve()
    selected_path = (
        output
        / "lgd_additive_canonical_final_rows_v2.jsonl"
    )
    held_path = (
        output
        / "lgd_additive_canonical_reparent_held_rows_v2.jsonl"
    )
    structural_path = (
        output
        / "lgd_additive_canonical_structural_held_rows_v2.jsonl"
    )

    atomic_write_jsonl(selected_path, selected)
    atomic_write_jsonl(held_path, held_reparent)
    atomic_write_jsonl(
        structural_path,
        held_structural,
    )

    required_district_list = sorted(
        required_districts.values(),
        key=lambda row: int(row["district_code"]),
    )
    required_subdistrict_list = sorted(
        required_subdistricts.values(),
        key=lambda row: int(row["subdistrict_code"]),
    )

    selected_identities = {
        (row["state_code"], row["village_code"])
        for row in selected
    }
    held_identities = {
        (row["state_code"], row["village_code"])
        for row in held_reparent
    }

    checks = {
        "selected_count_exact":
            len(selected) == EXPECTED["selected"],
        "held_reparent_count_exact":
            len(held_reparent)
            == EXPECTED["held_reparent"],
        "district_insert_count_exact":
            len(required_district_list)
            == EXPECTED["district_inserts"],
        "subdistrict_insert_count_exact":
            len(required_subdistrict_list)
            == EXPECTED["subdistrict_inserts"],
        "selected_identity_unique":
            len(selected_identities) == len(selected),
        "held_identity_unique":
            len(held_identities) == len(held_reparent),
        "selected_and_held_disjoint":
            selected_identities.isdisjoint(
                held_identities
            ),
        "no_database_writes": True,
        "not_authorized": True,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "SELECTED_NOT_AUTHORIZED",
        "authorized": False,
        "database_writes_attempted": False,
        "healthy": all(checks.values()),
        "checks": checks,
        "current_master_row_count":
            len(source_rows),
        "selected_village_count":
            len(selected),
        "held_reparent_count":
            len(held_reparent),
        "structural_held_count":
            len(held_structural),
        "counts_by_final_disposition": dict(
            sorted(Counter(
                row["final_additive_disposition"]
                for row in selected
            ).items())
        ),
        "counts_by_state": dict(
            sorted(Counter(
                row["state_name"]
                for row in selected
            ).items())
        ),
        "required_districts":
            required_district_list,
        "required_subdistricts":
            required_subdistrict_list,
        "source_pins": {
            **village_pins,
            **hierarchy_pins,
        },
        "completed_import_created_at":
            COMPLETED_IMPORT_CREATED_AT,
        "selected_rows":
            str(selected_path),
        "selected_rows_sha256":
            sha256_file(selected_path),
        "held_rows":
            str(held_path),
        "held_rows_sha256":
            sha256_file(held_path),
        "structural_held_rows":
            str(structural_path),
        "structural_held_rows_sha256":
            sha256_file(structural_path),
    }
    report["summary_checksum"] = canonical_checksum(
        report
    )

    summary_path = (
        output
        / "lgd_additive_canonical_final_selection_v2.json"
    )
    atomic_write_json(summary_path, report)
    print(json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))

    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-villages",
        type=Path,
        default=(
            ROOT
            / "data/raw/lgd_national_villages"
            / "20260925/downloads"
        ),
    )
    parser.add_argument(
        "--raw-hierarchy",
        type=Path,
        default=(
            ROOT
            / "data/raw/lgd_national_geography"
            / "20260925/downloads"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--database-url",
        default=settings.DATABASE_URL,
    )
    args = parser.parse_args()

    try:
        report = build(args)
        return 0 if report["healthy"] else 1
    except Exception as exc:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "healthy": False,
            "fail_closed": True,
            "authorized": False,
            "database_writes_attempted": False,
            "error": f"{type(exc).__name__}:{exc}",
        }, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
