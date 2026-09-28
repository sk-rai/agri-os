#!/usr/bin/env python3
"""Build a human-review batch for NWDP district reconciliation evidence.

The batch pre-fills current LGD district identity and NWDP legacy-parent
evidence. All review and authoritative confirmation fields remain blank.
Accepting NWDP evidence only permits its use in further research; it does not
approve Core mappings or change canonical geography.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness"
)
DEFAULT_INPUT = DEFAULT_DIR / (
    "geography_core_layer_nwdp_district_reconciliation_probe_rows.jsonl"
)

EXPECTED_INPUT_SHA256 = (
    "a1302e18759668f74623b2611d2006a18dc7a8b37db95f720a06497343299f1d"
)
EXPECTED_ROW_COUNT = 13
EXPECTED_COUNTS_BY_EVIDENCE_STATUS = {
    "NWDP_COMPLETE_VILLAGE_CODE_RECONCILIATION_EVIDENCE": 4,
    "NWDP_NO_VILLAGE_CODE_RECONCILIATION_EVIDENCE": 1,
    "NWDP_PARTIAL_VILLAGE_CODE_RECONCILIATION_EVIDENCE": 8,
}

ALLOWED_REVIEW_DECISIONS = [
    "ACCEPT_NWDP_RECONCILIATION_EVIDENCE_FOR_RESEARCH",
    "REJECT_NWDP_RECONCILIATION_EVIDENCE",
    "DEFER_FOR_AUTHORITATIVE_RESEARCH",
]
ALLOWED_EVIDENCE_BASES = [
    "LGD_VILLAGE_CODE_CONTINUITY",
    "OFFICIAL_REORGANIZATION_NOTIFICATION",
    "AUTHORITATIVE_CURRENT_DISTRICT_GEOMETRY",
    "OTHER_DOCUMENTED_EVIDENCE",
]

REVIEW_FIELDS = {
    "review_decision": "",
    "review_evidence_basis": "",
    "authoritative_source_title": "",
    "authoritative_source_url": "",
    "authoritative_source_date": "",
    "authoritative_notification_number": "",
    "reviewer": "",
    "review_notes": "",
}

SCHEMA_VERSION = (
    "geography_core_layer_nwdp_district_reconciliation_review_batch.v1"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-rows",
        type=Path,
        default=DEFAULT_INPUT,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DIR,
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def review_route(row: dict[str, Any]) -> str:
    status = row["evidence_status"]
    if status == (
        "NWDP_COMPLETE_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
    ):
        return (
            "REVIEW_COMPLETE_NWDP_EVIDENCE_WITH_AUTHORITATIVE_CONFIRMATION"
        )
    if status == (
        "NWDP_PARTIAL_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
    ):
        return (
            "REVIEW_PARTIAL_NWDP_EVIDENCE_AND_UNMATCHED_VILLAGES"
        )
    return "AUTHORITATIVE_SOURCE_REQUIRED_NO_NWDP_EVIDENCE"


def review_priority(row: dict[str, Any]) -> str:
    status = row["evidence_status"]
    if status == (
        "NWDP_COMPLETE_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
    ):
        return "R1_COMPLETE_NWDP_EVIDENCE"
    if status == (
        "NWDP_PARTIAL_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
    ):
        return "R2_PARTIAL_NWDP_EVIDENCE"
    return "R3_NO_NWDP_EVIDENCE"


def main() -> int:
    args = parse_args()
    input_hash = sha256(args.input_rows)
    input_rows = read_jsonl(args.input_rows)

    rows = []
    for source in input_rows:
        parent_summary = [
            {
                "source_state_name": parent.get(
                    "source_state_name"
                ),
                "source_stcode": parent.get("source_stcode"),
                "source_district_name": parent.get(
                    "source_district_name"
                ),
                "source_dtcode": parent.get("source_dtcode"),
                "matched_canonical_village_count": parent.get(
                    "matched_canonical_village_count"
                ),
                "matched_source_feature_count": parent.get(
                    "matched_source_feature_count"
                ),
                "validated_source_feature_count": parent.get(
                    "validated_source_feature_count"
                ),
            }
            for parent in source["nwdp_source_parents"]
        ]

        rows.append(
            {
                "state_or_ut": source["state_or_ut"],
                "state_lgd_code": source["state_lgd_code"],
                "district": source["district"],
                "district_lgd_code": source[
                    "district_lgd_code"
                ],
                "crosswalk_review_priority": source[
                    "crosswalk_review_priority"
                ],
                "canonical_active_village_count": source[
                    "canonical_active_village_count"
                ],
                "matched_canonical_village_count": source[
                    "matched_canonical_village_count"
                ],
                "unmatched_canonical_village_count": source[
                    "unmatched_canonical_village_count"
                ],
                "nwdp_village_code_coverage_ratio": source[
                    "nwdp_village_code_coverage_ratio"
                ],
                "nwdp_source_parent_count": source[
                    "nwdp_source_parent_count"
                ],
                "nwdp_direct_district_name_match": source[
                    "nwdp_direct_district_name_match"
                ],
                "nwdp_matched_source_feature_count": source[
                    "nwdp_matched_source_feature_count"
                ],
                "nwdp_validated_source_feature_count": source[
                    "nwdp_validated_source_feature_count"
                ],
                "all_matched_source_geometry_validated": source[
                    "all_matched_source_geometry_validated"
                ],
                "nwdp_source_parents": parent_summary,
                "evidence_status": source["evidence_status"],
                "review_priority": review_priority(source),
                "review_route": review_route(source),
                "accepted_use_boundary": (
                    "NON_AUTHORITATIVE_RECONCILIATION_EVIDENCE_ONLY"
                ),
                "authoritative_confirmation_required": True,
                "core_mapping_approval_authorized": False,
                "canonical_change_authorized": False,
                "database_apply_authorized": False,
                "runtime_activation_authorized": False,
                **REVIEW_FIELDS,
            }
        )

    rows.sort(
        key=lambda row: (
            row["review_priority"],
            row["state_or_ut"],
            row["district_lgd_code"],
        )
    )

    counts_by_status = Counter(
        row["evidence_status"] for row in rows
    )
    counts_by_priority = Counter(
        row["review_priority"] for row in rows
    )
    counts_by_route = Counter(
        row["review_route"] for row in rows
    )

    identities = [
        (
            row["state_lgd_code"],
            row["district_lgd_code"],
        )
        for row in rows
    ]

    checks = {
        "input_sha256_pinned": (
            input_hash == EXPECTED_INPUT_SHA256
        ),
        "input_row_count_exact": (
            len(input_rows) == EXPECTED_ROW_COUNT
        ),
        "review_row_count_exact": (
            len(rows) == EXPECTED_ROW_COUNT
        ),
        "evidence_status_counts_exact": (
            dict(sorted(counts_by_status.items()))
            == EXPECTED_COUNTS_BY_EVIDENCE_STATUS
        ),
        "district_identity_unique": (
            len(identities) == len(set(identities))
        ),
        "source_parent_counts_reconcile": all(
            row["nwdp_source_parent_count"]
            == len(row["nwdp_source_parents"])
            for row in rows
        ),
        "parent_village_counts_reconcile": all(
            sum(
                int(
                    parent[
                        "matched_canonical_village_count"
                    ]
                    or 0
                )
                for parent in row["nwdp_source_parents"]
            )
            == row["matched_canonical_village_count"]
            for row in rows
        ),
        "review_fields_blank": all(
            all(row[field] == "" for field in REVIEW_FIELDS)
            for row in rows
        ),
        "authoritative_confirmation_required": all(
            row["authoritative_confirmation_required"]
            is True
            for row in rows
        ),
        "nwdp_use_boundary_exact": all(
            row["accepted_use_boundary"]
            == (
                "NON_AUTHORITATIVE_RECONCILIATION_"
                "EVIDENCE_ONLY"
            )
            for row in rows
        ),
        "no_database_writes": True,
        "not_authorized": True,
        "automatic_actions_disabled": True,
    }
    healthy = all(checks.values())

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_"
        "review_batch_rows.jsonl"
    )
    csv_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_"
        "review_batch.csv"
    )
    summary_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_"
        "review_batch.json"
    )

    with rows_path.open("w", encoding="utf-8") as handle:
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

    flat_rows = []
    for row in rows:
        flat = dict(row)
        flat["nwdp_source_parents"] = json.dumps(
            row["nwdp_source_parents"],
            ensure_ascii=False,
            sort_keys=True,
        )
        flat_rows.append(flat)

    fieldnames = sorted(
        {field for row in flat_rows for field in row}
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(flat_rows)

    core_summary = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "NWDP_RECONCILIATION_REVIEW_BATCH_BUILT_NOT_AUTHORIZED"
            if healthy
            else "NWDP_RECONCILIATION_REVIEW_BATCH_INVALID"
        ),
        "healthy": healthy,
        "database_writes_attempted": False,
        "input": str(args.input_rows.resolve()),
        "input_sha256": input_hash,
        "row_count": len(rows),
        "counts_by_evidence_status": dict(
            sorted(counts_by_status.items())
        ),
        "counts_by_review_priority": dict(
            sorted(counts_by_priority.items())
        ),
        "counts_by_review_route": dict(
            sorted(counts_by_route.items())
        ),
        "allowed_review_decisions": (
            ALLOWED_REVIEW_DECISIONS
        ),
        "allowed_evidence_bases": (
            ALLOWED_EVIDENCE_BASES
        ),
        "checks": checks,
        "policy": {
            "lgd_remains_canonical": True,
            "nwdp_is_non_authoritative_reconciliation_evidence": True,
            "authoritative_confirmation_required": True,
            "human_review_required": True,
            "core_mapping_approval_authorized": False,
            "canonical_geography_changes_authorized": False,
            "database_apply_authorized": False,
            "runtime_activation_authorized": False,
            "android_behavior_change_authorized": False,
        },
    }

    summary = {
        **core_summary,
        "rows": str(rows_path.resolve()),
        "rows_sha256": sha256(rows_path),
        "csv": str(csv_path.resolve()),
        "csv_sha256": sha256(csv_path),
        "summary_checksum": canonical_sha256(core_summary),
    }
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
