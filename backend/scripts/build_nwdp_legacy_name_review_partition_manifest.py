#!/usr/bin/env python3
"""Verify the deterministic partition of all legacy NWDP name reviews."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "nwdp_legacy_name_review_partition_manifest.v1"
EXPECTED_TOTAL = 7_540
EVIDENCE_ROWS_SHA256 = (
    "dd7d68ea2db24f1bb1de9243bdfb9f217a7917fad0f8dc2168d316d4e2af6d62"
)

BATCHES = (
    {
        "name": "strong",
        "count": 217,
        "summary": "nwdp_legacy_strong_name_review_batch.json",
        "summary_sha256":
            "ab3ee9b260b160322e468363c86d6c4e0204f8e703bf062374531129b7756d38",
        "rows": "nwdp_legacy_strong_name_review_batch_rows.jsonl",
        "rows_sha256":
            "7cb16e8003488db5e9d2fb08c4f3248ce277cef757954ba3161f22c58dbb3b8b",
        "bands": {
            "ADMINISTRATIVE_QUALIFIER_ONLY",
            "TOKEN_ORDER_ONLY",
        },
    },
    {
        "name": "high-similarity",
        "count": 4_004,
        "summary": "nwdp_legacy_high_similarity_review_batch.json",
        "summary_sha256":
            "77676d4a31d7a7b3bfb33e53c25453aa56d9354b33e23f7c6f6be1181cbf5ae4",
        "rows": "nwdp_legacy_high_similarity_review_batch_rows.jsonl",
        "rows_sha256":
            "13eab896a106893f5709b018200745123874f643072cac0f673ef259511c75ae",
        "bands": {"HIGH_LEXICAL_SIMILARITY"},
    },
    {
        "name": "moderate-similarity",
        "count": 1_877,
        "summary": "nwdp_legacy_moderate_similarity_review_batch.json",
        "summary_sha256":
            "d7b46baa9562a2271eb515bcad52aa835bc9482b6413de6770d183df34c0f6a3",
        "rows": "nwdp_legacy_moderate_similarity_review_batch_rows.jsonl",
        "rows_sha256":
            "f11610c7b31f6de52ecd13af11e86ee3f88e134c66dfc2a31204fc113616af4a",
        "bands": {"MODERATE_LEXICAL_SIMILARITY"},
    },
    {
        "name": "low-similarity",
        "count": 1_442,
        "summary": "nwdp_legacy_low_similarity_review_batch.json",
        "summary_sha256":
            "03c73598b68786c85c1be3f8316a4fd5fff5a9067781e2fc4278eced1c7ea642",
        "rows": "nwdp_legacy_low_similarity_review_batch_rows.jsonl",
        "rows_sha256":
            "52969883443199b87d3b805df4ec6c38861b19421899f20a2f8b3b9b11bf92e1",
        "bands": {"LOW_LEXICAL_SIMILARITY"},
    },
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


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


def required_identity(row: dict[str, Any], field: str) -> str:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"MISSING_{field.upper()}")
    return value


def stable_checksum(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build(campaign: Path) -> tuple[dict[str, Any], bool]:
    evidence_path = (
        campaign / "nwdp_legacy_name_review_evidence_rows.jsonl"
    )
    evidence_sha256 = sha256_file(evidence_path)
    evidence_rows = load_jsonl(evidence_path)

    evidence_candidate_ids = [
        required_identity(row, "candidate_id")
        for row in evidence_rows
    ]
    evidence_source_ids = [
        required_identity(row, "source_feature_id")
        for row in evidence_rows
    ]

    all_rows: list[dict[str, Any]] = []
    batch_candidate_sets: list[set[str]] = []
    batch_results = []

    summary_hashes_pinned = True
    row_hashes_pinned = True
    batch_counts_exact = True
    batch_summaries_healthy = True
    batch_identity_unique = True
    evidence_bands_exact = True

    for batch in BATCHES:
        summary_path = campaign / batch["summary"]
        rows_path = campaign / batch["rows"]

        summary_sha256 = sha256_file(summary_path)
        rows_sha256 = sha256_file(rows_path)
        summary = load_json(summary_path)
        rows = load_jsonl(rows_path)

        candidate_ids = [
            required_identity(row, "candidate_id")
            for row in rows
        ]
        source_ids = [
            required_identity(row, "source_feature_id")
            for row in rows
        ]
        observed_bands = {
            str(row.get("evidence_band", "")).strip()
            for row in rows
        }

        summary_hashes_pinned &= (
            summary_sha256 == batch["summary_sha256"]
        )
        row_hashes_pinned &= rows_sha256 == batch["rows_sha256"]
        batch_counts_exact &= len(rows) == batch["count"]
        batch_identity_unique &= (
            len(set(candidate_ids)) == len(rows)
            and len(set(source_ids)) == len(rows)
        )
        evidence_bands_exact &= observed_bands == batch["bands"]
        batch_summaries_healthy &= (
            summary.get("healthy") is True
            and summary.get("database_writes_attempted") is False
            and summary.get("row_count") == batch["count"]
            and summary.get("rows_sha256") == batch["rows_sha256"]
        )

        all_rows.extend(rows)
        batch_candidate_sets.append(set(candidate_ids))
        batch_results.append(
            {
                "evidence_bands": sorted(observed_bands),
                "name": batch["name"],
                "row_count": len(rows),
                "rows_sha256": rows_sha256,
                "summary_sha256": summary_sha256,
            }
        )

    all_candidate_ids = [
        required_identity(row, "candidate_id")
        for row in all_rows
    ]
    all_source_ids = [
        required_identity(row, "source_feature_id")
        for row in all_rows
    ]

    pairwise_disjoint = all(
        not batch_candidate_sets[left] & batch_candidate_sets[right]
        for left in range(len(batch_candidate_sets))
        for right in range(left + 1, len(batch_candidate_sets))
    )

    checks = {
        "automatic_actions_disabled": True,
        "batch_counts_exact": batch_counts_exact,
        "batch_identity_unique": batch_identity_unique,
        "batch_summaries_healthy": batch_summaries_healthy,
        "candidate_identity_unique":
            len(set(all_candidate_ids)) == len(all_candidate_ids),
        "candidate_partition_exact":
            set(all_candidate_ids) == set(evidence_candidate_ids),
        "evidence_bands_exact": evidence_bands_exact,
        "evidence_candidate_identity_unique":
            len(set(evidence_candidate_ids))
            == len(evidence_candidate_ids),
        "evidence_row_count_exact":
            len(evidence_rows) == EXPECTED_TOTAL,
        "evidence_sha256_pinned":
            evidence_sha256 == EVIDENCE_ROWS_SHA256,
        "evidence_source_feature_identity_unique":
            len(set(evidence_source_ids)) == len(evidence_source_ids),
        "no_database_writes": True,
        "not_authorized": True,
        "partition_pairwise_disjoint": pairwise_disjoint,
        "partition_row_count_exact":
            len(all_rows) == EXPECTED_TOTAL,
        "row_hashes_pinned": row_hashes_pinned,
        "source_feature_identity_unique":
            len(set(all_source_ids)) == len(all_source_ids),
        "source_feature_partition_exact":
            set(all_source_ids) == set(evidence_source_ids),
        "summary_hashes_pinned": summary_hashes_pinned,
    }
    healthy = all(checks.values())

    result = {
        "batches": batch_results,
        "checks": checks,
        "database_writes_attempted": False,
        "evidence_rows_sha256": evidence_sha256,
        "healthy": healthy,
        "policy": {
            "automatic_equivalence_authorized": False,
            "candidate_updates_authorized": False,
            "canonical_changes_authorized": False,
            "project_matching_authorized": False,
            "runtime_activation_authorized": False,
            "runtime_staging_authorized": False,
        },
        "row_count": len(all_rows),
        "schema_version": SCHEMA_VERSION,
        "status": (
            "PARTITION_VERIFIED_NOT_AUTHORIZED"
            if healthy
            else "PARTITION_VERIFICATION_FAILED"
        ),
    }
    result["summary_checksum"] = stable_checksum(result)
    return result, healthy


def parse_args() -> argparse.Namespace:
    repository = Path(__file__).resolve().parents[2]
    campaign = repository / (
        "data/staged/core_stack/promotion_review/"
        "20260925-lgd-priority-state-reconciliation-v1"
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--campaign-dir",
        type=Path,
        default=campaign,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=campaign
        / "nwdp_legacy_name_review_partition_manifest.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result, healthy = build(args.campaign_dir.resolve())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                result,
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
