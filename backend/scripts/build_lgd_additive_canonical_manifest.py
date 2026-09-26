#!/usr/bin/env python3
"""Build a deterministic additive canonical LGD manifest.

Database behavior: read-only. No authorization is granted by this script.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
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
    canonical_checksum,
    normalize_code,
    sha256_file,
)

SCHEMA_VERSION = "lgd_additive_canonical_manifest.v3"
PROPOSAL_SCHEMA_VERSION = "lgd_additive_canonical_proposal.v3"
VERSION = "v1.0"

EXPECTED = {
    "states": 8,
    "districts": 1,
    "subdistricts": 5,
    "villages": 24_564,
    "held_reparent": 1_269,
}

CAMPAIGN_CREATED_AT = "2026-09-25T19:05:52.787095+05:30"

# Stable fallback namespace for a clean pre-apply database.
NAMESPACE = uuid.UUID(
    "b9d48ba7-965c-52e0-a224-c847d9b23e4b"
)


def deterministic_id(kind: str, *parts: str) -> str:
    label = ":".join((
        "farmint",
        "lgd-priority-state-additive-v3",
        kind,
        *parts,
    ))
    return str(uuid.uuid5(NAMESPACE, label))


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONL_OBJECT_REQUIRED:{path}:{number}"
                )
            rows.append(value)
    return rows


def db_snapshot(database_url: str) -> dict[str, Any]:
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )
    with engine.connect() as connection:
        states = [
            dict(row)
            for row in connection.execute(text("""
                select
                  id::text,
                  lgd_code::text,
                  canonical_name,
                  is_active
                from geography_states
            """)).mappings()
        ]
        districts = [
            dict(row)
            for row in connection.execute(text("""
                select
                  district.id::text,
                  district.lgd_code::text,
                  district.canonical_name,
                  district.census_name,
                  district.aliases,
                  district.version,
                  district.is_active,
                  district.created_at,
                  state.lgd_code::text as state_code
                from geography_districts district
                join geography_states state
                  on state.id = district.state_id
            """)).mappings()
        ]
        blocks = [
            dict(row)
            for row in connection.execute(text("""
                select
                  block.id::text,
                  block.lgd_code::text,
                  block.canonical_name,
                  block.aliases,
                  block.version,
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
            """)).mappings()
        ]
        villages = [
            dict(row)
            for row in connection.execute(text("""
                select
                  village.id::text,
                  village.lgd_code::text,
                  village.canonical_name,
                  village.census_name,
                  village.census_village_code,
                  village.pin_codes,
                  village.latitude,
                  village.longitude,
                  village.aliases,
                  village.version,
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
            """)).mappings()
        ]

    return {
        "states": states,
        "districts": districts,
        "blocks": blocks,
        "villages": villages,
    }


def iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def one(
    rows: list[dict[str, Any]],
    label: str,
) -> dict[str, Any] | None:
    if len(rows) > 1:
        raise ValueError(f"MULTIPLE_DATABASE_MATCHES:{label}")
    return rows[0] if rows else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--selection",
        type=Path,
        default=(
            DEFAULT_OUTPUT_DIR
            / "lgd_additive_canonical_final_selection_v2.json"
        ),
    )
    parser.add_argument(
        "--rows",
        type=Path,
        default=(
            DEFAULT_OUTPUT_DIR
            / "lgd_additive_canonical_final_rows_v2.jsonl"
        ),
    )
    parser.add_argument(
        "--held",
        type=Path,
        default=(
            DEFAULT_OUTPUT_DIR
            / "lgd_additive_canonical_reparent_held_rows_v2.jsonl"
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
        selection = load_json(args.selection)
        rows = load_jsonl(args.rows)
        held = load_jsonl(args.held)

        if not selection.get("healthy"):
            raise ValueError("SELECTION_NOT_HEALTHY")
        if len(rows) != EXPECTED["villages"]:
            raise ValueError(
                f"VILLAGE_COUNT_MISMATCH:{len(rows)}"
            )
        if len(held) != EXPECTED["held_reparent"]:
            raise ValueError(
                f"HELD_COUNT_MISMATCH:{len(held)}"
            )

        database = db_snapshot(args.database_url)

        states = {
            normalize_code(row["lgd_code"]): row
            for row in database["states"]
            if row["is_active"]
        }

        db_districts = {}
        for row in database["districts"]:
            key = (
                normalize_code(row["state_code"]),
                normalize_code(row["lgd_code"]),
            )
            db_districts.setdefault(key, []).append(row)

        db_blocks = {}
        for row in database["blocks"]:
            key = (
                normalize_code(row["state_code"]),
                normalize_code(row["district_code"]),
                normalize_code(row["lgd_code"]),
            )
            db_blocks.setdefault(key, []).append(row)

        db_villages = {}
        for row in database["villages"]:
            key = (
                normalize_code(row["state_code"]),
                normalize_code(row["lgd_code"]),
            )
            db_villages.setdefault(key, []).append(row)

        district_inserts = []
        district_ids = {}

        for source in selection["required_districts"]:
            state_code = normalize_code(
                source["state_code"]
            )
            district_code = normalize_code(
                source["district_code"]
            )
            existing = one(
                [
                    row
                    for row in db_districts.get(
                        (state_code, district_code),
                        [],
                    )
                    if (
                        row["is_active"]
                        and iso(row["created_at"])
                        == CAMPAIGN_CREATED_AT
                    )
                ],
                f"district:{state_code}:{district_code}",
            )
            row_id = (
                existing["id"]
                if existing
                else deterministic_id(
                    "district",
                    state_code,
                    district_code,
                )
            )
            district_ids[
                (state_code, district_code)
            ] = row_id
            district_inserts.append({
                "id": row_id,
                "lgd_code": district_code,
                "state_lgd_code": state_code,
                "canonical_name":
                    source["district_name"],
                "census_name": None,
                "aliases": [],
                "version": VERSION,
                "is_active": True,
            })

        subdistrict_inserts = []
        block_ids = {}

        for source in selection["required_subdistricts"]:
            state_code = normalize_code(
                source["state_code"]
            )
            district_code = normalize_code(
                source["district_code"]
            )
            block_code = normalize_code(
                source["subdistrict_code"]
            )
            existing = one(
                [
                    row
                    for row in db_blocks.get(
                        (
                            state_code,
                            district_code,
                            block_code,
                        ),
                        [],
                    )
                    if (
                        row["is_active"]
                        and iso(row["created_at"])
                        == CAMPAIGN_CREATED_AT
                    )
                ],
                "subdistrict:"
                f"{state_code}:{district_code}:{block_code}",
            )
            row_id = (
                existing["id"]
                if existing
                else deterministic_id(
                    "subdistrict",
                    state_code,
                    district_code,
                    block_code,
                )
            )
            block_ids[
                (state_code, district_code, block_code)
            ] = row_id
            subdistrict_inserts.append({
                "id": row_id,
                "lgd_code": block_code,
                "district_lgd_code": district_code,
                "state_lgd_code": state_code,
                "canonical_name":
                    source["subdistrict_name"],
                "aliases": [],
                "version": VERSION,
                "is_active": True,
            })

        village_inserts = []

        for source in rows:
            state_code = normalize_code(
                source["state_code"]
            )
            district_code = normalize_code(
                source["authoritative_district_code"]
            )
            block_code = normalize_code(
                source["authoritative_subdistrict_code"]
            )
            village_code = normalize_code(
                source["village_code"]
            )

            state = states.get(state_code)
            if state is None:
                raise ValueError(
                    f"ACTIVE_STATE_NOT_FOUND:{state_code}"
                )

            district = one(
                [
                    row
                    for row in db_districts.get(
                        (state_code, district_code),
                        [],
                    )
                    if row["is_active"]
                ],
                f"district-parent:{state_code}:{district_code}",
            )
            district_id = (
                district["id"]
                if district
                else district_ids.get(
                    (state_code, district_code)
                )
            )
            if not district_id:
                raise ValueError(
                    "DISTRICT_PARENT_NOT_RESOLVED:"
                    f"{state_code}:{district_code}"
                )

            block = one(
                [
                    row
                    for row in db_blocks.get(
                        (
                            state_code,
                            district_code,
                            block_code,
                        ),
                        [],
                    )
                    if row["is_active"]
                ],
                "block-parent:"
                f"{state_code}:{district_code}:{block_code}",
            )
            block_id = (
                block["id"]
                if block
                else block_ids.get((
                    state_code,
                    district_code,
                    block_code,
                ))
            )
            if not block_id:
                raise ValueError(
                    "BLOCK_PARENT_NOT_RESOLVED:"
                    f"{state_code}:{district_code}:"
                    f"{block_code}"
                )

            existing = one(
                [
                    row
                    for row in db_villages.get(
                        (state_code, village_code),
                        [],
                    )
                    if (
                        row["is_active"]
                        and iso(row["created_at"])
                        == CAMPAIGN_CREATED_AT
                    )
                ],
                f"village:{state_code}:{village_code}",
            )

            village_id = (
                existing["id"]
                if existing
                else deterministic_id(
                    "village",
                    state_code,
                    village_code,
                )
            )

            manifest_row = {
                "id": village_id,
                "lgd_code": village_code,
                "state_lgd_code": state_code,
                "district_lgd_code": district_code,
                "subdistrict_lgd_code": block_code,
                "district_id": district_id,
                "block_id": block_id,
                "canonical_name":
                    source["village_name"],
                "census_name": None,
                "census_village_code":
                    source["village_census_2011_code"],
                "pin_codes": [],
                "latitude": None,
                "longitude": None,
                "aliases": [],
                "version": VERSION,
                "is_active": True,
                "source_update_date":
                    source["data_gov_update_date"],
                "final_additive_disposition":
                    source[
                        "final_additive_disposition"
                    ],
            }
            manifest_row["row_checksum"] = (
                canonical_checksum(manifest_row)
            )
            village_inserts.append(manifest_row)

        district_inserts.sort(
            key=lambda row: (
                int(row["state_lgd_code"]),
                int(row["lgd_code"]),
            )
        )
        subdistrict_inserts.sort(
            key=lambda row: (
                int(row["state_lgd_code"]),
                int(row["district_lgd_code"]),
                int(row["lgd_code"]),
            )
        )
        village_inserts.sort(
            key=lambda row: (
                int(row["state_lgd_code"]),
                int(row["lgd_code"]),
            )
        )

        ordered_rows_hash = canonical_checksum([
            row["row_checksum"]
            for row in village_inserts
        ])

        checks = {
            "selection_healthy":
                selection["healthy"] is True,
            "state_count":
                len({
                    row["state_lgd_code"]
                    for row in village_inserts
                }) == EXPECTED["states"],
            "district_insert_count":
                len(district_inserts)
                == EXPECTED["districts"],
            "subdistrict_insert_count":
                len(subdistrict_inserts)
                == EXPECTED["subdistricts"],
            "village_insert_count":
                len(village_inserts)
                == EXPECTED["villages"],
            "held_reparent_count":
                len(held)
                == EXPECTED["held_reparent"],
            "village_ids_unique":
                len({
                    row["id"]
                    for row in village_inserts
                }) == len(village_inserts),
            "village_codes_unique":
                len({
                    row["lgd_code"]
                    for row in village_inserts
                }) == len(village_inserts),
            "all_versions_v1_0":
                all(
                    row["version"] == VERSION
                    for row in (
                        district_inserts
                        + subdistrict_inserts
                        + village_inserts
                    )
                ),
            "no_database_writes": True,
            "not_authorized": True,
        }

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "MANIFESTED_NOT_AUTHORIZED",
            "authorized": False,
            "database_writes_attempted": False,
            "healthy": all(checks.values()),
            "checks": checks,
            "version_contract": {
                "value": VERSION,
                "maximum_length": 10,
            },
            "source_pins": {
                args.selection.name:
                    sha256_file(args.selection),
                args.rows.name:
                    sha256_file(args.rows),
                args.held.name:
                    sha256_file(args.held),
            },
            "state_count": EXPECTED["states"],
            "district_insert_count":
                len(district_inserts),
            "subdistrict_insert_count":
                len(subdistrict_inserts),
            "village_insert_count":
                len(village_inserts),
            "held_reparent_count": len(held),
            "counts_by_state_lgd_code": dict(
                sorted(Counter(
                    row["state_lgd_code"]
                    for row in village_inserts
                ).items())
            ),
            "counts_by_final_disposition": dict(
                sorted(Counter(
                    row["final_additive_disposition"]
                    for row in village_inserts
                ).items())
            ),
            "ordered_row_manifest_sha256":
                ordered_rows_hash,
            "district_inserts": district_inserts,
            "subdistrict_inserts":
                subdistrict_inserts,
            "village_inserts": village_inserts,
        }
        manifest["manifest_checksum"] = (
            canonical_checksum(manifest)
        )

        args.output.mkdir(
            parents=True,
            exist_ok=True,
        )
        manifest_path = (
            args.output
            / "lgd_additive_canonical_manifest_v3.json"
        )
        atomic_write_json(manifest_path, manifest)

        proposal = {
            "schema_version":
                PROPOSAL_SCHEMA_VERSION,
            "status": "PROPOSED_NOT_AUTHORIZED",
            "authorized": False,
            "database_writes_attempted": False,
            "healthy": manifest["healthy"],
            "manifest_checksum":
                manifest["manifest_checksum"],
            "manifest_file_sha256":
                sha256_file(manifest_path),
            "ordered_row_manifest_sha256":
                ordered_rows_hash,
            "district_insert_count":
                len(district_inserts),
            "subdistrict_insert_count":
                len(subdistrict_inserts),
            "village_insert_count":
                len(village_inserts),
            "held_reparent_count": len(held),
            "permissions": {
                "canonical_insert_allowed": False,
                "canonical_update_allowed": False,
                "canonical_reparent_allowed": False,
                "canonical_delete_allowed": False,
                "android_change_allowed": False,
                "pin_link_write_allowed": False,
                "project_match_write_allowed": False,
                "nwdp_runtime_write_allowed": False,
            },
        }
        proposal["proposal_checksum"] = (
            canonical_checksum(proposal)
        )

        proposal_path = (
            args.output
            / "lgd_additive_canonical_proposal_v3.json"
        )
        atomic_write_json(proposal_path, proposal)

        result = {
            "healthy": manifest["healthy"],
            "authorized": False,
            "database_writes_attempted": False,
            "manifest_checksum":
                manifest["manifest_checksum"],
            "manifest_file_sha256":
                sha256_file(manifest_path),
            "proposal_checksum":
                proposal["proposal_checksum"],
            "proposal_file_sha256":
                sha256_file(proposal_path),
            "ordered_row_manifest_sha256":
                ordered_rows_hash,
            "district_insert_count":
                len(district_inserts),
            "subdistrict_insert_count":
                len(subdistrict_inserts),
            "village_insert_count":
                len(village_inserts),
            "held_reparent_count": len(held),
        }
        print(json.dumps(
            result,
            indent=2,
            sort_keys=True,
        ))
        return 0 if result["healthy"] else 1

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
