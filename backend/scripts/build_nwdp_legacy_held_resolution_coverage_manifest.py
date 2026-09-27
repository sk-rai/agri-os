#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

EXPECTED_INPUT_SHA256 = (
    "71513ec165ea100a5412688a1ac876a122eafd722bc71a62d89d1edf4adba2d0"
)
EXPECTED_QUEUE_COUNTS = {
    "BLOCK_PARENT_REVIEW": 2272,
    "CANONICAL_DISTRICT_GAP_REVIEW": 3,
    "CANONICAL_STATE_GAP_REVIEW": 12,
    "CURRENT_LGD_ABSENCE_REVIEW": 1,
    "DISTRICT_PARENT_REVIEW": 192,
    "NAME_EQUIVALENCE_REVIEW": 7540,
    "SOURCE_HIERARCHY_REVIEW": 32,
}
WORKFLOWS = [
    {
        "name": "name_equivalence",
        "queues": ["NAME_EQUIVALENCE_REVIEW"],
        "expected_count": 7540,
        "summary":
            "nwdp_legacy_name_review_partition_manifest.json",
        "summary_count_field": "row_count",
    },
    {
        "name": "block_parent",
        "queues": ["BLOCK_PARENT_REVIEW"],
        "expected_count": 2272,
        "summary":
            "nwdp_legacy_block_parent_review_evidence.json",
        "summary_count_field": "row_count",
    },
    {
        "name": "district_transition",
        "queues": ["DISTRICT_PARENT_REVIEW"],
        "expected_count": 192,
        "summary":
            "nwdp_legacy_district_parent_review_batch.json",
        "summary_count_field": "selected_village_row_count",
    },
    {
        "name": "source_hierarchy",
        "queues": ["SOURCE_HIERARCHY_REVIEW"],
        "expected_count": 32,
        "summary":
            "nwdp_legacy_source_hierarchy_review_batch.json",
        "summary_count_field": "selected_village_row_count",
    },
    {
        "name": "canonical_gap",
        "queues": [
            "CANONICAL_DISTRICT_GAP_REVIEW",
            "CANONICAL_STATE_GAP_REVIEW",
            "CURRENT_LGD_ABSENCE_REVIEW",
        ],
        "expected_count": 16,
        "summary":
            "nwdp_legacy_canonical_gap_resolution_routes.json",
        "summary_count_field": "row_count",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--campaign-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    input_hash = sha256(args.input)
    rows = [
        json.loads(line)
        for line in args.input.read_text(
            encoding="utf-8"
        ).splitlines()
        if line
    ]
    queue_counts = dict(sorted(Counter(
        row.get("review_queue") for row in rows
    ).items()))
    candidate_ids = [row["candidate_id"] for row in rows]
    feature_ids = [row["source_feature_id"] for row in rows]

    queue_to_workflow = {}
    duplicate_queue_routes = []
    for workflow in WORKFLOWS:
        for queue in workflow["queues"]:
            if queue in queue_to_workflow:
                duplicate_queue_routes.append(queue)
            queue_to_workflow[queue] = workflow["name"]

    routed_candidate_ids = []
    workflow_results = []
    artifact_checks = []

    for workflow in WORKFLOWS:
        selected = [
            row for row in rows
            if row.get("review_queue") in workflow["queues"]
        ]
        routed_candidate_ids.extend(
            row["candidate_id"] for row in selected
        )

        summary_path = (
            args.campaign_dir / workflow["summary"]
        )
        summary_exists = summary_path.is_file()
        summary = {}
        if summary_exists:
            summary = json.loads(
                summary_path.read_text(encoding="utf-8")
            )

        count_field = workflow["summary_count_field"]
        summary_count = summary.get(count_field)
        summary_healthy = summary.get("healthy") is True
        no_writes = (
            summary.get("database_writes_attempted") is False
        )

        output_hash_checks = {}
        for field in (
            "rows",
            "csv",
        ):
            referenced = summary.get(field)
            expected_hash = summary.get(f"{field}_sha256")
            if not referenced or not expected_hash:
                continue
            referenced_path = Path(referenced)
            output_hash_checks[field] = (
                referenced_path.is_file()
                and sha256(referenced_path) == expected_hash
            )

        result = {
            "name": workflow["name"],
            "queues": workflow["queues"],
            "expected_count": workflow["expected_count"],
            "actual_count": len(selected),
            "summary": str(summary_path.resolve()),
            "summary_sha256":
                sha256(summary_path) if summary_exists else None,
            "summary_count_field": count_field,
            "summary_count": summary_count,
            "summary_healthy": summary_healthy,
            "database_writes_attempted":
                summary.get("database_writes_attempted"),
            "output_hash_checks": output_hash_checks,
        }
        workflow_results.append(result)

        artifact_checks.extend([
            summary_exists,
            summary_healthy,
            no_writes,
            summary_count == workflow["expected_count"],
            len(selected) == workflow["expected_count"],
            all(output_hash_checks.values()),
        ])

    unexpected_queues = sorted(
        set(queue_counts) - set(queue_to_workflow)
    )
    missing_queues = sorted(
        set(queue_to_workflow) - set(queue_counts)
    )

    checks = {
        "input_sha256_pinned":
            input_hash == EXPECTED_INPUT_SHA256,
        "input_row_count_exact": len(rows) == 10052,
        "queue_counts_exact":
            queue_counts == EXPECTED_QUEUE_COUNTS,
        "candidate_identity_unique":
            len(candidate_ids) == len(set(candidate_ids)),
        "source_feature_identity_unique":
            len(feature_ids) == len(set(feature_ids)),
        "workflow_queue_routes_unique":
            not duplicate_queue_routes,
        "all_queues_routed":
            not unexpected_queues and not missing_queues,
        "workflow_counts_exact": all(
            item["actual_count"] == item["expected_count"]
            for item in workflow_results
        ),
        "candidate_partition_exact":
            len(routed_candidate_ids) == len(candidate_ids)
            and set(routed_candidate_ids) == set(candidate_ids),
        "candidate_partition_unique":
            len(routed_candidate_ids)
            == len(set(routed_candidate_ids)),
        "workflow_artifacts_healthy":
            all(artifact_checks),
        "automatic_actions_disabled": True,
        "no_database_writes": True,
        "not_authorized": True,
    }
    healthy = all(checks.values())

    summary_core = {
        "schema_version":
            "nwdp_legacy_held_resolution_coverage_manifest.v1",
        "status":
            "COVERAGE_VERIFIED_NOT_AUTHORIZED"
            if healthy else "COVERAGE_INVALID",
        "healthy": healthy,
        "input": str(args.input.resolve()),
        "input_sha256": input_hash,
        "row_count": len(rows),
        "queue_counts": queue_counts,
        "workflow_count": len(workflow_results),
        "workflows": workflow_results,
        "unexpected_queues": unexpected_queues,
        "missing_queues": missing_queues,
        "checks": checks,
        "policy": {
            "global_deterministic_reuse_supported": True,
            "global_evidenced_vernacular_reuse_supported": True,
            "project_manual_mapping_tenant_scoped": True,
            "project_manual_mapping_project_scoped": True,
            "canonical_changes_authorized": False,
            "project_mapping_apply_authorized": False,
            "runtime_activation_authorized": False,
        },
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

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
