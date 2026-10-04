#!/usr/bin/env python3
"""Validate or transactionally load a canonical-village local-evidence snapshot."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.core.database import engine

SCHEMA_VERSION = "canonical_village_resolution_evidence_snapshot_load.v1"
SOURCE_SCHEMA = "canonical_unresolved_local_evidence_delta.v1"
CONFIRMATION = "LOAD CANONICAL LOCAL EVIDENCE SNAPSHOT"
EXPECTED = {
    "items": 7493,
    "deterministic": 70,
    "high_confidence": 70,
    "ambiguous": 47,
    "blocked": 7306,
    "collision_rows": 15,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--packet-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation")
    args = parser.parse_args()

    source_manifest_path = args.evidence_dir / "canonical_unresolved_local_evidence_delta.json"
    villages_path = args.evidence_dir / "canonical_unresolved_villages.csv"
    pairs_path = args.evidence_dir / "canonical_unresolved_candidate_pairs.csv"
    packet_manifest_path = args.packet_dir / "single_candidate_review_packet.json"
    packet_path = args.packet_dir / "single_candidate_review_packet.csv"

    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    packet_manifest = json.loads(packet_manifest_path.read_text(encoding="utf-8"))
    villages = read_csv(villages_path)
    pairs = read_csv(pairs_path)
    packet = read_csv(packet_path)

    best_pair: dict[str, dict[str, str]] = {}
    for row in sorted(pairs, key=lambda item: (item["village_id"], int(item["match_rank"]), int(item["candidate_number"]))):
        best_pair.setdefault(row["village_id"], row)
    packet_by_village = {row["village_id"]: row for row in packet}

    items = []
    for village in villages:
        pair = best_pair.get(village["village_id"])
        review = packet_by_village.get(village["village_id"])
        disposition = village["disposition"]
        if review:
            eligibility = review["review_eligibility"]
        elif disposition == "AMBIGUOUS_MULTIPLE_CANDIDATES":
            eligibility = "AMBIGUOUS_REVIEW_REQUIRED"
        else:
            eligibility = "AUTHORITATIVE_EVIDENCE_REQUIRED"
        items.append({
            "id": str(uuid4()),
            "village_id": village["village_id"],
            "disposition": disposition,
            "candidate_count": int(village["candidate_count"]),
            "best_match_rank": int(village["best_match_rank"]) if village["best_match_rank"] else None,
            "best_match_basis": pair["match_basis"] if pair else None,
            "source_feature_id": pair["source_feature_id"] if review else None,
            "source_candidate_village_count": int(review["source_candidate_village_count"]) if review else 0,
            "source_collision": review["source_collision"] == "True" if review else False,
            "review_eligibility": eligibility,
            "prior_candidate_evidence": pair["prior_candidate_evidence"] if review and pair else None,
        })

    dispositions = Counter(row["disposition"] for row in items)
    checks = {
        "source_manifest_valid": source_manifest.get("schema_version") == SOURCE_SCHEMA
        and source_manifest.get("healthy") is True
        and source_manifest.get("database_before") == source_manifest.get("database_after"),
        "packet_manifest_valid": packet_manifest.get("healthy") is True
        and packet_manifest.get("policy", {}).get("database_accessed") is False,
        "items_exact": len(items) == EXPECTED["items"],
        "villages_unique": len({row["village_id"] for row in items}) == EXPECTED["items"],
        "deterministic_exact": dispositions["DETERMINISTIC_SINGLE_REVIEW"] == EXPECTED["deterministic"],
        "high_confidence_exact": dispositions["HIGH_CONFIDENCE_SINGLE_REVIEW"] == EXPECTED["high_confidence"],
        "ambiguous_exact": dispositions["AMBIGUOUS_MULTIPLE_CANDIDATES"] == EXPECTED["ambiguous"],
        "blocked_exact": dispositions["NO_LOCAL_CANDIDATE"] == EXPECTED["blocked"],
        "collision_rows_exact": sum(row["source_collision"] for row in items) == EXPECTED["collision_rows"],
        "automatic_resolution_prohibited": all(
            row.get("automatic_resolution_authorized", False) is False for row in items
        ),
    }
    if args.apply and args.confirmation != CONFIRMATION:
        raise SystemExit(f"--apply requires --confirmation '{CONFIRMATION}'")

    before = {}
    after = {}
    snapshot_id = str(uuid4())
    with engine.connect() as connection:
        transaction = connection.begin()
        before = dict(connection.execute(text("""
          select
            (select count(*) from geography_village_resolution_evidence_snapshots) snapshot_count,
            (select count(*) from geography_village_resolution_evidence_items) item_count,
            (select count(*) from geography_village_resolution_evidence_snapshots where is_active) active_snapshot_count
        """)).mappings().one())
        if args.apply and all(checks.values()):
            connection.execute(text("""
              update geography_village_resolution_evidence_snapshots
              set is_active=false where is_active
            """))
            connection.execute(text("""
              insert into geography_village_resolution_evidence_snapshots(
                id,schema_version,source_manifest_sha256,source_candidate_pairs_sha256,
                canonical_unresolved_count,item_count,is_active,activated_at,metadata
              ) values (
                :id,:schema,:manifest_hash,:pairs_hash,:unresolved,:items,true,now(),
                cast(:metadata as jsonb)
              )
            """), {
                "id": snapshot_id,
                "schema": SOURCE_SCHEMA,
                "manifest_hash": digest(source_manifest_path),
                "pairs_hash": digest(pairs_path),
                "unresolved": EXPECTED["items"],
                "items": len(items),
                "metadata": json.dumps({"packet_manifest_sha256": digest(packet_manifest_path)}),
            })
            insert_sql = text("""
              insert into geography_village_resolution_evidence_items(
                id,snapshot_id,village_id,disposition,candidate_count,best_match_rank,
                best_match_basis,source_feature_id,source_candidate_village_count,
                source_collision,review_eligibility,prior_candidate_evidence,
                automatic_resolution_authorized
              ) values (
                :id,:snapshot_id,:village_id,:disposition,:candidate_count,:best_match_rank,
                :best_match_basis,cast(:source_feature_id as uuid),:source_candidate_village_count,
                :source_collision,:review_eligibility,:prior_candidate_evidence,false
              )
            """)
            connection.execute(insert_sql, [{**row, "snapshot_id": snapshot_id} for row in items])
            transaction.commit()
        else:
            transaction.rollback()
    with engine.connect() as connection:
        after = dict(connection.execute(text("""
          select
            (select count(*) from geography_village_resolution_evidence_snapshots) snapshot_count,
            (select count(*) from geography_village_resolution_evidence_items) item_count,
            (select count(*) from geography_village_resolution_evidence_snapshots where is_active) active_snapshot_count
        """)).mappings().one())

    checks["dry_run_unchanged"] = args.apply or before == after
    checks["apply_row_count_exact"] = not args.apply or (
        after["item_count"] - before["item_count"] == EXPECTED["items"]
        and after["active_snapshot_count"] == 1
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "APPLIED" if args.apply and all(checks.values()) else "DRY_RUN_PASSED" if all(checks.values()) else "FAILED",
        "healthy": all(checks.values()),
        "apply_requested": args.apply,
        "snapshot_id": snapshot_id if args.apply else None,
        "checks": checks,
        "database_before": before,
        "database_after": after,
        "counts": {"items": len(items), "dispositions": dict(sorted(dispositions.items()))},
        "policy": {
            "canonical_geography_changed": False,
            "pin_links_changed": False,
            "runtime_changed": False,
            "project_resolution_changed": False,
            "android_changed": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["healthy"]:
        raise SystemExit("CANONICAL VILLAGE RESOLUTION EVIDENCE SNAPSHOT LOAD FAILED")
    print("CANONICAL VILLAGE RESOLUTION EVIDENCE SNAPSHOT LOAD PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
