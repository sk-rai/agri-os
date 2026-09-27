#!/usr/bin/env python3
"""Build read-only evidence for legacy NWDP block-parent reviews."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "nwdp_legacy_block_parent_review_evidence.v1"
EXPECTED_INPUT_ROWS = 10_052
EXPECTED_SELECTED_ROWS = 2_272
INPUT_ROWS_SHA256 = (
    "71513ec165ea100a5412688a1ac876a122eafd722bc71a62d89d1edf4adba2d0"
)
SELECTED_QUEUE = "BLOCK_PARENT_REVIEW"
SELECTED_DISPOSITION = "CANONICAL_BLOCK_MISMATCH"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONL_OBJECT_REQUIRED:{path}:{line_number}"
                )
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.casefold()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(
        r"\b(ct|rural|urban|st|tehsil|tahsil|subdistrict|block)\b",
        " ",
        text,
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def tokens(value: str) -> set[str]:
    return {token for token in value.split() if token}


def classify(
    source_parent: str,
    canonical_parent: str,
) -> tuple[str, str]:
    source_tokens = tokens(source_parent)
    canonical_tokens = tokens(canonical_parent)
    similarity = SequenceMatcher(
        None,
        source_parent,
        canonical_parent,
    ).ratio()

    if source_parent and source_parent == canonical_parent:
        return (
            "B1_EXACT_NORMALIZED_PARENT_NAME",
            "VERIFY_CROSS_LEVEL_ADMINISTRATIVE_RELATIONSHIP",
        )

    if (
        source_tokens
        and canonical_tokens
        and source_tokens == canonical_tokens
    ):
        return (
            "B2_TOKEN_EQUIVALENT_PARENT_NAME",
            "VERIFY_CROSS_LEVEL_ADMINISTRATIVE_RELATIONSHIP",
        )

    if similarity >= 0.80:
        return (
            "B3_HIGH_PARENT_NAME_SIMILARITY",
            "VERIFY_PARENT_NAME_AND_CURRENT_LGD_HIERARCHY",
        )

    if source_tokens & canonical_tokens:
        return (
            "B4_PARTIAL_PARENT_TOKEN_OVERLAP",
            "RESEARCH_CURRENT_LGD_HIERARCHY",
        )

    return (
        "B5_DISTINCT_PARENT_NAMES",
        "RESEARCH_CURRENT_LGD_HIERARCHY",
    )


def stable_checksum(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def required(row: dict[str, Any], field: str) -> str:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"MISSING_{field.upper()}")
    return value


def build(
    input_path: Path,
    output_rows: Path,
) -> tuple[dict[str, Any], bool]:
    input_sha256 = sha256_file(input_path)
    input_rows = load_jsonl(input_path)

    selected = [
        row
        for row in input_rows
        if row.get("review_queue") == SELECTED_QUEUE
    ]

    pair_counts = Counter()
    prepared = []

    for source in selected:
        matches = source.get("canonical_matches")
        if not isinstance(matches, list) or len(matches) != 1:
            raise ValueError(
                "EXPECTED_ONE_CANONICAL_MATCH:"
                + required(source, "candidate_id")
            )

        canonical = matches[0]
        source_parent_normalized = normalize_name(
            source.get("source_subdistrict_name")
        )
        canonical_parent_normalized = normalize_name(
            canonical.get("block_name")
        )
        pair_key = (
            required(source, "source_state"),
            required(source, "normalized_source_district_code"),
            required(source, "normalized_source_subdistrict_code"),
            required(canonical, "block_code"),
        )
        pair_counts[pair_key] += 1
        prepared.append(
            (
                source,
                canonical,
                source_parent_normalized,
                canonical_parent_normalized,
                pair_key,
            )
        )

    output = []
    for (
        source,
        canonical,
        source_parent_normalized,
        canonical_parent_normalized,
        pair_key,
    ) in prepared:
        evidence_band, review_focus = classify(
            source_parent_normalized,
            canonical_parent_normalized,
        )
        source_tokens = tokens(source_parent_normalized)
        canonical_tokens = tokens(canonical_parent_normalized)
        union = source_tokens | canonical_tokens
        intersection = source_tokens & canonical_tokens

        output.append(
            {
                "automatic_action_authorized": False,
                "candidate_id": required(source, "candidate_id"),
                "canonical_block_active":
                    canonical.get("block_active") is True,
                "canonical_block_code":
                    required(canonical, "block_code"),
                "canonical_block_name":
                    required(canonical, "block_name"),
                "canonical_block_name_normalized":
                    canonical_parent_normalized,
                "canonical_district_code":
                    required(canonical, "district_code"),
                "canonical_district_name":
                    required(canonical, "district_name"),
                "canonical_state_code":
                    required(canonical, "state_code"),
                "canonical_state_name":
                    required(canonical, "state_name"),
                "canonical_village_code":
                    required(canonical, "village_code"),
                "canonical_village_id":
                    required(canonical, "village_id"),
                "canonical_village_name":
                    required(canonical, "village_name"),
                "evidence_band": evidence_band,
                "identifier_comparison":
                    "NOT_COMPARABLE_CROSS_LEVEL",
                "levenshtein_proxy_similarity": round(
                    SequenceMatcher(
                        None,
                        source_parent_normalized,
                        canonical_parent_normalized,
                    ).ratio(),
                    6,
                ),
                "pair_recurrence_count": pair_counts[pair_key],
                "review_decision": "",
                "review_evidence_basis": "",
                "review_evidence_reference": "",
                "review_focus": review_focus,
                "review_notes": "",
                "reviewer": "",
                "source_district_code":
                    required(source, "normalized_source_district_code"),
                "source_district_name":
                    required(source, "source_district_name"),
                "source_feature_id":
                    required(source, "source_feature_id"),
                "source_feature_index":
                    source.get("source_feature_index"),
                "source_geometry_hash":
                    required(source, "source_geometry_hash"),
                "source_state": required(source, "source_state"),
                "source_state_code":
                    required(source, "expected_state_code"),
                "source_subdistrict_code":
                    required(
                        source,
                        "normalized_source_subdistrict_code",
                    ),
                "source_subdistrict_name":
                    required(source, "source_subdistrict_name"),
                "source_subdistrict_name_normalized":
                    source_parent_normalized,
                "source_village_code":
                    required(source, "normalized_source_village_code"),
                "source_village_name":
                    required(source, "source_village_name"),
                "token_jaccard_similarity": round(
                    len(intersection) / len(union)
                    if union else 0.0,
                    6,
                ),
            }
        )

    output.sort(
        key=lambda row: (
            row["source_state"],
            row["source_district_code"],
            row["source_subdistrict_code"],
            row["canonical_block_code"],
            row["source_feature_index"],
            row["candidate_id"],
        )
    )

    candidate_ids = [row["candidate_id"] for row in output]
    source_feature_ids = [row["source_feature_id"] for row in output]

    disposition_exact = all(
        row.get("current_disposition") == SELECTED_DISPOSITION
        for row in selected
    )
    one_match_each = all(
        row.get("canonical_match_count") == 1
        and isinstance(row.get("canonical_matches"), list)
        and len(row["canonical_matches"]) == 1
        for row in selected
    )
    district_context_exact = all(
        str(row["normalized_source_district_code"])
        == str(row["canonical_matches"][0]["district_code"])
        for row in selected
    )
    state_context_exact = all(
        str(row["expected_state_code"])
        == str(row["canonical_matches"][0]["state_code"])
        for row in selected
    )

    write_jsonl(output_rows, output)
    rows_sha256 = sha256_file(output_rows)

    band_counts = dict(
        sorted(Counter(row["evidence_band"] for row in output).items())
    )
    state_band_matrix: dict[str, dict[str, int]] = {}
    for row in output:
        state_band_matrix.setdefault(row["source_state"], {})
        band = row["evidence_band"]
        state_band_matrix[row["source_state"]][band] = (
            state_band_matrix[row["source_state"]].get(band, 0) + 1
        )
    state_band_matrix = {
        state: dict(sorted(counts.items()))
        for state, counts in sorted(state_band_matrix.items())
    }

    checks = {
        "all_rows_require_review": all(
            row["review_decision"] == ""
            and row["reviewer"] == ""
            and row["review_evidence_basis"] == ""
            and row["review_evidence_reference"] == ""
            for row in output
        ),
        "automatic_reparenting_disabled": all(
            row["automatic_action_authorized"] is False
            for row in output
        ),
        "candidate_identity_unique":
            len(set(candidate_ids)) == len(candidate_ids),
        "canonical_match_count_exact": one_match_each,
        "cross_level_identifiers_not_compared": all(
            row["identifier_comparison"]
            == "NOT_COMPARABLE_CROSS_LEVEL"
            for row in output
        ),
        "district_context_exact": district_context_exact,
        "input_disposition_exact": disposition_exact,
        "input_row_count_exact":
            len(input_rows) == EXPECTED_INPUT_ROWS,
        "input_sha256_pinned":
            input_sha256 == INPUT_ROWS_SHA256,
        "no_database_writes": True,
        "not_authorized": True,
        "selected_row_count_exact":
            len(output) == EXPECTED_SELECTED_ROWS,
        "source_feature_identity_unique":
            len(set(source_feature_ids)) == len(source_feature_ids),
        "state_context_exact": state_context_exact,
    }
    healthy = all(checks.values())

    summary = {
        "allowed_review_decisions": [
            "CONFIRM_CURRENT_CANONICAL_BLOCK",
            "IDENTIFY_ALTERNATE_CURRENT_BLOCK",
            "DEFER_FOR_AUTHORITATIVE_RESEARCH",
        ],
        "checks": checks,
        "counts_by_evidence_band": band_counts,
        "database_writes_attempted": False,
        "healthy": healthy,
        "input": str(input_path),
        "input_row_count": len(input_rows),
        "input_sha256": input_sha256,
        "policy": {
            "automatic_reparenting_authorized": False,
            "candidate_updates_authorized": False,
            "canonical_changes_authorized": False,
            "project_matching_authorized": False,
            "runtime_activation_authorized": False,
            "runtime_staging_authorized": False,
        },
        "row_count": len(output),
        "rows": str(output_rows),
        "rows_sha256": rows_sha256,
        "schema_version": SCHEMA_VERSION,
        "state_evidence_band_matrix": state_band_matrix,
        "status": (
            "EVIDENCE_BUILT_NOT_AUTHORIZED"
            if healthy
            else "EVIDENCE_BUILD_FAILED"
        ),
    }
    summary["summary_checksum"] = stable_checksum(summary)
    return summary, healthy


def parse_args() -> argparse.Namespace:
    repository = Path(__file__).resolve().parents[2]
    campaign = repository / (
        "data/staged/core_stack/promotion_review/"
        "20260925-lgd-priority-state-reconciliation-v1"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=campaign
        / "nwdp_legacy_held_review_queue_rows.jsonl",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=campaign
        / "nwdp_legacy_block_parent_review_evidence.json",
    )
    parser.add_argument(
        "--output-rows",
        type=Path,
        default=campaign
        / "nwdp_legacy_block_parent_review_evidence_rows.jsonl",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        args.output_summary.parent.mkdir(parents=True, exist_ok=True)
        args.output_rows.parent.mkdir(parents=True, exist_ok=True)

        summary, healthy = build(
            args.input.resolve(),
            args.output_rows.resolve(),
        )
        args.output_summary.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if healthy else 1
    except Exception as exc:
        error = {
            "database_writes_attempted": False,
            "error": f"{type(exc).__name__}:{exc}",
            "fail_closed": True,
            "healthy": False,
            "schema_version": SCHEMA_VERSION,
        }
        print(
            json.dumps(error, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
