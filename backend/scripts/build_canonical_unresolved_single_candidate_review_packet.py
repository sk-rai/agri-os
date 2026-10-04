#!/usr/bin/env python3
"""Build a read-only admin review packet from validated local-evidence output."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA_VERSION = "canonical_unresolved_single_candidate_review_packet.v1"
SOURCE_SCHEMA = "canonical_unresolved_local_evidence_delta.v1"
QUEUES = {"DETERMINISTIC_SINGLE_REVIEW", "HIGH_CONFIDENCE_SINGLE_REVIEW"}
EXPECTED = {
    "review_rows": 140,
    "deterministic": 70,
    "high_confidence": 70,
    "rank_1": 51,
    "rank_3": 19,
    "rank_4": 70,
    "states": 6,
    "with_prior_evidence": 140,
    "unique_sources": 131,
    "collision_sources": 6,
    "collision_rows": 15,
}
OUTPUT_FIELDS = (
    "packet_order",
    "review_priority",
    "review_queue",
    "state_lgd_code",
    "state_name",
    "district_lgd_code",
    "district_name",
    "block_name",
    "village_lgd_code",
    "village_name",
    "village_id",
    "source_feature_id",
    "source_feature_index",
    "source_stcode",
    "source_dtcode",
    "source_sdcode",
    "source_bkcode",
    "source_vlcode",
    "source_state_name",
    "source_district_name",
    "source_subdistrict_name",
    "source_block_name",
    "source_village_name",
    "match_rank",
    "match_basis",
    "prior_candidate_evidence_present",
    "prior_candidate_evidence",
    "source_candidate_village_count",
    "source_collision",
    "review_eligibility",
    "automatic_resolution_authorized",
    "primary_review_decision",
    "primary_reviewer_id",
    "primary_reviewed_at",
    "primary_review_notes",
    "second_review_decision",
    "second_reviewer_id",
    "second_reviewed_at",
    "second_review_notes",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    manifest_path = args.evidence_dir / "canonical_unresolved_local_evidence_delta.json"
    pairs_path = args.evidence_dir / "canonical_unresolved_candidate_pairs.csv"
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pairs = read_csv(pairs_path)

    source_valid = (
        source_manifest.get("schema_version") == SOURCE_SCHEMA
        and source_manifest.get("healthy") is True
        and source_manifest.get("read_only") is True
        and source_manifest.get("database_before") == source_manifest.get("database_after")
    )
    selected = [
        row
        for row in pairs
        if row["disposition"] in QUEUES and row["candidate_count"] == "1"
    ]
    source_counts = Counter(row["source_feature_id"] for row in selected)
    collision_sources = {source_id for source_id, count in source_counts.items() if count > 1}

    priority_by_rank = {"1": "1", "3": "2", "4": "3"}
    selected.sort(
        key=lambda row: (
            int(priority_by_rank[row["match_rank"]]),
            int(row["state_lgd_code"]),
            row["district_name"].casefold(),
            row["block_name"].casefold(),
            row["village_name"].casefold(),
            row["village_id"],
        )
    )

    packet_rows: list[dict[str, object]] = []
    for packet_order, row in enumerate(selected, 1):
        packet_rows.append(
            {
                "packet_order": packet_order,
                "review_priority": priority_by_rank[row["match_rank"]],
                "review_queue": row["disposition"],
                **{field: row[field] for field in OUTPUT_FIELDS if field in row},
                "source_candidate_village_count": source_counts[row["source_feature_id"]],
                "source_collision": source_counts[row["source_feature_id"]] > 1,
                "review_eligibility": "CONFLICT_REVIEW_REQUIRED" if source_counts[row["source_feature_id"]] > 1 else "TWO_SESSION_REVIEW_ELIGIBLE",
                "automatic_resolution_authorized": False,
                "primary_review_decision": "",
                "primary_reviewer_id": "",
                "primary_reviewed_at": "",
                "primary_review_notes": "",
                "second_review_decision": "",
                "second_reviewer_id": "",
                "second_reviewed_at": "",
                "second_review_notes": "",
            }
        )

    dispositions = Counter(row["review_queue"] for row in packet_rows)
    ranks = Counter(row["match_rank"] for row in packet_rows)
    evidence = Counter(row["prior_candidate_evidence"] for row in packet_rows)
    states: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in packet_rows:
        states[(str(row["state_lgd_code"]), str(row["state_name"]))][
            str(row["review_queue"])
        ] += 1

    state_rows = [
        {
            "state_lgd_code": code,
            "state_name": name,
            "review_rows": sum(counts.values()),
            "deterministic_single_review": counts["DETERMINISTIC_SINGLE_REVIEW"],
            "high_confidence_single_review": counts["HIGH_CONFIDENCE_SINGLE_REVIEW"],
        }
        for (code, name), counts in sorted(states.items(), key=lambda item: int(item[0][0]))
    ]

    checks = {
        "source_manifest_valid": source_valid,
        "review_rows_exact": len(packet_rows) == EXPECTED["review_rows"],
        "villages_unique": len({row["village_id"] for row in packet_rows})
        == EXPECTED["review_rows"],
        "unique_sources_exact": len(source_counts) == EXPECTED["unique_sources"],
        "collision_sources_exact": len(collision_sources) == EXPECTED["collision_sources"],
        "collision_rows_exact": sum(row["source_collision"] for row in packet_rows)
        == EXPECTED["collision_rows"],
        "deterministic_exact": dispositions["DETERMINISTIC_SINGLE_REVIEW"]
        == EXPECTED["deterministic"],
        "high_confidence_exact": dispositions["HIGH_CONFIDENCE_SINGLE_REVIEW"]
        == EXPECTED["high_confidence"],
        "rank_1_exact": ranks["1"] == EXPECTED["rank_1"],
        "rank_3_exact": ranks["3"] == EXPECTED["rank_3"],
        "rank_4_exact": ranks["4"] == EXPECTED["rank_4"],
        "state_count_exact": len(state_rows) == EXPECTED["states"],
        "prior_evidence_exact": sum(
            row["prior_candidate_evidence_present"] == "True" for row in packet_rows
        )
        == EXPECTED["with_prior_evidence"],
        "review_fields_blank": all(
            not row[field]
            for row in packet_rows
            for field in (
                "primary_review_decision",
                "primary_reviewer_id",
                "second_review_decision",
                "second_reviewer_id",
            )
        ),
        "automatic_resolution_prohibited": all(
            row["automatic_resolution_authorized"] is False for row in packet_rows
        ),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = args.output_dir / "single_candidate_review_packet.csv"
    state_path = args.output_dir / "single_candidate_review_state_summary.csv"
    write_csv(packet_path, packet_rows, OUTPUT_FIELDS)
    write_csv(
        state_path,
        state_rows,
        (
            "state_lgd_code",
            "state_name",
            "review_rows",
            "deterministic_single_review",
            "high_confidence_single_review",
        ),
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASSED" if all(checks.values()) else "FAILED",
        "healthy": all(checks.values()),
        "read_only": True,
        "checks": checks,
        "scope": {
            "review_rows": len(packet_rows),
            "state_count": len(state_rows),
            "unique_source_features": len(source_counts),
            "source_collision_groups": len(collision_sources),
            "source_collision_rows": sum(source_counts[row["source_feature_id"]] > 1 for row in selected),
            "dispositions": dict(sorted(dispositions.items())),
            "match_ranks": dict(sorted(ranks.items())),
            "prior_candidate_evidence": dict(sorted(evidence.items())),
        },
        "source_evidence": {
            "manifest_sha256": sha256(manifest_path),
            "candidate_pairs_sha256": sha256(pairs_path),
            "source_database_unchanged": source_manifest.get("database_before")
            == source_manifest.get("database_after"),
        },
        "workflow": {
            "allowed_primary_decisions": [
                "ACCEPT_FOR_SECOND_REVIEW",
                "REJECT",
                "HOLD",
            ],
            "second_review_required_for_acceptance": True,
            "packet_records_decisions": False,
            "automatic_application_authorized": False,
            "collision_rows_can_be_accepted": False,
        },
        "policy": {
            "database_accessed": False,
            "database_writes_attempted": False,
            "canonical_changes_authorized": False,
            "pin_link_changes_authorized": False,
            "runtime_changes_authorized": False,
            "project_resolution_changes_authorized": False,
            "android_changes_authorized": False,
        },
    }
    manifest_output = args.output_dir / "single_candidate_review_packet.json"
    manifest_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["healthy"]:
        raise SystemExit("CANONICAL UNRESOLVED SINGLE-CANDIDATE REVIEW PACKET FAILED")
    print("CANONICAL UNRESOLVED SINGLE-CANDIDATE REVIEW PACKET PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
