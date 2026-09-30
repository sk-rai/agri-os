#!/usr/bin/env python3
"""Re-audit unresolved NWDP rows against current canonical geography.

Database behavior: read-only.

This orchestrates the existing post-LGD actionability audit and legacy-held
coverage verifier, then proves their unresolved candidate populations are
disjoint and still total 14,773 against the current canonical baseline.

It does not authorize canonical changes, boundary-candidate changes, staging,
runtime activation, project mapping, source changes, or Android changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
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


SCHEMA_VERSION = (
    "nwdp_current_canonical_unresolved_reaudit.v1"
)

DEFAULT_CAMPAIGN_DIR = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260925-lgd-priority-state-reconciliation-v1"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260930-current-canonical-unresolved-reaudit-v1"
)

EXPECTED = {
    "states": 35,
    "districts": 779,
    "villages": 600_647,
    "boundary_candidates": 654_285,
    "boundary_source_features": 654_285,
    "snapshots": 780,
    "active_snapshots": 779,
    "post_source_rows": 22_219,
    "post_deterministic": 17_498,
    "post_unresolved": 4_721,
    "legacy_unresolved": 10_052,
    "combined_unresolved": 14_773,
}

COUNT_QUERIES = {
    "states": """
        select count(*) from geography_states
        where is_active
    """,
    "districts": """
        select count(*) from geography_districts
        where is_active
    """,
    "villages": """
        select count(*) from geography_villages
        where is_active
    """,
    "boundary_candidates": """
        select count(*)
        from geography_boundary_crosswalk_candidates
    """,
    "boundary_source_features": """
        select count(*)
        from geography_boundary_source_features
    """,
    "snapshots": """
        select count(*)
        from geography_layer_readiness_snapshots
    """,
    "active_snapshots": """
        select count(*)
        from geography_layer_readiness_snapshots
        where is_active
    """,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign-dir",
        type=Path,
        default=DEFAULT_CAMPAIGN_DIR,
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
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def database_counts(database_url: str) -> dict[str, int]:
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )
    with engine.connect() as connection:
        return {
            name: int(
                connection.execute(
                    text(sql)
                ).scalar_one()
            )
            for name, sql in COUNT_QUERIES.items()
        }


def run_checked(arguments: list[str]) -> None:
    completed = subprocess.run(
        arguments,
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "SUBPROCESS_FAILED:"
            + " ".join(arguments)
            + f":{completed.returncode}"
        )


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    campaign = args.campaign_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    before = database_counts(args.database_url)

    run_checked([
        sys.executable,
        str(
            SCRIPT_DIR
            / "audit_nwdp_post_lgd_reconciliation.py"
        ),
        "--output",
        str(output),
        "--database-url",
        args.database_url,
    ])

    legacy_rows_path = (
        campaign
        / "nwdp_legacy_held_review_queue_rows.jsonl"
    )
    legacy_coverage_path = (
        output
        / "nwdp_legacy_held_resolution_coverage_manifest.json"
    )

    run_checked([
        sys.executable,
        str(
            SCRIPT_DIR
            / "build_nwdp_legacy_held_resolution_coverage_manifest.py"
        ),
        "--input",
        str(legacy_rows_path),
        "--campaign-dir",
        str(campaign),
        "--output",
        str(legacy_coverage_path),
    ])

    post_audit_path = (
        output
        / "nwdp_post_lgd_actionability_audit_v2.json"
    )
    post_rows_path = (
        output
        / "nwdp_post_lgd_actionability_rows_v2.jsonl"
    )

    post_audit = load_json(post_audit_path)
    post_rows = load_jsonl(post_rows_path)
    legacy_coverage = load_json(
        legacy_coverage_path
    )
    legacy_rows = load_jsonl(legacy_rows_path)

    post_counts = post_audit[
        "counts_by_actionability"
    ]

    post_unresolved_counts = {
        "NAME_REVIEW_REQUIRED":
            post_counts["NAME_REVIEW_REQUIRED"],
        "CANONICAL_REPARENT_REVIEW_REQUIRED":
            post_counts[
                "CANONICAL_REPARENT_REVIEW_REQUIRED"
            ],
        "ABSENT_FROM_CURRENT_LGD_REVIEW_REQUIRED":
            post_counts[
                "ABSENT_FROM_CURRENT_LGD_REVIEW_REQUIRED"
            ],
        "OTHER_STRUCTURAL_REVIEW_REQUIRED":
            post_counts[
                "OTHER_STRUCTURAL_REVIEW_REQUIRED"
            ],
    }

    post_unresolved_count = sum(
        post_unresolved_counts.values()
    )
    legacy_unresolved_count = int(
        legacy_coverage["row_count"]
    )
    combined_unresolved_count = (
        post_unresolved_count
        + legacy_unresolved_count
    )

    post_unresolved_ids = {
        row["candidate_id"]
        for row in post_rows
        if row["actionability"]
        != "DETERMINISTIC_INACTIVE_STAGING_CANDIDATE"
    }
    legacy_ids = {
        row["candidate_id"]
        for row in legacy_rows
    }
    overlap = sorted(
        post_unresolved_ids & legacy_ids
    )

    after = database_counts(args.database_url)

    checks = {
        "canonical_states_exact":
            before["states"] == EXPECTED["states"],
        "canonical_districts_exact":
            before["districts"]
            == EXPECTED["districts"],
        "canonical_villages_exact":
            before["villages"]
            == EXPECTED["villages"],
        "source_feature_count_exact":
            before["boundary_source_features"]
            == EXPECTED["boundary_source_features"],
        "candidate_count_exact":
            before["boundary_candidates"]
            == EXPECTED["boundary_candidates"],
        "snapshot_history_exact":
            before["snapshots"]
            == EXPECTED["snapshots"],
        "active_snapshot_coverage_exact":
            before["active_snapshots"]
            == EXPECTED["active_snapshots"],
        "post_lgd_audit_healthy":
            post_audit["healthy"] is True,
        "post_lgd_read_only":
            post_audit["database_writes_attempted"]
            is False,
        "post_lgd_not_authorized":
            post_audit["authorized"] is False,
        "post_lgd_source_rows_exact":
            post_audit["row_count"]
            == EXPECTED["post_source_rows"],
        "post_lgd_deterministic_exact":
            post_counts[
                "DETERMINISTIC_INACTIVE_STAGING_CANDIDATE"
            ] == EXPECTED["post_deterministic"],
        "post_lgd_unresolved_exact":
            post_unresolved_count
            == EXPECTED["post_unresolved"],
        "legacy_coverage_healthy":
            legacy_coverage["healthy"] is True,
        "legacy_coverage_read_only":
            legacy_coverage[
                "database_writes_attempted"
            ] is False,
        "legacy_coverage_not_authorized":
            legacy_coverage["status"]
            == "COVERAGE_VERIFIED_NOT_AUTHORIZED",
        "legacy_unresolved_exact":
            legacy_unresolved_count
            == EXPECTED["legacy_unresolved"],
        "candidate_populations_disjoint":
            not overlap,
        "combined_unresolved_exact":
            combined_unresolved_count
            == EXPECTED["combined_unresolved"],
        "database_counts_unchanged":
            before == after,
        "automatic_resolution_disabled": True,
        "canonical_changes_unauthorized": True,
        "runtime_activation_unauthorized": True,
        "android_changes_unauthorized": True,
    }

    summary_core = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "CURRENT_BASELINE_REAUDITED_NOT_AUTHORIZED"
            if all(checks.values())
            else "CURRENT_BASELINE_REAUDIT_FAILED"
        ),
        "healthy": all(checks.values()),
        "authorized": False,
        "database_writes_attempted": False,
        "database_before": before,
        "database_after": after,
        "post_lgd": {
            "source_rows":
                post_audit["row_count"],
            "deterministic_inactive_staging":
                post_counts[
                    "DETERMINISTIC_INACTIVE_STAGING_CANDIDATE"
                ],
            "unresolved_count":
                post_unresolved_count,
            "unresolved_counts":
                post_unresolved_counts,
            "audit_sha256":
                sha256(post_audit_path),
            "rows_sha256":
                sha256(post_rows_path),
        },
        "legacy_held": {
            "unresolved_count":
                legacy_unresolved_count,
            "queue_counts":
                legacy_coverage["queue_counts"],
            "coverage_sha256":
                sha256(legacy_coverage_path),
            "rows_sha256":
                sha256(legacy_rows_path),
        },
        "combined_unresolved_count":
            combined_unresolved_count,
        "overlap_candidate_count":
            len(overlap),
        "checks": checks,
        "policy": {
            "automatic_resolution_authorized":
                False,
            "canonical_geography_changes_authorized":
                False,
            "boundary_candidate_changes_authorized":
                False,
            "runtime_staging_authorized":
                False,
            "runtime_activation_authorized":
                False,
            "project_mapping_apply_authorized":
                False,
            "android_changes_authorized":
                False,
        },
        "next_step": (
            "Partition and prioritize the confirmed "
            "unresolved population without automatic "
            "approval."
        ),
    }

    summary_checksum = hashlib.sha256(
        json.dumps(
            summary_core,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    summary = {
        **summary_core,
        "summary_checksum": summary_checksum,
    }

    summary_path = (
        output
        / "nwdp_current_canonical_unresolved_reaudit.json"
    )
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
    )

    if not summary["healthy"]:
        raise SystemExit(
            "CURRENT CANONICAL UNRESOLVED "
            "REAUDIT FAILED"
        )

    print(
        "CURRENT CANONICAL UNRESOLVED "
        "REAUDIT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
