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


SCHEMA_VERSION = "project_boundary_readiness_report.v2"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"


def row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping if hasattr(row, "_mapping") else row)


def scalar(db, sql: str, params: dict[str, Any] | None = None) -> int:
    value = db.execute(text(sql), params or {}).scalar()
    return int(value or 0)


def rows(db, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [row_to_dict(r) for r in db.execute(text(sql), params or {})]


def write_csv(path: Path, data: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            writer.writerow(row)


def as_list(scope: dict[str, Any], key: str) -> list[str]:
    value = scope.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_state_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    aliases = {
        "up": "uttar pradesh",
        "u.p.": "uttar pradesh",
        "uttar pradesh": "uttar pradesh",
    }
    return aliases.get(normalized, normalized)


def project_direct_village_count(db, project_id: str) -> int:
    return scalar(
        db,
        """
        with direct_project_villages as (
            select distinct f.village_id
            from farmer_project_enrollments e
            join farmers f on f.id = e.farmer_id
            where e.project_id = :project_id
              and e.is_active = true
              and f.is_active = true
              and f.village_id is not null

            union

            select distinct f.village_id
            from farmers f
            where f.project_id = :project_id
              and f.is_active = true
              and f.village_id is not null

            union

            select distinct p.village_id
            from parcels p
            where p.project_id = :project_id
              and p.is_active = true
              and p.village_id is not null

            union

            select distinct p.village_id
            from farmer_project_enrollments e
            join parcels p on p.farmer_id = e.farmer_id
            where e.project_id = :project_id
              and e.is_active = true
              and p.is_active = true
              and p.village_id is not null
        )
        select count(*)::bigint from direct_project_villages
        """,
        {"project_id": project_id},
    )


def build_scope_village_sql(scope: dict[str, Any]) -> tuple[str | None, dict[str, Any], list[str]]:
    params: dict[str, Any] = {}
    parts: list[str] = []
    sources: list[str] = []

    village_lgd_codes = as_list(scope, "village_lgd_codes")
    village_names = as_list(scope, "village_names")
    pin_codes = as_list(scope, "pin_codes")
    district_lgd_codes = as_list(scope, "district_lgd_codes")
    district_names = as_list(scope, "districts")
    state_lgd_codes = as_list(scope, "state_lgd_codes") + as_list(scope, "state_ids")
    state_name = normalize_state_name(scope.get("state") if isinstance(scope.get("state"), str) else None)

    # Precedence rule:
    # village/PIN/district scopes are narrow scopes. State is only a qualifier for them.
    # State-wide expansion is used only when no narrower scope exists.
    has_narrow_scope = bool(village_lgd_codes or village_names or pin_codes or district_lgd_codes or district_names)

    if village_lgd_codes:
        params["village_lgd_codes"] = village_lgd_codes
        parts.append("""
            select distinct v.id as village_id, 'village_lgd_code' as source
            from geography_villages v
            where v.is_active = true
              and v.lgd_code::text = any(:village_lgd_codes)
        """)
        sources.append("village_lgd_code")

    if village_names:
        params["village_names"] = [name.lower() for name in village_names]
        parts.append("""
            select distinct v.id as village_id, 'village_name_exact' as source
            from geography_villages v
            join geography_districts d on d.id = v.district_id
            join geography_states s on s.id = d.state_id
            where v.is_active = true
              and lower(v.canonical_name) = any(:village_names)
              and (
                :state_name is null
                or lower(s.canonical_name) = :state_name
              )
        """)
        sources.append("village_name_exact")

    if pin_codes:
        params["pin_codes"] = pin_codes
        parts.append("""
            select distinct vpl.geography_village_id as village_id, 'pin_code' as source
            from geography_village_pin_links vpl
            join geography_villages v on v.id = vpl.geography_village_id
            join geography_districts d on d.id = v.district_id
            join geography_states s on s.id = d.state_id
            where vpl.is_active = true
              and vpl.match_status = 'MATCHED'
              and vpl.pin_code = any(:pin_codes)
              and (
                :state_name is null
                or lower(s.canonical_name) = :state_name
              )
        """)
        sources.append("pin_code")

    if district_lgd_codes:
        params["district_lgd_codes"] = district_lgd_codes
        parts.append("""
            select distinct v.id as village_id, 'district_lgd_code' as source
            from geography_districts d
            join geography_states s on s.id = d.state_id
            join geography_villages v on v.district_id = d.id
            where d.is_active = true
              and v.is_active = true
              and d.lgd_code::text = any(:district_lgd_codes)
              and (
                :state_name is null
                or lower(s.canonical_name) = :state_name
              )
        """)
        sources.append("district_lgd_code")

    if district_names:
        params["district_names"] = [name.lower() for name in district_names]
        parts.append("""
            select distinct v.id as village_id, 'district_name' as source
            from geography_districts d
            join geography_states s on s.id = d.state_id
            join geography_villages v on v.district_id = d.id
            where d.is_active = true
              and v.is_active = true
              and lower(d.canonical_name) = any(:district_names)
              and (
                :state_name is null
                or lower(s.canonical_name) = :state_name
              )
        """)
        sources.append("district_name")

    if state_lgd_codes and not has_narrow_scope:
        params["state_lgd_codes"] = state_lgd_codes
        parts.append("""
            select distinct v.id as village_id, 'state_lgd_code' as source
            from geography_states s
            join geography_districts d on d.state_id = s.id
            join geography_villages v on v.district_id = d.id
            where s.is_active = true
              and d.is_active = true
              and v.is_active = true
              and s.lgd_code::text = any(:state_lgd_codes)
        """)
        sources.append("state_lgd_code")

    if state_name and not has_narrow_scope and not state_lgd_codes:
        parts.append("""
            select distinct v.id as village_id, 'state_name' as source
            from geography_states s
            join geography_districts d on d.state_id = s.id
            join geography_villages v on v.district_id = d.id
            where s.is_active = true
              and d.is_active = true
              and v.is_active = true
              and lower(s.canonical_name) = :state_name
        """)
        sources.append("state_name")

    params["state_name"] = state_name

    if not parts:
        return None, params, []

    return "\nunion\n".join(parts), params, sources


def scope_counts_for_project(db, project_id: str, scope: dict[str, Any]) -> dict[str, Any]:
    village_sql, params, sources = build_scope_village_sql(scope)
    if not village_sql:
        return {
            "scope_resolved_village_count": 0,
            "scope_villages_with_eligible_boundary_count": 0,
            "scope_eligible_boundary_candidate_count": 0,
            "scope_manual_review_candidate_count": 0,
            "scope_blocked_candidate_count": 0,
            "scope_non_direct_candidate_count": 0,
            "scope_sources": [],
        }

    params = dict(params)
    params["source_system"] = SOURCE_SYSTEM

    counts = row_to_dict(
        db.execute(
            text(f"""
            with scope_villages as (
                {village_sql}
            ),
            eligible_candidates as (
                select c.id, c.proposed_village_id
                from geography_boundary_import_batches b
                join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id
                join geography_boundary_source_features f on f.id = c.source_feature_id
                where b.source_system = :source_system
                  and f.geometry_validation_status = 'VALIDATED'
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
            )
            select
              count(distinct sv.village_id)::bigint as scope_resolved_village_count,
              count(distinct ec.proposed_village_id)::bigint as scope_villages_with_eligible_boundary_count,
              count(distinct ec.id)::bigint as scope_eligible_boundary_candidate_count,
              count(distinct exc.id) filter (where exc.review_status = 'MANUAL_REVIEW')::bigint as scope_manual_review_candidate_count,
              count(distinct exc.id) filter (where exc.review_status = 'BLOCKED')::bigint as scope_blocked_candidate_count,
              count(distinct exc.id) filter (where exc.candidate_bucket <> 'DIRECT_VLCODE_MATCH')::bigint as scope_non_direct_candidate_count
            from scope_villages sv
            left join eligible_candidates ec on ec.proposed_village_id = sv.village_id
            left join excluded_candidates exc on exc.proposed_village_id = sv.village_id
            """),
            params,
        ).one()
    )
    counts["scope_sources"] = sorted(set(sources))
    return counts


def gap_samples_for_project(db, project_id: str, project_name: str, scope: dict[str, Any], sample_limit: int) -> list[dict[str, Any]]:
    village_sql, params, _sources = build_scope_village_sql(scope)
    if not village_sql:
        return []

    params = dict(params)
    params["source_system"] = SOURCE_SYSTEM
    params["sample_limit"] = sample_limit

    return rows(
        db,
        f"""
        with scope_villages as (
            {village_sql}
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
          :project_id as project_id,
          :project_name as project_name,
          s.canonical_name as state_or_ut,
          d.canonical_name as district,
          v.lgd_code::text as village_lgd_code,
          v.canonical_name as village_name
        from scope_villages sv
        join geography_villages v on v.id = sv.village_id
        join geography_districts d on d.id = v.district_id
        join geography_states s on s.id = d.state_id
        left join eligible_candidates ec on ec.proposed_village_id = sv.village_id
        where ec.id is null
        order by s.canonical_name, d.canonical_name, v.canonical_name
        limit :sample_limit
        """,
        {**params, "project_id": project_id, "project_name": project_name},
    )


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
        projects = rows(
            db,
            """
            select
              id::text as project_id,
              tenant_id::text as tenant_id,
              name as project_name,
              status::text as project_status,
              is_active,
              geography_scope
            from projects
            where is_active = true
            order by created_at desc nulls last, name asc
            limit :limit
            """,
            {"limit": args.limit},
        )

        raw_summary = row_to_dict(
            db.execute(
                text("""
                select
                  (select count(*) from projects where is_active = true)::bigint as active_project_count,
                  (select count(*) from projects where is_active = true and geography_scope is not null and geography_scope::text not in ('{}', 'null', '[]'))::bigint as projects_with_non_empty_geography_scope_count,
                  (select count(*) from geography_boundary_project_matches where is_active = true)::bigint as active_project_boundary_match_count,
                  (select count(*) from geography_boundary_import_batches b join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id where b.source_system = :source_system)::bigint as raw_boundary_candidate_count,
                  (select count(*) from geography_boundary_import_batches b join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id join geography_boundary_source_features f on f.id = c.source_feature_id where b.source_system = :source_system and f.geometry_validation_status = 'VALIDATED' and c.candidate_bucket = 'DIRECT_VLCODE_MATCH' and c.review_status = 'AUTO_CANDIDATE' and c.promotion_status = 'NOT_PROMOTED' and c.is_active = false and c.proposed_village_id is not null)::bigint as raw_eligible_boundary_candidate_count,
                  (select count(*) from geography_boundary_import_batches b join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id where b.source_system = :source_system and c.review_status = 'MANUAL_REVIEW')::bigint as raw_manual_review_candidate_count,
                  (select count(*) from geography_boundary_import_batches b join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id where b.source_system = :source_system and c.review_status = 'BLOCKED')::bigint as raw_blocked_candidate_count,
                  (select count(*) from geography_boundary_import_batches b join geography_boundary_crosswalk_candidates c on c.import_batch_id = b.id where b.source_system = :source_system and c.candidate_bucket <> 'DIRECT_VLCODE_MATCH')::bigint as raw_non_direct_candidate_count
                """),
                {"source_system": SOURCE_SYSTEM},
            ).one()
        )

        project_rows: list[dict[str, Any]] = []
        gap_samples: list[dict[str, Any]] = []

        for project in projects:
            scope = project.get("geography_scope") or {}
            if isinstance(scope, str):
                try:
                    scope = json.loads(scope)
                except Exception:
                    scope = {}
            if not isinstance(scope, dict):
                scope = {}

            direct_village_count = project_direct_village_count(db, project["project_id"])
            scope_counts = scope_counts_for_project(db, project["project_id"], scope)

            project_village_count = max(
                direct_village_count,
                int(scope_counts["scope_resolved_village_count"] or 0),
            )
            eligible_candidate_count = int(scope_counts["scope_eligible_boundary_candidate_count"] or 0)
            villages_with_eligible = int(scope_counts["scope_villages_with_eligible_boundary_count"] or 0)
            villages_without_eligible = max(project_village_count - villages_with_eligible, 0)

            match_count = scalar(
                db,
                """
                select count(*)::bigint
                from geography_boundary_project_matches
                where project_id = :project_id
                  and is_active = true
                """,
                {"project_id": project["project_id"]},
            )

            row = {
                **project,
                "geography_scope": scope,
                "direct_project_village_count": direct_village_count,
                "scope_resolved_village_count": int(scope_counts["scope_resolved_village_count"] or 0),
                "scope_sources": ",".join(scope_counts["scope_sources"]),
                "project_village_count": project_village_count,
                "villages_with_eligible_boundary_count": villages_with_eligible,
                "villages_without_eligible_boundary_count": villages_without_eligible,
                "eligible_boundary_candidate_count": eligible_candidate_count,
                "manual_review_candidate_count": int(scope_counts["scope_manual_review_candidate_count"] or 0),
                "blocked_candidate_count": int(scope_counts["scope_blocked_candidate_count"] or 0),
                "non_direct_candidate_count": int(scope_counts["scope_non_direct_candidate_count"] or 0),
                "multiple_eligible_candidate_village_count": 0,
                "existing_project_boundary_match_count": match_count,
                "eligible_boundary_coverage_ratio": round(villages_with_eligible / project_village_count, 6) if project_village_count else 0,
                "ready_for_project_boundary_dry_run": project_village_count > 0 and eligible_candidate_count > 0,
                "ready_for_project_boundary_apply": False,
                "ready_for_runtime_spatial_matching": False,
                "ready_for_android_behavior_change": False,
            }
            project_rows.append(row)

            if len(gap_samples) < args.sample_limit and project_village_count > villages_with_eligible:
                remaining = args.sample_limit - len(gap_samples)
                gap_samples.extend(gap_samples_for_project(db, project["project_id"], project["project_name"], scope, remaining))

        project_rows.sort(
            key=lambda r: (
                -int(r["project_village_count"] or 0),
                -int(r["eligible_boundary_candidate_count"] or 0),
                str(r["project_name"]),
            )
        )

        state_acc: dict[tuple[str, str], dict[str, Any]] = {}
        for sample_project in project_rows:
            scope = sample_project.get("geography_scope") or {}
            village_sql, params, _sources = build_scope_village_sql(scope)
            if not village_sql:
                continue
            for r in rows(
                db,
                f"""
                with scope_villages as ({village_sql})
                select
                  s.canonical_name as state_or_ut,
                  s.lgd_code::text as state_lgd_code,
                  count(distinct sv.village_id)::bigint as distinct_project_village_count
                from scope_villages sv
                join geography_villages v on v.id = sv.village_id
                join geography_districts d on d.id = v.district_id
                join geography_states s on s.id = d.state_id
                group by s.canonical_name, s.lgd_code
                """,
                params,
            ):
                key = (r["state_or_ut"], r["state_lgd_code"])
                item = state_acc.setdefault(
                    key,
                    {
                        "state_or_ut": r["state_or_ut"],
                        "state_lgd_code": r["state_lgd_code"],
                        "project_count": 0,
                        "project_village_link_count": 0,
                    },
                )
                item["project_count"] += 1
                item["project_village_link_count"] += int(r["distinct_project_village_count"] or 0)

        state_rows = sorted(state_acc.values(), key=lambda r: (-r["project_village_link_count"], r["state_or_ut"]))

    finally:
        db.close()

    summary = {
        **raw_summary,
        "project_count_in_report": len(project_rows),
        "projects_with_villages_count": sum(1 for r in project_rows if int(r["project_village_count"] or 0) > 0),
        "project_village_link_count": sum(int(r["project_village_count"] or 0) for r in project_rows),
        "distinct_project_village_count": sum(int(r["project_village_count"] or 0) for r in project_rows),
        "project_villages_with_eligible_boundary_count": sum(int(r["villages_with_eligible_boundary_count"] or 0) for r in project_rows),
        "project_villages_without_eligible_boundary_count": sum(int(r["villages_without_eligible_boundary_count"] or 0) for r in project_rows),
        "project_eligible_boundary_candidate_count": sum(int(r["eligible_boundary_candidate_count"] or 0) for r in project_rows),
        "projects_ready_for_project_boundary_dry_run_count": sum(1 for r in project_rows if r["ready_for_project_boundary_dry_run"]),
    }

    readiness = {
        "ready_for_admin_review": True,
        "ready_for_project_boundary_dry_run": summary["projects_ready_for_project_boundary_dry_run_count"] > 0,
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
        "claim_boundary": "This report is read-only. It resolves project geography_scope and persisted project-village links against eligible NWDP boundary candidates, but does not write project matches, promote candidates, enable runtime spatial lookup, overwrite LGD geography, or change Android behavior.",
        "source_system": SOURCE_SYSTEM,
        "scope_resolution_policy": {
            "state_scope_used_only_without_narrower_scope": True,
            "state_field_qualifies_district_and_village_name_scopes": True,
            "supported_scope_keys": [
                "village_lgd_codes",
                "village_names",
                "pin_codes",
                "district_lgd_codes",
                "districts",
                "state_lgd_codes",
                "state_ids",
                "state",
            ],
        },
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
    }

    (output_dir / "project_boundary_readiness_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    project_csv_rows = [{**r, "geography_scope": json.dumps(r.get("geography_scope", {}), sort_keys=True)} for r in project_rows]

    write_csv(
        output_dir / "project_boundary_readiness_by_project.csv",
        project_csv_rows,
        [
            "project_id",
            "tenant_id",
            "project_name",
            "project_status",
            "direct_project_village_count",
            "scope_resolved_village_count",
            "scope_sources",
            "project_village_count",
            "villages_with_eligible_boundary_count",
            "villages_without_eligible_boundary_count",
            "eligible_boundary_candidate_count",
            "manual_review_candidate_count",
            "blocked_candidate_count",
            "non_direct_candidate_count",
            "existing_project_boundary_match_count",
            "eligible_boundary_coverage_ratio",
            "ready_for_project_boundary_dry_run",
            "ready_for_project_boundary_apply",
            "ready_for_runtime_spatial_matching",
            "ready_for_android_behavior_change",
            "geography_scope",
        ],
    )
    write_csv(
        output_dir / "project_boundary_readiness_by_state.csv",
        state_rows,
        ["state_or_ut", "state_lgd_code", "project_count", "project_village_link_count"],
    )
    write_csv(
        output_dir / "project_boundary_readiness_gap_samples.csv",
        gap_samples,
        ["project_id", "project_name", "state_or_ut", "district", "village_lgd_code", "village_name"],
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
