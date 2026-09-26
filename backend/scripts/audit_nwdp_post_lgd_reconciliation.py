#!/usr/bin/env python3
"""Rebuild post-LGD NWDP reconciliation and actionability evidence.

Database behavior: read-only.

This script does not authorize runtime staging, activation, candidate changes,
canonical reparenting, project matching, Android changes, or source writes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
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
    normalize_code,
    sha256_file,
)

SCHEMA_VERSION = (
    "nwdp_post_lgd_actionability_audit.v2"
)

DEFAULT_SOURCE = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260924-nwdp-no-canonical-village-audit-v1"
    / "nwdp_no_canonical_village_rows.jsonl"
)

EXPECTED = {
    "source_rows": 22_219,
    "resolved_same_district": 18_928,
    "resolved_other_district": 1_437,
    "still_absent": 1_854,
    "deterministic": 17_498,
    "name_review": 2_867,
    "canonical_reparent": 1_076,
    "absent_current_lgd": 400,
    "other_structural": 378,
}

# Only a terminal parenthesized numeric cadastral suffix is removable.
# Accepted examples: (147), (12-3), (25/27), and (86 ).
# Whitespace immediately after "(" is intentionally not accepted.
NUMERIC_SUFFIX = re.compile(
    r"\s*\(\d+(?:\s*[-/]\s*\d+)*\s*\)\s*$"
)


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


def normalized_name(value: Any) -> str:
    text_value = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )
    text_value = "".join(
        character
        for character in text_value
        if not unicodedata.combining(character)
    )
    return "".join(
        character
        for character in text_value.casefold()
        if character.isalnum()
    )


def without_numeric_suffix(value: Any) -> str:
    return NUMERIC_SUFFIX.sub(
        "",
        str(value or "").strip(),
    )


def name_disposition(
    source_name: str,
    canonical_name: str,
) -> str:
    if normalized_name(source_name) == normalized_name(
        canonical_name
    ):
        return "EXACT_OR_PUNCTUATION_MATCH"

    source_without_suffix = without_numeric_suffix(
        source_name
    )
    canonical_without_suffix = without_numeric_suffix(
        canonical_name
    )

    suffix_was_removed = (
        source_without_suffix != source_name.strip()
        or canonical_without_suffix
        != canonical_name.strip()
    )

    if (
        suffix_was_removed
        and normalized_name(source_without_suffix)
        == normalized_name(canonical_without_suffix)
    ):
        return "TRAILING_NUMERIC_SUFFIX_ONLY"

    return "NAME_MISMATCH_REVIEW_REQUIRED"


def database_villages(
    database_url: str,
) -> dict[str, list[dict[str, Any]]]:
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )
    with engine.connect() as connection:
        rows = [
            dict(row)
            for row in connection.execute(text("""
                select
                  village.id::text as village_id,
                  village.lgd_code::text as village_code,
                  village.canonical_name as village_name,
                  village.is_active as village_active,
                  block.id::text as block_id,
                  block.lgd_code::text as block_code,
                  block.canonical_name as block_name,
                  block.is_active as block_active,
                  district.id::text as district_id,
                  district.lgd_code::text as district_code,
                  district.canonical_name as district_name,
                  district.is_active as district_active,
                  state.id::text as state_id,
                  state.lgd_code::text as state_code,
                  state.canonical_name as state_name,
                  state.is_active as state_active
                from geography_villages village
                join geography_blocks block
                  on block.id = village.block_id
                join geography_districts district
                  on district.id = village.district_id
                join geography_states state
                  on state.id = district.state_id
                where village.is_active
            """)).mappings()
        ]

    indexed: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in rows:
        normalized = dict(row)
        for key in (
            "village_code",
            "block_code",
            "district_code",
            "state_code",
        ):
            normalized[key] = normalize_code(
                normalized[key]
            )
        indexed[normalized["village_code"]].append(
            normalized
        )

    return dict(indexed)


def identity_set(
    rows: list[dict[str, Any]],
) -> set[tuple[str, str]]:
    return {
        (
            normalize_code(row["state_code"]),
            normalize_code(row["village_code"]),
        )
        for row in rows
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
    )
    parser.add_argument(
        "--reparent-held",
        type=Path,
        default=(
            DEFAULT_OUTPUT_DIR
            / "lgd_additive_canonical_reparent_held_rows_v2.jsonl"
        ),
    )
    parser.add_argument(
        "--structural-held",
        type=Path,
        default=(
            DEFAULT_OUTPUT_DIR
            / "lgd_additive_canonical_structural_held_rows_v2.jsonl"
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
        all_source_rows = load_jsonl(args.source)
        source_rows = [
            row
            for row in all_source_rows
            if row.get("disposition")
            == "ABSENT_FROM_CANONICAL_GLOBALLY"
        ]
        reparent_held = load_jsonl(
            args.reparent_held
        )
        structural_held = load_jsonl(
            args.structural_held
        )

        if len(source_rows) != EXPECTED["source_rows"]:
            raise ValueError(
                "SOURCE_ROW_COUNT_MISMATCH:"
                f"{len(source_rows)}"
            )

        reparent_identities = identity_set(
            reparent_held
        )
        structural_identities = identity_set(
            structural_held
        )
        canonical = database_villages(
            args.database_url
        )

        output_rows: list[dict[str, Any]] = []

        for source in source_rows:
            state_code = normalize_code(
                source["expected_state_lgd_code"]
            )
            village_code = normalize_code(
                source["source_village_code"]
            )
            source_district_code = normalize_code(
                source["source_district_code"]
            )
            identity = (
                state_code,
                village_code,
            )

            matches = [
                row
                for row in canonical.get(
                    village_code,
                    [],
                )
                if row["state_code"] == state_code
            ]

            if len(matches) > 1:
                raise ValueError(
                    "DUPLICATE_ACTIVE_SAME_STATE_VILLAGE:"
                    f"{state_code}:{village_code}"
                )

            if matches:
                match = matches[0]
                if (
                    match["district_code"]
                    == source_district_code
                ):
                    resolution = (
                        "RESOLVED_SAME_EXPECTED_DISTRICT"
                    )
                else:
                    resolution = (
                        "RESOLVED_SAME_STATE_OTHER_DISTRICT"
                    )

                disposition = name_disposition(
                    source["source_village_name"],
                    match["village_name"],
                )

                if disposition in {
                    "EXACT_OR_PUNCTUATION_MATCH",
                    "TRAILING_NUMERIC_SUFFIX_ONLY",
                }:
                    actionability = (
                        "DETERMINISTIC_INACTIVE_"
                        "STAGING_CANDIDATE"
                    )
                else:
                    actionability = (
                        "NAME_REVIEW_REQUIRED"
                    )

                canonical_matches = [match]
            else:
                resolution = (
                    "STILL_ABSENT_FROM_CANONICAL_GLOBALLY"
                )
                disposition = None
                canonical_matches = []

                if identity in reparent_identities:
                    actionability = (
                        "CANONICAL_REPARENT_"
                        "REVIEW_REQUIRED"
                    )
                elif identity in structural_identities:
                    actionability = (
                        "OTHER_STRUCTURAL_REVIEW_REQUIRED"
                    )
                else:
                    actionability = (
                        "ABSENT_FROM_CURRENT_LGD_"
                        "REVIEW_REQUIRED"
                    )

            row = {
                "candidate_id":
                    source["candidate_id"],
                "source_feature_id":
                    source["source_feature_id"],
                "source_feature_index":
                    source["source_feature_index"],
                "source_state":
                    source["source_state"],
                "source_village_code":
                    village_code,
                "source_village_name":
                    source["source_village_name"],
                "source_district_code":
                    source_district_code,
                "expected_state_lgd_code":
                    state_code,
                "expected_district_id":
                    source["expected_district_id"],
                "post_import_disposition":
                    resolution,
                "nwdp_name_disposition":
                    disposition,
                "actionability":
                    actionability,
                "canonical_matches":
                    canonical_matches,
            }
            row["row_checksum"] = canonical_checksum(
                row
            )
            output_rows.append(row)

        output_rows.sort(
            key=lambda row: (
                int(row["expected_state_lgd_code"]),
                int(row["source_feature_index"]),
                row["candidate_id"],
            )
        )

        resolution_counts = Counter(
            row["post_import_disposition"]
            for row in output_rows
        )
        actionability_counts = Counter(
            row["actionability"]
            for row in output_rows
        )

        state_matrix: dict[
            str,
            Counter[str],
        ] = defaultdict(Counter)
        for row in output_rows:
            state_matrix[row["source_state"]][
                row["actionability"]
            ] += 1

        rows_path = (
            args.output
            / "nwdp_post_lgd_actionability_rows_v2.jsonl"
        )
        atomic_write_jsonl(
            rows_path,
            output_rows,
        )

        checks = {
            "source_row_count_exact":
                len(output_rows)
                == EXPECTED["source_rows"],
            "resolved_same_district_exact":
                resolution_counts[
                    "RESOLVED_SAME_EXPECTED_DISTRICT"
                ] == EXPECTED[
                    "resolved_same_district"
                ],
            "resolved_other_district_exact":
                resolution_counts[
                    "RESOLVED_SAME_STATE_OTHER_DISTRICT"
                ] == EXPECTED[
                    "resolved_other_district"
                ],
            "still_absent_exact":
                resolution_counts[
                    "STILL_ABSENT_FROM_CANONICAL_GLOBALLY"
                ] == EXPECTED["still_absent"],
            "deterministic_count_exact":
                actionability_counts[
                    "DETERMINISTIC_INACTIVE_STAGING_CANDIDATE"
                ] == EXPECTED["deterministic"],
            "name_review_count_exact":
                actionability_counts[
                    "NAME_REVIEW_REQUIRED"
                ] == EXPECTED["name_review"],
            "canonical_reparent_count_exact":
                actionability_counts[
                    "CANONICAL_REPARENT_REVIEW_REQUIRED"
                ] == EXPECTED["canonical_reparent"],
            "absent_current_lgd_count_exact":
                actionability_counts[
                    "ABSENT_FROM_CURRENT_LGD_REVIEW_REQUIRED"
                ] == EXPECTED["absent_current_lgd"],
            "other_structural_count_exact":
                actionability_counts[
                    "OTHER_STRUCTURAL_REVIEW_REQUIRED"
                ] == EXPECTED["other_structural"],
            "candidate_identity_unique":
                len({
                    row["candidate_id"]
                    for row in output_rows
                }) == len(output_rows),
            "source_feature_identity_unique":
                len({
                    row["source_feature_id"]
                    for row in output_rows
                }) == len(output_rows),
            "no_database_writes": True,
            "not_authorized": True,
        }

        report = {
            "schema_version": SCHEMA_VERSION,
            "status": "AUDITED_NOT_AUTHORIZED",
            "authorized": False,
            "database_writes_attempted": False,
            "healthy": all(checks.values()),
            "checks": checks,
            "row_count": len(output_rows),
            "counts_by_resolution": dict(
                sorted(resolution_counts.items())
            ),
            "counts_by_actionability": dict(
                sorted(actionability_counts.items())
            ),
            "state_actionability_matrix": {
                state: dict(sorted(counts.items()))
                for state, counts in sorted(
                    state_matrix.items()
                )
            },
            "policy": {
                "runtime_staging_authorized": False,
                "runtime_activation_authorized": False,
                "candidate_updates_authorized": False,
                "canonical_reparenting_authorized": False,
                "name_mismatch_auto_approval_authorized":
                    False,
                "project_matching_authorized": False,
                "android_changes_authorized": False,
            },
            "source_pins": {
                args.source.name:
                    sha256_file(args.source),
                args.reparent_held.name:
                    sha256_file(args.reparent_held),
                args.structural_held.name:
                    sha256_file(args.structural_held),
            },
            "ordered_row_manifest_sha256":
                canonical_checksum([
                    row["row_checksum"]
                    for row in output_rows
                ]),
            "rows": str(rows_path),
            "rows_sha256":
                sha256_file(rows_path),
        }
        report["summary_checksum"] = (
            canonical_checksum(report)
        )

        summary_path = (
            args.output
            / "nwdp_post_lgd_actionability_audit_v2.json"
        )
        atomic_write_json(summary_path, report)

        print(json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ))
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
