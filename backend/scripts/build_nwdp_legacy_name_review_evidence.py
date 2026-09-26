#!/usr/bin/env python3
"""Build deterministic lexical evidence for legacy NWDP name-review rows."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from lgd_priority_state_common import (
    DEFAULT_OUTPUT_DIR,
    atomic_write_json,
    atomic_write_jsonl,
    canonical_checksum,
    sha256_file,
)


SCHEMA_VERSION = "nwdp_legacy_name_review_evidence.v1"
EXPECTED_INPUT_SHA256 = (
    "71513ec165ea100a5412688a1ac876a122eafd722bc71a62d89d1edf4adba2d0"
)
EXPECTED_INPUT_ROWS = 10_052
EXPECTED_NAME_REVIEW_ROWS = 7_540

ADMINISTRATIVE_TOKENS = {
    "ct",
    "census",
    "town",
    "village",
    "vill",
    "rural",
    "urban",
}

PARENTHETICAL_PATTERN = re.compile(r"\([^)]*\)")
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")
TRAILING_NUMBER_PATTERN = re.compile(r"(?:\s+\d+)+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            DEFAULT_OUTPUT_DIR
            / "nwdp_legacy_held_review_queue_rows.jsonl"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser.parse_args()


def text(value: Any) -> str:
    return "" if value is None else str(value)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue

            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"NON_OBJECT_JSONL_ROW:{line_number}")

            rows.append(value)

    return rows


def ascii_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", text(value))
    return normalized.encode("ascii", "ignore").decode("ascii")


def normalized_name(value: Any) -> str:
    value_text = ascii_text(value).lower()
    return " ".join(
        part
        for part in NON_ALNUM_PATTERN.sub(" ", value_text).split()
        if part
    )


def core_name(value: Any) -> str:
    value_text = ascii_text(value).lower()
    value_text = PARENTHETICAL_PATTERN.sub(" ", value_text)
    value_text = NON_ALNUM_PATTERN.sub(" ", value_text)
    value_text = TRAILING_NUMBER_PATTERN.sub("", value_text)

    tokens = [
        token
        for token in value_text.split()
        if token and token not in ADMINISTRATIVE_TOKENS
    ]
    return " ".join(tokens)


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    if len(left) > len(right):
        left, right = right, left

    previous = list(range(len(left) + 1))

    for right_index, right_char in enumerate(right, 1):
        current = [right_index]

        for left_index, left_char in enumerate(left, 1):
            insertion = current[left_index - 1] + 1
            deletion = previous[left_index] + 1
            substitution = (
                previous[left_index - 1]
                + (left_char != right_char)
            )
            current.append(min(insertion, deletion, substitution))

        previous = current

    return previous[-1]


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())

    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0

    return len(left_tokens & right_tokens) / len(
        left_tokens | right_tokens
    )


def evidence_band(
    source_normalized: str,
    canonical_normalized: str,
    source_core: str,
    canonical_core: str,
    edit_distance: int,
    similarity: float,
    jaccard: float,
) -> str:
    if source_core and source_core == canonical_core:
        return "ADMINISTRATIVE_QUALIFIER_ONLY"

    if (
        source_core
        and canonical_core
        and sorted(source_core.split())
        == sorted(canonical_core.split())
    ):
        return "TOKEN_ORDER_ONLY"

    maximum_length = max(len(source_core), len(canonical_core), 1)
    normalized_edit_distance = edit_distance / maximum_length

    if (
        similarity >= 0.90
        or normalized_edit_distance <= 0.12
        or (
            edit_distance == 1
            and maximum_length >= 5
        )
    ):
        return "HIGH_LEXICAL_SIMILARITY"

    if similarity >= 0.75 or jaccard >= 0.67:
        return "MODERATE_LEXICAL_SIMILARITY"

    return "LOW_LEXICAL_SIMILARITY"


def output_sort_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        text(row.get("evidence_band")),
        text(row.get("source_state")),
        text(row.get("source_district_code")),
        text(row.get("source_subdistrict_code")),
        text(row.get("source_village_code")),
        text(row.get("candidate_id")),
    )


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.is_file():
        raise ValueError(f"INPUT_NOT_FOUND:{input_path}")

    input_sha256 = sha256_file(input_path)
    all_rows = load_jsonl(input_path)

    selected_rows = [
        row
        for row in all_rows
        if row.get("review_queue") == "NAME_EQUIVALENCE_REVIEW"
    ]

    evidence_rows: list[dict[str, Any]] = []
    malformed_rows: list[str] = []

    for row in selected_rows:
        canonical_matches = row.get("canonical_matches")

        if (
            not isinstance(canonical_matches, list)
            or len(canonical_matches) != 1
            or not isinstance(canonical_matches[0], dict)
        ):
            malformed_rows.append(text(row.get("candidate_id")))
            continue

        canonical_match = canonical_matches[0]
        source_name = text(row.get("source_village_name"))
        canonical_name = text(
            canonical_match.get("village_name")
        )

        source_normalized = normalized_name(source_name)
        canonical_normalized = normalized_name(canonical_name)
        source_core = core_name(source_name)
        canonical_core = core_name(canonical_name)

        comparison_source = source_core or source_normalized
        comparison_canonical = (
            canonical_core or canonical_normalized
        )

        edit_distance = levenshtein_distance(
            comparison_source,
            comparison_canonical,
        )
        similarity = SequenceMatcher(
            None,
            comparison_source,
            comparison_canonical,
            autojunk=False,
        ).ratio()
        jaccard = token_jaccard(
            comparison_source,
            comparison_canonical,
        )

        band = evidence_band(
            source_normalized,
            canonical_normalized,
            source_core,
            canonical_core,
            edit_distance,
            similarity,
            jaccard,
        )

        evidence_rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "source_feature_id": row.get(
                    "source_feature_id"
                ),
                "source_state": row.get("source_state"),
                "source_district_code": row.get(
                    "source_district_code"
                ),
                "source_district_name": row.get(
                    "source_district_name"
                ),
                "source_subdistrict_code": row.get(
                    "source_subdistrict_code"
                ),
                "source_subdistrict_name": row.get(
                    "source_subdistrict_name"
                ),
                "source_village_code": row.get(
                    "source_village_code"
                ),
                "source_village_name": source_name,
                "canonical_village_id": canonical_match.get(
                    "village_id"
                ),
                "canonical_village_code": canonical_match.get(
                    "village_code"
                ),
                "canonical_village_name": canonical_name,
                "canonical_district_code": canonical_match.get(
                    "district_code"
                ),
                "canonical_district_name": canonical_match.get(
                    "district_name"
                ),
                "canonical_block_code": canonical_match.get(
                    "block_code"
                ),
                "canonical_block_name": canonical_match.get(
                    "block_name"
                ),
                "source_name_normalized": source_normalized,
                "canonical_name_normalized": (
                    canonical_normalized
                ),
                "source_name_core": source_core,
                "canonical_name_core": canonical_core,
                "levenshtein_distance": edit_distance,
                "sequence_similarity": round(
                    similarity,
                    6,
                ),
                "token_jaccard": round(jaccard, 6),
                "evidence_band": band,
                "review_required": True,
                "automatic_equivalence_authorized": False,
                "automatic_runtime_staging_authorized": False,
            }
        )

    evidence_rows.sort(key=output_sort_key)

    candidate_ids = [
        text(row.get("candidate_id"))
        for row in evidence_rows
    ]
    source_feature_ids = [
        text(row.get("source_feature_id"))
        for row in evidence_rows
    ]

    band_counts = Counter(
        text(row.get("evidence_band"))
        for row in evidence_rows
    )

    state_band_counts: dict[str, Counter[str]] = {}

    for row in evidence_rows:
        state = text(row.get("source_state"))
        state_band_counts.setdefault(state, Counter())[
            text(row.get("evidence_band"))
        ] += 1

    checks = {
        "input_sha256_pinned": (
            input_sha256 == EXPECTED_INPUT_SHA256
        ),
        "input_row_count_exact": (
            len(all_rows) == EXPECTED_INPUT_ROWS
        ),
        "name_review_row_count_exact": (
            len(selected_rows) == EXPECTED_NAME_REVIEW_ROWS
        ),
        "single_canonical_match_per_row": (
            not malformed_rows
            and len(evidence_rows) == len(selected_rows)
        ),
        "candidate_identity_unique": (
            len(candidate_ids) == len(set(candidate_ids))
            and all(candidate_ids)
        ),
        "source_feature_identity_unique": (
            len(source_feature_ids)
            == len(set(source_feature_ids))
            and all(source_feature_ids)
        ),
        "all_rows_require_review": all(
            row["review_required"] is True
            for row in evidence_rows
        ),
        "automatic_equivalence_disabled": all(
            row["automatic_equivalence_authorized"] is False
            for row in evidence_rows
        ),
        "automatic_runtime_staging_disabled": all(
            row["automatic_runtime_staging_authorized"] is False
            for row in evidence_rows
        ),
        "no_database_writes": True,
        "not_authorized": True,
    }

    healthy = all(checks.values())

    rows_path = (
        output_dir
        / "nwdp_legacy_name_review_evidence_rows.jsonl"
    )
    summary_path = (
        output_dir
        / "nwdp_legacy_name_review_evidence.json"
    )

    atomic_write_jsonl(rows_path, evidence_rows)
    rows_sha256 = sha256_file(rows_path)

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "EVIDENCE_BUILT_NOT_AUTHORIZED",
        "healthy": healthy,
        "database_writes_attempted": False,
        "checks": checks,
        "policy": {
            "automatic_equivalence_authorized": False,
            "candidate_updates_authorized": False,
            "runtime_staging_authorized": False,
            "runtime_activation_authorized": False,
            "project_matching_authorized": False,
            "canonical_changes_authorized": False,
        },
        "input": str(input_path),
        "input_sha256": input_sha256,
        "input_row_count": len(all_rows),
        "row_count": len(evidence_rows),
        "counts_by_evidence_band": dict(
            sorted(band_counts.items())
        ),
        "state_evidence_band_matrix": {
            state: dict(sorted(counts.items()))
            for state, counts
            in sorted(state_band_counts.items())
        },
        "malformed_candidate_ids": sorted(
            malformed_rows
        ),
        "rows": str(rows_path),
        "rows_sha256": rows_sha256,
    }

    summary["summary_checksum"] = canonical_checksum(summary)
    atomic_write_json(summary_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
