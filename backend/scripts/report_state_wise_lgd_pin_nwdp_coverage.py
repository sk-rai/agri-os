#!/usr/bin/env python3
"""Generate the corrected read-only state-wise LGD/PIN/NWDP coverage report."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
from app.core.database import engine  # noqa: E402

SCHEMA_VERSION = "state_wise_lgd_pin_nwdp_coverage.v2"
EXPECTED_VILLAGES = 600_647
EXPECTED_RUNTIME = 467_397

SNAPSHOT_SQL = """
select
 (select count(*) from geography_villages where is_active) as active_villages,
 (select count(*) from geography_village_pin_links where is_active and match_status='MATCHED') as active_pin_links,
 (select count(*) from geography_boundary_runtime_crosswalks where is_active) as active_runtime_crosswalks,
 (select count(*) from geography_boundary_crosswalk_candidates where is_active) as active_candidates,
 (select count(*) from geography_boundary_project_matches where is_active) as active_project_matches
"""

LGD_SQL = """
with pins as (
 select distinct geography_village_id as village_id from geography_village_pin_links
 where is_active and match_status='MATCHED'
), candidates as (
 select distinct c.proposed_village_id as village_id
 from geography_boundary_crosswalk_candidates c
 join geography_boundary_import_batches b on b.id=c.import_batch_id
 where b.source_system='NWDP_GSI_VILLAGE_BOUNDARY' and c.proposed_village_id is not null
), runtime as (
 select distinct x.village_id
 from geography_boundary_runtime_crosswalks x
 join geography_boundary_runtime_features f on f.id=x.runtime_feature_id and f.is_active
 where x.is_active
), base as (
 select s.lgd_code::text state_lgd_code, s.canonical_name state_name, v.id,
        (p.village_id is not null) has_pin,
        (c.village_id is not null) has_candidate_mapping,
        (r.village_id is not null) has_active_runtime,
        (c.village_id is not null or r.village_id is not null) has_effective_nwdp
 from geography_villages v
 join geography_districts d on d.id=v.district_id and d.is_active
 join geography_states s on s.id=d.state_id and s.is_active
 left join pins p on p.village_id=v.id
 left join candidates c on c.village_id=v.id
 left join runtime r on r.village_id=v.id
 where v.is_active
)
select state_lgd_code, state_name,
 count(*)::bigint lgd_villages,
 count(*) filter(where has_pin)::bigint lgd_with_pin,
 count(*) filter(where not has_pin)::bigint lgd_without_pin,
 count(*) filter(where has_candidate_mapping)::bigint lgd_with_candidate_nwdp_mapping,
 count(*) filter(where has_active_runtime)::bigint lgd_with_active_nwdp_runtime,
 count(*) filter(where has_effective_nwdp)::bigint lgd_with_effective_nwdp_mapping,
 count(*) filter(where not has_effective_nwdp)::bigint lgd_without_effective_nwdp_mapping,
 count(*) filter(where has_pin and has_effective_nwdp)::bigint fully_resolved,
 count(*) filter(where has_pin and not has_effective_nwdp)::bigint pin_only,
 count(*) filter(where not has_pin and has_effective_nwdp)::bigint nwdp_only,
 count(*) filter(where not has_pin and not has_effective_nwdp)::bigint unresolved
from base group by state_lgd_code,state_name order by state_lgd_code::int
"""

NWDP_SQL = """
with candidate_map as (
 select distinct c.source_feature_id, c.proposed_village_id village_id
 from geography_boundary_crosswalk_candidates c
 join geography_boundary_import_batches b on b.id=c.import_batch_id
 where b.source_system='NWDP_GSI_VILLAGE_BOUNDARY' and c.proposed_village_id is not null
), runtime_map as (
 select distinct c.source_feature_id, x.village_id
 from geography_boundary_runtime_crosswalks x
 join geography_boundary_runtime_features f on f.id=x.runtime_feature_id and f.is_active
 join geography_boundary_crosswalk_candidates c on c.id=x.source_candidate_id
 where x.is_active
), effective as (
 select source_feature_id,village_id from candidate_map
 union
 select source_feature_id,village_id from runtime_map
), pin_villages as (
 select distinct geography_village_id village_id from geography_village_pin_links
 where is_active and match_status='MATCHED'
), effective_status as (
 select e.source_feature_id, bool_or(p.village_id is not null) target_has_pin
 from effective e left join pin_villages p on p.village_id=e.village_id
 group by e.source_feature_id
), candidate_features as (select distinct source_feature_id from candidate_map),
runtime_features as (select distinct source_feature_id from runtime_map),
source as (
 select f.id, f.source_state_name,
        (c.source_feature_id is not null) has_candidate,
        (e.source_feature_id is not null) has_effective,
        coalesce(e.target_has_pin,false) target_has_pin,
        (r.source_feature_id is not null) has_runtime
 from geography_boundary_source_features f
 join geography_boundary_import_batches b on b.id=f.import_batch_id
 left join candidate_features c on c.source_feature_id=f.id
 left join effective_status e on e.source_feature_id=f.id
 left join runtime_features r on r.source_feature_id=f.id
 where b.source_system='NWDP_GSI_VILLAGE_BOUNDARY'
)
select source_state_name,
 count(*)::bigint nwdp_source_features,
 count(*) filter(where has_candidate)::bigint nwdp_features_with_candidate_lgd_mapping,
 count(*) filter(where has_effective)::bigint nwdp_features_with_effective_lgd_mapping,
 count(*) filter(where not has_effective)::bigint nwdp_features_without_effective_lgd_mapping,
 count(*) filter(where has_effective and target_has_pin)::bigint mapped_target_with_pin,
 count(*) filter(where has_effective and not target_has_pin)::bigint mapped_target_without_pin,
 count(*) filter(where has_runtime)::bigint nwdp_features_with_active_runtime
from source group by source_state_name order by source_state_name
"""


def rows(connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(text(sql)).mappings().all()]


def totals(items: list[dict[str, Any]], excluded: set[str]) -> dict[str, int]:
    return {key: sum(int(row[key]) for row in items) for key in items[0] if key not in excluded}


def write_csv(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(items[0]))
        writer.writeheader(); writer.writerows(items)


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args=parser.parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)
    with engine.connect() as connection:
        before=dict(connection.execute(text(SNAPSHOT_SQL)).mappings().one())
        lgd=rows(connection,LGD_SQL); nwdp=rows(connection,NWDP_SQL)
        after=dict(connection.execute(text(SNAPSHOT_SQL)).mappings().one())
    lgd_totals=totals(lgd,{"state_lgd_code","state_name"})
    nwdp_totals=totals(nwdp,{"source_state_name"})
    checks={
      "database_counts_unchanged": before==after,
      "canonical_total_exact": lgd_totals["lgd_villages"]==EXPECTED_VILLAGES,
      "runtime_total_exact": lgd_totals["lgd_with_active_nwdp_runtime"]==EXPECTED_RUNTIME,
      "four_way_partition_exact": lgd_totals["fully_resolved"]+lgd_totals["pin_only"]+lgd_totals["nwdp_only"]+lgd_totals["unresolved"]==EXPECTED_VILLAGES,
      "effective_partition_exact": lgd_totals["lgd_with_effective_nwdp_mapping"]+lgd_totals["lgd_without_effective_nwdp_mapping"]==EXPECTED_VILLAGES,
    }
    payload={"schema_version":SCHEMA_VERSION,"status":"PASSED" if all(checks.values()) else "FAILED","healthy":all(checks.values()),"read_only":True,"definitions":{"effective_nwdp_mapping":"union of candidate mapping and active runtime mapping","fully_resolved":"PIN and effective NWDP","pin_only":"PIN without effective NWDP","nwdp_only":"effective NWDP without PIN","unresolved":"neither PIN nor effective NWDP"},"checks":checks,"database_before":before,"database_after":after,"lgd_totals":lgd_totals,"nwdp_totals":nwdp_totals,"lgd_states":lgd,"nwdp_source_states":nwdp}
    (args.output_dir/"state_wise_lgd_pin_nwdp_coverage.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
    write_csv(args.output_dir/"state_wise_lgd_pin_nwdp_lgd_centric.csv",lgd)
    write_csv(args.output_dir/"state_wise_lgd_pin_nwdp_nwdp_centric.csv",nwdp)
    print(json.dumps({k:payload[k] for k in ("schema_version","status","healthy","checks","lgd_totals","nwdp_totals")},indent=2,sort_keys=True))
    if not payload["healthy"]: raise SystemExit("coverage report validation failed")
    print("STATE-WISE LGD PIN NWDP COVERAGE REPORT PASSED")
    return 0
if __name__=="__main__": raise SystemExit(main())
