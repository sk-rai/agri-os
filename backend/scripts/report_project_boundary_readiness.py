#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import text

from app.core.database import SessionLocal
from scripts.apply_nwdp_demographic_profile_import import load_settings_url


SCHEMA_VERSION = "project_boundary_readiness_report.v1"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"


def row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping if hasattr(row, "_mapping") else row)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


PROJECT_ROWS_SQL = """
with project_villages as (
    select distinct e.project_id, f.village_id
    from farmer_project_enrollments e
    join farmers f on f.id = e.farmer_id
    where e.is_active = true
      and f.is_active = true
      and f.village_id is not null

    union

    select distinct f.project_id, f.village_id
    from farmers f
    where f.is_active = true
      and f.project_id is not null
      and f.village_id is not null

    union

    select distinct p.project_id, p.village_id
    from parcels p
    where p.is_active = true
      and p.project_id is not null
      and p.village_id is not null

    union

    select distinct e.project_id, p.village_id
    from farmer_project_enrollments e
    join parcels p on p.farmer_id = e.farmer_id
    where e.is_active = true
      and p.is_active = true
      and p.village_id is not null
),
eligible_candidates as (
    select c.id, c.proposed_village_id
    from geography_boundary_import_batches b
    join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
    where b.source_system = :source_system
      and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
      and c.review_status = 'AUTO_CANDIDATE'
      and c.promotion_status = 'NOT_PROMOTED'
      and c.is_active = false
      and c.proposed_village_id is not null
),
excluded_candidates as (
    select c.id, c.proposed_village_id, c.candidate_bucket, c.review_status
    from geography_boundary_import_batches b
    join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
    where b.source_system = :source_system
      and c.promotion_status = 'NOT_PROMOTED'
      and c.is_active = false
      and c.proposed_village_id is not null
),
multi_candidate_project_villages as (
    select pv.project_id, pv.village_id, count(ec.id)::bigint as eligible_candidate_count
    from project_villages pv
    join eligible_candidates ec on ec.proposed_village_id = pv.village_id
    group by pv.project_id, pv.village_id
    having count(ec.id) > 1
),
project_rows as (
    select
        p.id::text as project_id,
        p.tenant_id::text as tenant_id,
        p.name as project_name,
        p.status::text as project_status,
        count(distinct pv.village_id)::bigint as project_village_count,
        count(distinct ec.proposed_village_id)::bigint as villages_with_eligible_boundary_count,
        (count(distinct pv.village_id) - count(distinct ec.proposed_village_id))::bigint as villages_without_eligible_boundary_count,
        count(distinct ec.id)::bigint as eligible_boundary_candidate_count,
        count(distinct exc.id) filter (where exc.review_status = 'MANUAL_REVIEW')::bigint as manual_review_candidate_count,
        count(distinct exc.id) filter (where exc.review_status = 'BLOCKED')::bigint as blocked_candidate_count,
        count(distinct exc.id) filter (where exc.candidate_bucket <> 'DIRECT_VLCODE_MATCH')::bigint as non_direct_candidate_count,
        count(distinct mpv.village_id)::bigint as multiple_eligible_candidate_village_count,
        count(distinct pm.id) filter (where pm.is_active = true)::bigint as existing_project_boundary_match_count
    from projects p
    left join project_villages pv on pv.project_id = p.id
    left join eligible_candidates ec on ec.proposed_village_id = pv.village_id
    left join excluded_candidates exc on exc.proposed_village_id = pv.village_id
    left join multi_candidate_project_villages mpv on mpv.project_id = pv.project_id and mpv.village_id = pv.village_id
    left join geography_boundary_project_matches pm on pm.project_id = p.id and pm.village_id = pv.village_id
    where p.is_active = true
    group by p.id, p.tenant_id, p.name, p.status
)
select
    *,
    case
      when project_village_count = 0 then 0
      else round(villages_with_eligible_boundary_count::numeric / project_village_count::numeric, 6)
    end as eligible_boundary_coverage_ratio,
    (project_village_count > 0 and eligible_boundary_candidate_count > 0) as ready_for_project_boundary_dry_run,
    false as ready_for_project_boundary_apply,
    false as ready_for_runtime_spatial_matching,
    false as ready_for_android_behavior_change
from project_rows
order by project_village_count desc, eligible_boundary_candidate_count desc, project_name asc
limit :limit
"""


SUMMARY_SQL = """
with project_villages as (
    select distinct e.project_id, f.village_id
    from farmer_project_enrollments e
    join farmers f on f.id = e.farmer_id
    where e.is_active = true
      and f.is_active = true
      and f.village_id is not null

    union

    select distinct f.project_id, f.village_id
    from farmers f
    where f.is_active = true
      and f.project_id is not null
      and f.village_id is not null

    union

    select distinct p.project_id, p.village_id
    from parcels p
    where p.is_active = true
      and p.project_id is not null
      and p.village_id is not null

    union

    select distinct e.project_id, p.village_id
    from farmer_project_enrollments e
    join parcels p on p.farmer_id = e.farmer_id
    where e.is_active = true
      and p.is_active = true
      and p.village_id is not null
),
eligible_candidates as (
    select c.id, c.proposed_village_id
    from geography_boundary_import_batches b
    join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
    where b.source_system = :source_system
      and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
      and c.review_status = 'AUTO_CANDIDATE'
      and c.promotion_status = 'NOT_PROMOTED'
      and c.is_active = false
      and c.proposed_village_id is not null
),
all_candidates as (
    select c.id, c.proposed_village_id, c.candidate_bucket, c.review_status, c.promotion_status, c.is_active
    from geography_boundary_import_batches b
    join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
    where b.source_system = :source_system
),
project_eligible as (
    select pv.project_id, pv.village_id, ec.id as candidate_id
    from project_villages pv
    join eligible_candidates ec on ec.proposed_village_id = pv.village_id
)
select
    (select count(*) from projects where is_active = true)::bigint as active_project_count,
    (select count(distinct project_id) from project_villages)::bigint as projects_with_villages_count,
    (select count(*) from project_villages)::bigint as project_village_link_count,
    (select count(distinct village_id) from project_villages)::bigint as distinct_project_village_count,
    (select count(distinct village_id) from project_eligible)::bigint as project_villages_with_eligible_boundary_count,
    ((select count(*) from project_villages) - (select count(distinct project_id::text || ':' || village_id::text) from project_eligible))::bigint as project_villages_without_eligible_boundary_count,
    (select count(*) from project_eligible)::bigint as project_eligible_boundary_candidate_count,
    (select count(*) from eligible_candidates)::bigint as raw_eligible_boundary_candidate_count,
    (select count(*) from all_candidates)::bigint as raw_boundary_candidate_count,
    (select count(*) from all_candidates where review_status = 'MANUAL_REVIEW')::bigint as raw_manual_review_candidate_count,
    (select count(*) from all_candidates where review_status = 'BLOCKED')::bigint as raw_blocked_candidate_count,
    (select count(*) from all_candidates where candidate_bucket <> 'DIRECT_VLCODE_MATCH')::bigint as raw_non_direct_candidate_count,
    (select count(*) from geography_boundary_project_matches where is_active = true)::bigint as active_project_boundary_match_count
"""


STATE_ROWS_SQL = """
with project_villages as (
    select distinct e.project_id, f.village_id
    from farmer_project_enrollments e
    join farmers f on f.id = e.farmer_id
    where e.is_active = true
      and f.is_active = true
      and f.village_id is not null

    union

    select distinct f.project_id, f.village_id
    from farmers f
    where f.is_active = true
      and f.project_id is not null
      and f.village_id is not null

    union

    select distinct p.project_id, p.village_id
    from parcels p
    where p.is_active = true
      and p.project_id is not null
      and p.village_id is not null

    union

    select distinct e.project_id, p.village_id
    from farmer_project_enrollments e
    join parcels p on p.farmer_id = e.farmer_id
    where e.is_active = true
      and p.is_active = true
      and p.village_id is not null
),
eligible_candidates as (
    select c.id, c.proposed_village_id
    from geography_boundary_import_batches b
    join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
    where b.source_system = :source_system
      and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
      and c.review_status = 'AUTO_CANDIDATE'
      and c.promotion_status = 'NOT_PROMOTED'
      and c.is_active = false
      and c.proposed_village_id is not null
)
select
    s.canonical_name as state_or_ut,
    s.lgd_code::text as state_lgd_code,
    count(distinct pv.project_id)::bigint as project_count,
    count(distinct pv.project_id::text || ':' || pv.village_id::text)::bigint as project_village_link_count,
    count(distinct pv.village_id)::bigint as distinct_project_village_count,
    count(distinct ec.proposed_village_id)::bigint as villages_with_eligible_boundary_count,
    count(distinct ec.id)::bigint as eligible_boundary_candidate_count
from project_villages pv
join geography_villages v on v.id = pv.village_id
join geography_districts d on d.id = v.district_id
join geography_states s on s.id = d.state_id
left join eligible_candidates ec on ec.proposed_village_id = pv.village_id
group by s.canonical_name, s.lgd_code
order by project_village_link_count desc, state_or_ut asc
"""


GAP_SAMPLE_SQL = """
with project_villages as (
    select distinct e.project_id, f.village_id
    from farmer_project_enrollments e
    join farmers f on f.id = e.farmer_id
    where e.is_active = true
      and f.is_active = true
      and f.village_id is not null

    union

    select distinct f.project_id, f.village_id
    from farmers f
    where f.is_active = true
      and f.project_id is not null
      and f.village_id is not null

    union

    select distinct p.project_id, p.village_id
    from parcels p
    where p.is_active = true
      and p.project_id is not null
      and p.village_id is not null

    union

    select distinct e.project_id, p.village_id
    from farmer_project_enrollments e
    join parcels p on p.farmer_id = e.farmer_id
    where e.is_active = true
      and p.is_active = true
      and p.village_id is not null
),
eligible_candidates as (
    select c.id, c.proposed_village_id
    from geography_boundary_import_batches b
    join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
    where b.source_system = :source_system
      and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
      and c.review_status = 'AUTO_CANDIDATE'
      and c.promotion_status = 'NOT_PROMOTED'
      and c.is_active = false
      and c.proposed_village_id is not null
)
select
    p.id::text as project_id,
    p.name as project_name,
    s.canonical_name as state_or_ut,
    d.canonical_name as district,
    v.lgd_code::text as village_lgd_code,
    v.canonical_name as village_name
from project_villages pv
join projects p on p.id = pv.project_id
join geography_villages v on v.id = pv.village_id
join geography_districts d on d.id = v.district_id
join geography_states s on s.id = d.state_id
left join eligible_candidates ec on ec.proposed_village_id = pv.village_id
where p.is_active = true
  and ec.id is null
order by p.name asc, s.canonical_name asc, d.canonical_name asc, v.canonical_name asc
limit :sample_limit
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only project boundary readiness report.")
    parser.add_argument("--output-dir", default="/tmp/project-boundary-readiness")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--sample-limit", type=int, default=100)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    load_settings_url()
    db = SessionLocal()
    try:
        project_rows = [
            row_to_dict(row)
            for row in db.execute(
                text(PROJECT_ROWS_SQL),
                {"source_system": SOURCE_SYSTEM, "limit": args.limit},
            )
        ]
        summary = row_to_dict(
            db.execute(text(SUMMARY_SQL), {"source_system": SOURCE_SYSTEM}).one()
        )
        state_rows = [
            row_to_dict(row)
            for row in db.execute(text(STATE_ROWS_SQL), {"source_system": SOURCE_SYSTEM})
        ]
        gap_samples = [
            row_to_dict(row)
            for row in db.execute(
                text(GAP_SAMPLE_SQL),
                {"source_system": SOURCE_SYSTEM, "sample_limit": args.sample_limit},
            )
        ]
    finally:
        db.close()

    project_village_links = int(summary["project_village_link_count"] or 0)
    eligible_project_links = int(summary["project_eligible_boundary_candidate_count"] or 0)
    raw_eligible = int(summary["raw_eligible_boundary_candidate_count"] or 0)

    readiness = {
        "ready_for_admin_review": True,
        "ready_for_project_boundary_dry_run": project_village_links > 0 and raw_eligible > 0,
        "ready_for_project_boundary_apply": False,
        "ready_for_selected_boundary_runtime_promotion": False,
        "ready_for_runtime_spatial_matching": False,
        "ready_for_android_behavior_change": False,
    }

    guardrails = {
        "db_writes_attempted": False,
        "project_boundary_matches_written": False,
        "boundary_candidates_activated": False,
        "boundary_candidates_promoted": False,
        "runtime_boundary_features_written": False,
        "runtime_lookup_enabled": False,
        "android_behavior_changed": False,
        "lgd_geography_overwritten": False,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "mode": "READ_ONLY_PROJECT_BOUNDARY_READINESS_REPORT",
        "claim_boundary": "This report is read-only. It summarizes active project village coverage against eligible NWDP boundary candidates, but does not write project matches, promote candidates, enable runtime spatial lookup, overwrite LGD geography, or change Android behavior.",
        "source_system": SOURCE_SYSTEM,
        "summary": summary,
        "readiness": readiness,
        "guardrails": guardrails,
        "project_rows": project_rows,
        "state_rows": state_rows,
        "gap_samples": gap_samples,
        "output_files": {
            "json": str(output_dir / "project_boundary_readiness_report.json"),
            "project_csv": str(output_dir / "project_boundary_readiness_by_project.csv"),
            "state_csv": str(output_dir / "project_boundary_readiness_by_state.csv"),
            "gap_sample_csv": str(output_dir / "project_boundary_readiness_gap_samples.csv"),
        },
        "recommended_next_steps": [
            "Review projects with low eligible boundary coverage.",
            "Use the existing project preview endpoint for project-level inspection.",
            "Keep apply disabled until dry-run, explicit policy flag, audit outputs, and rollback/supersession plan are in place.",
            "Do not enable Android or runtime spatial lookup from this report.",
        ],
    }

    json_path = output_dir / "project_boundary_readiness_report.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")

    write_csv(
        output_dir / "project_boundary_readiness_by_project.csv",
        project_rows,
        [
            "project_id",
            "tenant_id",
            "project_name",
            "project_status",
            "project_village_count",
            "villages_with_eligible_boundary_count",
            "villages_without_eligible_boundary_count",
            "eligible_boundary_candidate_count",
            "manual_review_candidate_count",
            "blocked_candidate_count",
            "non_direct_candidate_count",
            "multiple_eligible_candidate_village_count",
            "existing_project_boundary_match_count",
            "eligible_boundary_coverage_ratio",
            "ready_for_project_boundary_dry_run",
            "ready_for_project_boundary_apply",
            "ready_for_runtime_spatial_matching",
            "ready_for_android_behavior_change",
        ],
    )
    write_csv(
        output_dir / "project_boundary_readiness_by_state.csv",
        state_rows,
        [
            "state_or_ut",
            "state_lgd_code",
            "project_count",
            "project_village_link_count",
            "distinct_project_village_count",
            "villages_with_eligible_boundary_count",
            "eligible_boundary_candidate_count",
        ],
    )
    write_csv(
        output_dir / "project_boundary_readiness_gap_samples.csv",
        gap_samples,
        [
            "project_id",
            "project_name",
            "state_or_ut",
            "district",
            "village_lgd_code",
            "village_name",
        ],
    )

    print(json.dumps({
        "healthy": True,
        "schema_version": SCHEMA_VERSION,
        "summary": summary,
        "readiness": readiness,
        "outputs": report["output_files"],
    }, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
