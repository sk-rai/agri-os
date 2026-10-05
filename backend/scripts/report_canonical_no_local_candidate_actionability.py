#!/usr/bin/env python3
"""Classify 7,306 canonical villages with no local NWDP candidate."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.core.database import engine
from scripts.report_project_village_resolution_worklist import (
    NWDP_UNMAPPED_SQL,
    SNAPSHOT_SQL,
    SOURCE_SYSTEM,
)

SCHEMA_VERSION = "canonical_no_local_candidate_actionability.v1"
EXPECTED_BLOCKED = 7306
EXPECTED_ACTIONABILITY = {
    "NO_NWDP_STATE_SOURCE": 421,
    "DISTRICT_IDENTITY_ALIGNMENT_REQUIRED": 824,
    "BLOCK_TEHSIL_ALIGNMENT_REQUIRED": 2122,
    "SAME_PARENT_NAME_RESEARCH_REQUIRED": 3939,
}
DEFAULT_INPUT = ROOT / "data/staged/core_stack/promotion_review/20261004-canonical-unresolved-local-evidence-delta-v1/canonical_unresolved_villages.csv"


def norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def read_blocked(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            row for row in csv.DictReader(handle)
            if row["disposition"] == "NO_LOCAL_CANDIDATE"
        ]


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    blocked = read_blocked(args.input)

    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("select set_config('statement_timeout','900000ms',true)"))
        before = dict(connection.execute(text(SNAPSHOT_SQL)).mappings().one())
        sources = [
            dict(row) for row in connection.execute(
                text(NWDP_UNMAPPED_SQL), {"source_system": SOURCE_SYSTEM}
            ).mappings()
        ]
        after = dict(connection.execute(text(SNAPSHOT_SQL)).mappings().one())
        transaction.rollback()

    states_by_code = Counter()
    states_by_name = Counter()
    districts_by_code = Counter()
    districts_by_name = Counter()
    blocks_by_code = Counter()
    blocks_by_name = Counter()
    for source in sources:
        state_code = str(source["source_stcode"] or "")
        state_name = norm(source["source_state_name"])
        district_code = str(source["source_dtcode"] or "")
        district_name = norm(source["source_district_name"])
        block_code = str(source["source_sdcode"] or source["source_bkcode"] or "")
        block_name = norm(source["source_block_name"] or source["source_subdistrict_name"])
        if state_code:
            states_by_code[state_code] += 1
        if state_name:
            states_by_name[state_name] += 1
        if state_code and district_code:
            districts_by_code[(state_code, district_code)] += 1
        if state_name and district_name:
            districts_by_name[(state_name, district_name)] += 1
        if state_code and district_code and block_code:
            blocks_by_code[(state_code, district_code, block_code)] += 1
        if state_name and district_name and block_name:
            blocks_by_name[(state_name, district_name, block_name)] += 1

    rows = []
    for village in blocked:
        state_code = str(village["state_lgd_code"])
        state_name = norm(village["state_name"])
        district_code = str(village["district_lgd_code"])
        district_name = norm(village["district_name"])
        block_name = norm(village["block_name"])
        state_sources = max(states_by_code[state_code], states_by_name[state_name])
        district_sources = max(
            districts_by_code[(state_code, district_code)],
            districts_by_name[(state_name, district_name)],
        )
        same_block_sources = blocks_by_name[(state_name, district_name, block_name)]
        if state_sources == 0:
            actionability = "NO_NWDP_STATE_SOURCE"
            next_evidence = "AUTHORITATIVE_STATE_OR_LGD_SOURCE_REQUIRED"
        elif district_sources == 0:
            actionability = "DISTRICT_IDENTITY_ALIGNMENT_REQUIRED"
            next_evidence = "DISTRICT_CODE_NAME_CROSSWALK_REQUIRED"
        elif same_block_sources == 0:
            actionability = "BLOCK_TEHSIL_ALIGNMENT_REQUIRED"
            next_evidence = "BLOCK_TEHSIL_CROSSWALK_REQUIRED"
        else:
            actionability = "SAME_PARENT_NAME_RESEARCH_REQUIRED"
            next_evidence = "GOVERNED_NAME_TRANSLITERATION_OR_LGD_EXPORT_REQUIRED"
        rows.append({
            **village,
            "actionability": actionability,
            "next_evidence": next_evidence,
            "unmapped_state_source_count": state_sources,
            "unmapped_district_source_count": district_sources,
            "unmapped_same_block_source_count": same_block_sources,
            "fuzzy_matching_used": False,
            "automatic_resolution_authorized": False,
        })

    counts = Counter(row["actionability"] for row in rows)
    state_counts = defaultdict(Counter)
    for row in rows:
        state_counts[(row["state_lgd_code"], row["state_name"])][row["actionability"]] += 1
    state_rows = []
    for (code, name), values in sorted(state_counts.items(), key=lambda item: int(item[0][0])):
        state_rows.append({
            "state_lgd_code": code,
            "state_name": name,
            "blocked_total": sum(values.values()),
            "NO_NWDP_STATE_SOURCE": values["NO_NWDP_STATE_SOURCE"],
            "DISTRICT_IDENTITY_ALIGNMENT_REQUIRED": values["DISTRICT_IDENTITY_ALIGNMENT_REQUIRED"],
            "BLOCK_TEHSIL_ALIGNMENT_REQUIRED": values["BLOCK_TEHSIL_ALIGNMENT_REQUIRED"],
            "SAME_PARENT_NAME_RESEARCH_REQUIRED": values["SAME_PARENT_NAME_RESEARCH_REQUIRED"],
        })

    checks = {
        "blocked_total_exact": len(rows) == EXPECTED_BLOCKED,
        "actionability_partition_exact": sum(counts.values()) == EXPECTED_BLOCKED,
        "actionability_counts_exact": dict(counts) == EXPECTED_ACTIONABILITY,
        "database_counts_unchanged": before == after,
        "fuzzy_matching_prohibited": all(not row["fuzzy_matching_used"] for row in rows),
        "automatic_resolution_prohibited": all(
            not row["automatic_resolution_authorized"] for row in rows
        ),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASSED" if all(checks.values()) else "FAILED",
        "healthy": all(checks.values()),
        "read_only": True,
        "scope": {
            "canonical_no_local_candidate": len(rows),
            "unmapped_nwdp_sources": len(sources),
        },
        "actionability": dict(counts),
        "checks": checks,
        "database_before": before,
        "database_after": after,
        "policy": {
            "fuzzy_matching_used": False,
            "automatic_resolution_authorized": False,
            "canonical_changes_authorized": False,
            "pin_link_changes_authorized": False,
            "runtime_changes_authorized": False,
            "android_changes_authorized": False,
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "canonical_no_local_candidate_actionability.csv", rows)
    write_csv(args.output_dir / "canonical_no_local_candidate_state_summary.csv", state_rows)
    (args.output_dir / "canonical_no_local_candidate_actionability.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    if not payload["healthy"]:
        raise SystemExit("CANONICAL NO-LOCAL-CANDIDATE ACTIONABILITY FAILED")
    print("CANONICAL NO-LOCAL-CANDIDATE ACTIONABILITY PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
