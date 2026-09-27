#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal

SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_code_sql(expression: str) -> str:
    return (
        "case when ltrim(coalesce("
        + expression
        + ", ''), '0') = '' then '0' "
        + "else ltrim(coalesce("
        + expression
        + ", ''), '0') end"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "/tmp/"
            "nwdp-boundary-project-manual-hierarchy-candidates.json"
        ),
    )
    args = parser.parse_args()

    source_state_code = normalized_code_sql(
        "sf.source_stcode"
    )
    source_district_code = normalized_code_sql(
        "sf.source_dtcode"
    )
    source_village_code = normalized_code_sql(
        "sf.source_vlcode"
    )
    canonical_state_code = normalized_code_sql(
        "gs.lgd_code"
    )
    canonical_district_code = normalized_code_sql(
        "gd_source.lgd_code"
    )
    canonical_village_code = normalized_code_sql(
        "gv.lgd_code"
    )

    query = text(f"""
        with candidate_targets as (
          select
            c.id::text as candidate_id,
            c.source_feature_id::text as source_feature_id,
            c.import_batch_id::text as import_batch_id,
            c.candidate_bucket,
            c.review_status,
            c.promotion_status,
            c.is_active as candidate_is_active,
            b.source_system,
            b.state_or_ut,
            sf.source_feature_index,
            sf.source_stcode,
            sf.source_dtcode,
            sf.source_sdcode,
            sf.source_vlcode,
            sf.source_state_name,
            sf.source_district_name,
            sf.source_subdistrict_name,
            sf.source_village_name,
            sf.geometry_validation_status,
            sf.source_geometry_hash,
            gs.id::text as canonical_state_id,
            gs.lgd_code as canonical_state_code,
            gs.canonical_name as canonical_state_name,
            gv.id::text as canonical_village_id,
            gv.lgd_code as canonical_village_code,
            gv.canonical_name as canonical_village_name,
            gd.id::text as canonical_district_id,
            gd.lgd_code as canonical_district_code,
            gd.canonical_name as canonical_district_name,
            gb.id::text as canonical_block_id,
            gb.lgd_code as canonical_block_code,
            gb.canonical_name as canonical_block_name,
            count(*) over (
              partition by c.id
            )::integer as canonical_target_count
          from geography_boundary_crosswalk_candidates c
          join geography_boundary_import_batches b
            on b.id = c.import_batch_id
          join geography_boundary_source_features sf
            on sf.id = c.source_feature_id
          join geography_states gs
            on gs.is_active = true
           and {canonical_state_code} = {source_state_code}
          join geography_villages gv
            on gv.is_active = true
           and {canonical_village_code} = {source_village_code}
          join geography_districts gd
            on gd.id = gv.district_id
           and gd.state_id = gs.id
           and gd.is_active = true
          left join geography_blocks gb
            on gb.id = gv.block_id
           and gb.is_active = true
          left join geography_districts gd_source
            on gd_source.state_id = gs.id
           and gd_source.is_active = true
           and {canonical_district_code} = {source_district_code}
          where b.source_system = :source_system
            and c.candidate_bucket = 'BLOCKED_SOURCE_CAVEAT'
            and c.review_status = 'BLOCKED'
            and c.promotion_status = 'NOT_PROMOTED'
            and c.is_active = false
            and c.proposed_village_id is null
            and sf.geometry_validation_status = 'VALIDATED'
            and gd_source.id is null
        )
        select *
        from candidate_targets
        order by candidate_id
    """)

    db = SessionLocal()
    try:
        rows = [
            dict(row)
            for row in db.execute(
                query,
                {"source_system": SOURCE_SYSTEM},
            ).mappings().all()
        ]
    finally:
        db.close()

    candidate_ids = [row["candidate_id"] for row in rows]
    feature_ids = [row["source_feature_id"] for row in rows]
    target_ids = [row["canonical_village_id"] for row in rows]

    counts_by_state = dict(sorted(Counter(
        row["canonical_state_name"] for row in rows
    ).items()))
    counts_by_source_district = dict(sorted(Counter(
        (
            row["source_state_name"],
            row["source_district_name"],
            row["source_dtcode"],
        )
        for row in rows
    ).items()))

    checks = {
        "row_count_exact": len(rows) == 3,
        "candidate_identity_unique":
            len(candidate_ids) == len(set(candidate_ids)),
        "source_feature_identity_unique":
            len(feature_ids) == len(set(feature_ids)),
        "canonical_target_identity_unique":
            len(target_ids) == len(set(target_ids)),
        "single_canonical_target_per_candidate": all(
            row["canonical_target_count"] == 1
            for row in rows
        ),
        "source_district_missing_from_current_hierarchy": True,
        "same_state_village_code_match": all(
            str(row["source_stcode"]).lstrip("0")
            == str(row["canonical_state_code"]).lstrip("0")
            and str(row["source_vlcode"]).lstrip("0")
            == str(row["canonical_village_code"]).lstrip("0")
            for row in rows
        ),
        "geometry_validated": all(
            row["geometry_validation_status"] == "VALIDATED"
            for row in rows
        ),
        "candidates_remain_blocked": all(
            row["candidate_bucket"] == "BLOCKED_SOURCE_CAVEAT"
            and row["review_status"] == "BLOCKED"
            and row["promotion_status"] == "NOT_PROMOTED"
            and row["candidate_is_active"] is False
            for row in rows
        ),
        "no_database_writes": True,
        "not_authorized": True,
    }
    healthy = all(checks.values())

    payload_core = {
        "schema_version":
            "nwdp_boundary_project_manual_hierarchy_candidates.v1",
        "status":
            "READ_MODEL_READY_NOT_AUTHORIZED"
            if healthy else "READ_MODEL_INVALID",
        "healthy": healthy,
        "source_system": SOURCE_SYSTEM,
        "row_count": len(rows),
        "counts_by_state": counts_by_state,
        "counts_by_source_district": {
            "|".join(key): value
            for key, value in counts_by_source_district.items()
        },
        "checks": checks,
        "policy": {
            "candidate_rows_mutated": False,
            "canonical_geography_mutated": False,
            "global_equivalence_created": False,
            "project_manual_mapping_tenant_scoped": True,
            "project_manual_mapping_project_scoped": True,
            "project_mapping_apply_authorized": False,
            "runtime_activation_authorized": False,
        },
        "database_writes_attempted": False,
        "items": rows,
    }
    checksum = sha256_bytes(
        json.dumps(
            payload_core,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )
    payload = {
        **payload_core,
        "summary_checksum": checksum,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
