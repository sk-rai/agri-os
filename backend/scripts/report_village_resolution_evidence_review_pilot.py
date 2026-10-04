#!/usr/bin/env python3
"""Build a deterministic, read-only ten-row village evidence review pilot."""
import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.database import SessionLocal

SCHEMA_VERSION = "village_resolution_evidence_review_pilot.v1"
PILOT_SIZE = 10
PRIOR_EVIDENCE = "BLOCKED_SOURCE_CAVEAT:APPROVED_FOR_PROMOTION:NOT_PROMOTED"


def database_counts(db):
    return dict(db.execute(text("""
      select
        (select count(*) from geography_villages where is_active) active_villages,
        (select count(*) from geography_village_pin_links where is_active) active_pin_links,
        (select count(*) from geography_boundary_runtime_crosswalks where is_active) active_runtime_crosswalks,
        (select count(*) from geography_village_resolution_evidence_reviews) review_rows,
        (select count(*) from geography_village_resolution_evidence_review_events) review_events
    """)).mappings().one())


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    db = SessionLocal()
    try:
        before = database_counts(db)
        rows = [dict(row) for row in db.execute(text("""
          select
            snapshot.id::text snapshot_id,
            snapshot.schema_version snapshot_schema_version,
            snapshot.source_manifest_sha256,
            snapshot.source_candidate_pairs_sha256,
            item.id::text evidence_item_id,
            item.village_id::text village_id,
            village.lgd_code::text village_lgd_code,
            village.canonical_name village_name,
            block.lgd_code::text block_lgd_code,
            block.canonical_name block_name,
            district.lgd_code::text district_lgd_code,
            district.canonical_name district_name,
            state.lgd_code::text state_lgd_code,
            state.canonical_name state_name,
            item.source_feature_id::text source_feature_id,
            source.source_vlcode,
            source.source_village_name,
            source.source_block_name,
            source.source_subdistrict_name,
            source.source_district_name,
            source.source_state_name,
            item.disposition,
            item.best_match_rank,
            item.best_match_basis,
            item.source_candidate_village_count,
            item.source_collision,
            item.review_eligibility,
            item.prior_candidate_evidence
          from geography_village_resolution_evidence_items item
          join geography_village_resolution_evidence_snapshots snapshot
            on snapshot.id=item.snapshot_id and snapshot.is_active=true
          join geography_villages village on village.id=item.village_id
          join geography_blocks block on block.id=village.block_id
          join geography_districts district on district.id=village.district_id
          join geography_states state on state.id=district.state_id
          join geography_boundary_source_features source
            on source.id=item.source_feature_id
          where item.review_eligibility='TWO_SESSION_REVIEW_ELIGIBLE'
            and item.source_collision=false
            and item.best_match_rank=1
            and not exists (
              select 1 from geography_village_resolution_evidence_reviews review
              where review.snapshot_id=item.snapshot_id
                and review.evidence_item_id=item.id
            )
          order by
            case item.disposition
              when 'DETERMINISTIC_SINGLE_REVIEW' then 0 else 1
            end,
            state.lgd_code::integer,
            district.lgd_code::integer,
            block.lgd_code::integer,
            village.lgd_code::integer,
            item.source_feature_id
          limit :limit
        """), {"limit": PILOT_SIZE}).mappings()]
        after = database_counts(db)
    finally:
        db.close()

    for index, row in enumerate(rows, start=1):
        row["pilot_sequence"] = index
        row["primary_decision"] = ""
        row["primary_reviewer_id"] = ""
        row["primary_notes"] = ""
        row["second_decision"] = ""
        row["second_reviewer_id"] = ""
        row["second_notes"] = ""
        row["application_authorized"] = False

    checks = {
        "pilot_size_exact": len(rows) == PILOT_SIZE,
        "villages_unique": len({row["village_id"] for row in rows}) == len(rows),
        "sources_unique": len({row["source_feature_id"] for row in rows}) == len(rows),
        "rank_one_only": all(row["best_match_rank"] == 1 for row in rows),
        "two_session_eligible_only": all(
            row["review_eligibility"] == "TWO_SESSION_REVIEW_ELIGIBLE"
            for row in rows
        ),
        "no_source_collisions": all(row["source_collision"] is False for row in rows),
        "prior_evidence_recorded": all(
            bool(row["prior_candidate_evidence"]) for row in rows
        ),
        "review_fields_blank": all(
            not row[field]
            for row in rows
            for field in (
                "primary_decision", "primary_reviewer_id", "primary_notes",
                "second_decision", "second_reviewer_id", "second_notes",
            )
        ),
        "database_counts_unchanged": before == after,
    }
    healthy = all(checks.values())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "village_resolution_evidence_review_pilot.csv"
    write_csv(csv_path, rows)
    csv_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASSED" if healthy else "FAILED",
        "healthy": healthy,
        "read_only": True,
        "selection_policy": {
            "pilot_size": PILOT_SIZE,
            "review_eligibility": "TWO_SESSION_REVIEW_ELIGIBLE",
            "best_match_rank": 1,
            "source_collision": False,
            "prior_candidate_evidence": "RECORDED_AND_PRIORITIZED_NOT_FILTERED",
            "existing_reviews_excluded": True,
            "deterministic_order": [
                "disposition_strength", "state_lgd_code", "district_lgd_code",
                "block_lgd_code", "village_lgd_code", "source_feature_id",
            ],
        },
        "source_evidence": {
            "snapshot_id": rows[0]["snapshot_id"] if rows else None,
            "snapshot_schema_version": rows[0]["snapshot_schema_version"] if rows else None,
            "source_manifest_sha256": rows[0]["source_manifest_sha256"] if rows else None,
            "source_candidate_pairs_sha256": rows[0]["source_candidate_pairs_sha256"] if rows else None,
            "pilot_csv_sha256": csv_sha256,
        },
        "checks": checks,
        "database_before": before,
        "database_after": after,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "policy": {
            "review_decisions_created": False,
            "automatic_application_authorized": False,
            "canonical_geography_changed": False,
            "pin_links_changed": False,
            "runtime_changed": False,
            "android_changed": False,
        },
        "rows": rows,
    }
    (args.output_dir / "village_resolution_evidence_review_pilot.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    if not healthy:
        print("VILLAGE RESOLUTION EVIDENCE REVIEW PILOT FAILED")
        return 1
    print("VILLAGE RESOLUTION EVIDENCE REVIEW PILOT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
