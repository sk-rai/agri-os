#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

EXPECTED_SHA256 = (
    "71513ec165ea100a5412688a1ac876a122eafd722bc71a62d89d1edf4adba2d0"
)
EXPECTED_COUNTS = {
    "GLOBAL_ADDITIVE_VILLAGE_REVIEW_REQUIRED": 1,
    "GLOBAL_CANONICAL_STATE_REMEDIATION_REQUIRED": 12,
    "PROJECT_MANUAL_ELIGIBLE_WITH_GLOBAL_HIERARCHY_REVIEW": 3,
}
ROUTES = {
    "CANONICAL_STATE_GAP_REVIEW":
        "GLOBAL_CANONICAL_STATE_REMEDIATION_REQUIRED",
    "CANONICAL_DISTRICT_GAP_REVIEW":
        "PROJECT_MANUAL_ELIGIBLE_WITH_GLOBAL_HIERARCHY_REVIEW",
    "CURRENT_LGD_ABSENCE_REVIEW":
        "GLOBAL_ADDITIVE_VILLAGE_REVIEW_REQUIRED",
}
CSV_FIELDS = [
    "candidate_id",
    "source_feature_id",
    "source_state",
    "source_district_code",
    "source_district_name",
    "source_subdistrict_code",
    "source_subdistrict_name",
    "source_village_code",
    "source_village_name",
    "review_queue",
    "resolution_route",
    "global_remediation_required",
    "project_manual_mapping_eligible",
    "canonical_target_village_id",
    "canonical_target_village_code",
    "canonical_target_village_name",
    "canonical_target_district_code",
    "canonical_target_district_name",
    "geometry_validation_status",
    "project_tenant_id",
    "project_id",
    "review_decision",
    "reviewer",
    "review_notes",
    "evidence_reference",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def route_row(source: dict) -> dict:
    route = ROUTES[source["review_queue"]]
    matches = source.get("canonical_matches") or []
    target = matches[0] if len(matches) == 1 else {}
    project_eligible = (
        route
        == "PROJECT_MANUAL_ELIGIBLE_WITH_GLOBAL_HIERARCHY_REVIEW"
    )
    return {
        "candidate_id": source["candidate_id"],
        "source_feature_id": source["source_feature_id"],
        "source_state": source["source_state"],
        "source_district_code":
            source.get("normalized_source_district_code"),
        "source_district_name": source.get("source_district_name"),
        "source_subdistrict_code":
            source.get("normalized_source_subdistrict_code"),
        "source_subdistrict_name":
            source.get("source_subdistrict_name"),
        "source_village_code":
            source.get("normalized_source_village_code"),
        "source_village_name": source.get("source_village_name"),
        "review_queue": source["review_queue"],
        "resolution_route": route,
        "global_remediation_required": True,
        "project_manual_mapping_eligible": project_eligible,
        "canonical_target_village_id": target.get("village_id"),
        "canonical_target_village_code": target.get("village_code"),
        "canonical_target_village_name": target.get("village_name"),
        "canonical_target_district_code": target.get("district_code"),
        "canonical_target_district_name": target.get("district_name"),
        "geometry_validation_status":
            source.get("geometry_validation_status"),
        "project_tenant_id": "",
        "project_id": "",
        "review_decision": "",
        "reviewer": "",
        "review_notes": "",
        "evidence_reference": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    input_hash = sha256(args.input)
    source_rows = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line
    ]
    selected = [
        row for row in source_rows
        if row.get("review_queue") in ROUTES
    ]
    rows = sorted(
        (route_row(row) for row in selected),
        key=lambda row: row["candidate_id"],
    )

    counts = dict(sorted(Counter(
        row["resolution_route"] for row in rows
    ).items()))
    candidate_ids = [row["candidate_id"] for row in rows]
    feature_ids = [row["source_feature_id"] for row in rows]

    checks = {
        "input_sha256_pinned": input_hash == EXPECTED_SHA256,
        "input_row_count_exact": len(source_rows) == 10052,
        "selected_row_count_exact": len(rows) == 16,
        "resolution_route_counts_exact": counts == EXPECTED_COUNTS,
        "candidate_identity_unique":
            len(candidate_ids) == len(set(candidate_ids)),
        "source_feature_identity_unique":
            len(feature_ids) == len(set(feature_ids)),
        "all_rows_geometry_validated": all(
            row["geometry_validation_status"] == "VALIDATED"
            for row in rows
        ),
        "project_manual_targets_present": all(
            bool(row["canonical_target_village_id"])
            == row["project_manual_mapping_eligible"]
            for row in rows
        ),
        "global_remediation_retained": all(
            row["global_remediation_required"] for row in rows
        ),
        "review_fields_blank": all(
            not row[field]
            for row in rows
            for field in (
                "project_tenant_id",
                "project_id",
                "review_decision",
                "reviewer",
                "review_notes",
                "evidence_reference",
            )
        ),
        "automatic_actions_disabled": True,
        "no_database_writes": True,
        "not_authorized": True,
    }
    healthy = all(checks.values())

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = (
        args.output_dir
        / "nwdp_legacy_canonical_gap_resolution_routes_rows.jsonl"
    )
    csv_path = (
        args.output_dir
        / "nwdp_legacy_canonical_gap_resolution_routes.csv"
    )
    summary_path = (
        args.output_dir
        / "nwdp_legacy_canonical_gap_resolution_routes.json"
    )

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(
            {field: row.get(field, "") for field in CSV_FIELDS}
            for row in rows
        )

    summary_core = {
        "schema_version":
            "nwdp_legacy_canonical_gap_resolution_routes.v2",
        "status":
            "ROUTED_NOT_AUTHORIZED"
            if healthy else "ROUTING_INVALID",
        "healthy": healthy,
        "input": str(args.input.resolve()),
        "input_sha256": input_hash,
        "input_row_count": len(source_rows),
        "row_count": len(rows),
        "counts_by_resolution_route": counts,
        "project_manual_mapping_eligible_count": sum(
            row["project_manual_mapping_eligible"] for row in rows
        ),
        "global_remediation_required_count": sum(
            row["global_remediation_required"] for row in rows
        ),
        "checks": checks,
        "policy": {
            "global_deterministic_reuse_supported": True,
            "global_evidenced_vernacular_reuse_supported": True,
            "project_manual_mapping_tenant_scoped": True,
            "project_manual_mapping_project_scoped": True,
            "project_manual_mapping_requires_existing_canonical_target":
                True,
            "canonical_changes_authorized": False,
            "project_mapping_apply_authorized": False,
            "runtime_activation_authorized": False,
        },
        "allowed_review_decisions": [
            "APPROVE_PROJECT_SCOPED_MANUAL_MAPPING",
            "CONFIRM_GLOBAL_REMEDIATION_ROUTE",
            "DEFER_FOR_AUTHORITATIVE_RESEARCH",
        ],
        "rows": str(rows_path.resolve()),
        "rows_sha256": sha256(rows_path),
        "csv": str(csv_path.resolve()),
        "csv_sha256": sha256(csv_path),
        "database_writes_attempted": False,
    }
    checksum = hashlib.sha256(
        json.dumps(
            summary_core,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    summary = {
        **summary_core,
        "summary_checksum": checksum,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
