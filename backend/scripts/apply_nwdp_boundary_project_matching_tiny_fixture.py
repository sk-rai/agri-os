#!/usr/bin/env python3
"""Tiny-fixture apply for NWDP boundary project matching.

This is intentionally NOT a broad project-boundary apply. It only allows
fixture-marked projects created by regression tests. It writes
geography_boundary_project_matches, proves idempotency, supports rollback by
deactivating fixture matches, and never promotes candidates, writes runtime
tables, enables lookup, overwrites LGD, or changes Android behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, text  # noqa: E402

from scripts.apply_nwdp_demographic_profile_import import load_settings_url  # noqa: E402
from scripts.plan_nwdp_boundary_project_matching_apply_dry_run import build_plan  # noqa: E402


SCHEMA_VERSION = "nwdp_boundary_project_matching_tiny_fixture_apply.v1"
FIXTURE_SOURCE = "nwdp_boundary_project_matching_tiny_fixture_regression"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
MATCH_SOURCE = "TINY_FIXTURE_PROJECT_MATCHING_APPLY"


def json_default(value: Any) -> str:
    return str(value)


def deterministic_match_id(project_id: str, candidate_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"agri-os:{SCHEMA_VERSION}:{project_id}:{candidate_id}"))


def table_counts(conn) -> dict[str, int]:
    row = conn.execute(text("""
        select
          (select count(*)::bigint from geography_boundary_project_matches) as project_match_rows,
          (select count(*)::bigint from geography_boundary_project_matches where is_active = true) as active_project_match_rows,
          (select count(*)::bigint from geography_boundary_project_matches where match_source = :match_source) as tiny_fixture_project_match_rows,
          (select count(*)::bigint from geography_boundary_project_matches where match_source = :match_source and is_active = true) as active_tiny_fixture_project_match_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where is_active = true) as active_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as promoted_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_runtime_features) as runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_features where is_active = true) as active_runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks) as runtime_crosswalk_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks where is_active = true) as active_runtime_crosswalk_rows
    """), {"match_source": MATCH_SOURCE}).mappings().one()
    return {key: int(value or 0) for key, value in dict(row).items()}


def load_project(conn, project_id: str) -> dict[str, Any] | None:
    row = conn.execute(text("""
        select id::text as project_id, tenant_id, name, status, geography_scope
        from projects
        where id = :project_id
    """), {"project_id": project_id}).mappings().first()
    return dict(row) if row else None


def normalize_scope(scope: Any) -> dict[str, Any]:
    if isinstance(scope, dict):
        return scope
    if isinstance(scope, str):
        try:
            parsed = json.loads(scope)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "match_id",
        "project_id",
        "tenant_id",
        "village_id",
        "boundary_candidate_id",
        "source_system",
        "match_source",
        "match_status",
        "action",
        "reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fail_audit(
    output_dir: Path,
    error: str,
    args: argparse.Namespace,
    before: dict[str, int],
    after: dict[str, int],
    dry_run: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
) -> int:
    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": "TINY_FIXTURE_PROJECT_BOUNDARY_MATCHING_APPLY",
        "error": error,
        "project": project,
        "project_id": args.project_id or None,
        "apply_requested": bool(args.apply),
        "rollback_requested": bool(args.rollback),
        "enable_project_boundary_apply_requested": bool(args.enable_project_boundary_apply),
        "dry_run_confirmed": bool(args.dry_run_confirmed),
        "admin_confirmation": bool(args.admin_confirmation),
        "rollback_token": args.rollback_token or None,
        "dry_run": dry_run,
        "before_counts": before,
        "after_counts": after,
        "counts_unchanged": before == after,
        "guardrails": base_guardrails(project_boundary_matches_written=False),
        "output_files": output_files(output_dir),
    }
    write_outputs(output_dir, audit, [])
    print(json.dumps(audit, indent=2, sort_keys=True, default=json_default))
    return 1


def output_files(output_dir: Path) -> dict[str, str]:
    return {
        "json": str(output_dir / "project_boundary_tiny_fixture_apply_audit.json"),
        "csv": str(output_dir / "project_boundary_tiny_fixture_apply_rows.csv"),
    }


def base_guardrails(project_boundary_matches_written: bool) -> dict[str, bool]:
    return {
        "db_writes_attempted": project_boundary_matches_written,
        "project_boundary_matches_written": project_boundary_matches_written,
        "boundary_candidates_activated": False,
        "boundary_candidates_promoted": False,
        "runtime_boundary_features_written": False,
        "runtime_boundary_crosswalks_written": False,
        "runtime_tables_written": False,
        "runtime_spatial_matching_changed": False,
        "lookup_api_enabled": False,
        "android_behavior_changed": False,
        "lgd_geography_overwritten": False,
    }


def write_outputs(output_dir: Path, audit: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "project_boundary_tiny_fixture_apply_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True, default=json_default) + "\n",
        encoding="utf-8",
    )
    write_csv(output_dir / "project_boundary_tiny_fixture_apply_rows.csv", rows)


def rollback_matches(conn, project_id: str, rollback_token: str, actor: str) -> tuple[int, list[dict[str, Any]]]:
    existing = conn.execute(text("""
        select
          id::text as match_id,
          project_id::text as project_id,
          tenant_id,
          village_id::text as village_id,
          boundary_candidate_id::text as boundary_candidate_id,
          source_system,
          match_source,
          match_status
        from geography_boundary_project_matches
        where project_id = :project_id
          and rollback_token = :rollback_token
          and match_source = :match_source
          and is_active = true
        order by created_at, id
    """), {
        "project_id": project_id,
        "rollback_token": rollback_token,
        "match_source": MATCH_SOURCE,
    }).mappings().all()

    rows = []
    for row in existing:
        rows.append({**dict(row), "action": "ROLLED_BACK", "reason": "fixture rollback/supersession"})

    updated = conn.execute(text("""
        update geography_boundary_project_matches
        set
          is_active = false,
          match_status = 'ROLLED_BACK',
          rolled_back_by = :actor,
          rolled_back_at = now(),
          rollback_report = jsonb_build_object(
            'schema_version', :schema_version,
            'rollback_token', :rollback_token,
            'rolled_back_by', :actor,
            'rolled_back_at', now()
          ),
          updated_at = now()
        where project_id = :project_id
          and rollback_token = :rollback_token
          and match_source = :match_source
          and is_active = true
    """), {
        "project_id": project_id,
        "rollback_token": rollback_token,
        "match_source": MATCH_SOURCE,
        "actor": actor,
        "schema_version": SCHEMA_VERSION,
    }).rowcount or 0

    return int(updated), rows


def apply_matches(conn, project: dict[str, Any], dry_run: dict[str, Any], args: argparse.Namespace) -> tuple[int, int, list[dict[str, Any]]]:
    selected = dry_run.get("selected_candidate_samples", [])[: args.limit]
    inserted = 0
    skipped = 0
    rows: list[dict[str, Any]] = []

    apply_report = {
        "schema_version": SCHEMA_VERSION,
        "mode": "TINY_FIXTURE_PROJECT_BOUNDARY_MATCHING_APPLY",
        "rollback_token": args.rollback_token,
        "selected_count": len(selected),
        "applied_by": args.applied_by,
    }

    for candidate in selected:
        candidate_id = candidate["candidate_id"]
        village_id = candidate["proposed_village_id"]
        match_id = deterministic_match_id(project["project_id"], candidate_id)

        result = conn.execute(text("""
            insert into geography_boundary_project_matches (
              id,
              tenant_id,
              project_id,
              village_id,
              boundary_candidate_id,
              source_system,
              match_source,
              match_status,
              applied_by,
              applied_at,
              rollback_token,
              dry_run_report,
              apply_report,
              metadata,
              is_active,
              created_at,
              updated_at,
              version
            )
            values (
              :id,
              :tenant_id,
              :project_id,
              :village_id,
              :boundary_candidate_id,
              :source_system,
              :match_source,
              'APPLIED',
              :applied_by,
              now(),
              :rollback_token,
              cast(:dry_run_report as jsonb),
              cast(:apply_report as jsonb),
              cast(:metadata as jsonb),
              true,
              now(),
              now(),
              'v1.0'
            )
            on conflict (id) do nothing
        """), {
            "id": match_id,
            "tenant_id": project["tenant_id"],
            "project_id": project["project_id"],
            "village_id": village_id,
            "boundary_candidate_id": candidate_id,
            "source_system": SOURCE_SYSTEM,
            "match_source": MATCH_SOURCE,
            "applied_by": args.applied_by,
            "rollback_token": args.rollback_token,
            "dry_run_report": json.dumps(dry_run, default=json_default),
            "apply_report": json.dumps(apply_report, default=json_default),
            "metadata": json.dumps({
                "fixture_source": FIXTURE_SOURCE,
                "candidate": candidate,
                "project_geography_scope": project.get("geography_scope"),
            }, default=json_default),
        })

        if result.rowcount:
            inserted += 1
            action = "INSERTED"
            reason = "tiny fixture apply inserted active project boundary match"
        else:
            skipped += 1
            action = "SKIPPED"
            reason = "idempotent existing match id"

        rows.append({
            "match_id": match_id,
            "project_id": project["project_id"],
            "tenant_id": project["tenant_id"],
            "village_id": village_id,
            "boundary_candidate_id": candidate_id,
            "source_system": SOURCE_SYSTEM,
            "match_source": MATCH_SOURCE,
            "match_status": "APPLIED",
            "action": action,
            "reason": reason,
        })

    return inserted, skipped, rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Tiny-fixture NWDP boundary project matching apply.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--output-dir", default="/tmp/nwdp-boundary-project-matching-tiny-fixture-apply")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--enable-project-boundary-apply", action="store_true")
    parser.add_argument("--dry-run-confirmed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    parser.add_argument("--rollback-token", default="")
    parser.add_argument("--applied-by", default="tiny-fixture-regression")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(load_settings_url())
    with engine.begin() as conn:
        before = table_counts(conn)
        project = load_project(conn, args.project_id)
        after_for_failure = table_counts(conn)

        if not project:
            return fail_audit(output_dir, "PROJECT_NOT_FOUND", args, before, after_for_failure, project=project)

        scope = normalize_scope(project.get("geography_scope"))
        project["geography_scope"] = scope

        if scope.get("source") != FIXTURE_SOURCE:
            return fail_audit(output_dir, "ONLY_TINY_FIXTURE_PROJECTS_SUPPORTED", args, before, after_for_failure, project=project)
        if not args.rollback_token:
            return fail_audit(output_dir, "ROLLBACK_TOKEN_REQUIRED", args, before, after_for_failure, project=project)

        dry_run = build_plan(args.project_id, args.limit)

        if args.rollback:
            rolled_back, rows = rollback_matches(conn, args.project_id, args.rollback_token, args.applied_by)
            after = table_counts(conn)
            audit = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "healthy": True,
                "mode": "TINY_FIXTURE_PROJECT_BOUNDARY_MATCHING_ROLLBACK",
                "project": project,
                "rollback_token": args.rollback_token,
                "rollback_count": rolled_back,
                "dry_run": dry_run,
                "before_counts": before,
                "after_counts": after,
                "guardrails": base_guardrails(project_boundary_matches_written=rolled_back > 0),
                "readiness": {
                    "ready_for_project_boundary_apply": False,
                    "ready_for_runtime_spatial_matching": False,
                    "ready_for_lookup_api_enablement": False,
                    "ready_for_android_behavior_change": False,
                },
                "output_files": output_files(output_dir),
            }
            write_outputs(output_dir, audit, rows)
            print(json.dumps(audit, indent=2, sort_keys=True, default=json_default))
            return 0

        if not args.apply:
            return fail_audit(output_dir, "EXPLICIT_APPLY_FLAG_REQUIRED", args, before, table_counts(conn), dry_run, project)
        if not args.enable_project_boundary_apply:
            return fail_audit(output_dir, "ENABLE_PROJECT_BOUNDARY_APPLY_POLICY_FLAG_REQUIRED", args, before, table_counts(conn), dry_run, project)
        if not args.dry_run_confirmed:
            return fail_audit(output_dir, "DRY_RUN_CONFIRMATION_REQUIRED", args, before, table_counts(conn), dry_run, project)
        if not args.admin_confirmation:
            return fail_audit(output_dir, "ADMIN_CONFIRMATION_REQUIRED", args, before, table_counts(conn), dry_run, project)
        if not dry_run.get("healthy"):
            return fail_audit(output_dir, "DRY_RUN_UNHEALTHY", args, before, table_counts(conn), dry_run, project)
        if int(dry_run.get("summary", {}).get("dry_run_candidate_selection_count") or 0) <= 0:
            return fail_audit(output_dir, "NO_DRY_RUN_CANDIDATES_SELECTED", args, before, table_counts(conn), dry_run, project)

        inserted, skipped, rows = apply_matches(conn, project, dry_run, args)
        after = table_counts(conn)

        audit = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "healthy": True,
            "mode": "TINY_FIXTURE_PROJECT_BOUNDARY_MATCHING_APPLY",
            "project": project,
            "apply_requested": True,
            "enable_project_boundary_apply_requested": True,
            "dry_run_confirmed": True,
            "admin_confirmation": True,
            "rollback_token": args.rollback_token,
            "dry_run": dry_run,
            "summary": {
                "planned_match_count": len(dry_run.get("selected_candidate_samples", [])[: args.limit]),
                "inserted_match_count": inserted,
                "idempotent_skipped_match_count": skipped,
                "active_project_boundary_match_delta": after["active_project_match_rows"] - before["active_project_match_rows"],
                "project_boundary_match_delta": after["project_match_rows"] - before["project_match_rows"],
            },
            "before_counts": before,
            "after_counts": after,
            "policy": {
                "tiny_fixture_only": True,
                "broad_apply_supported": False,
                "target_table": "geography_boundary_project_matches",
                "unique_match_id_policy": "uuid5(project_id, boundary_candidate_id)",
                "rollback_strategy": "set is_active=false and match_status='ROLLED_BACK'",
                "runtime_boundary_promotion_allowed": False,
                "runtime_lookup_enablement_allowed": False,
                "android_behavior_change_allowed": False,
            },
            "guardrails": base_guardrails(project_boundary_matches_written=inserted > 0),
            "readiness": {
                "ready_for_project_boundary_apply": False,
                "ready_for_tiny_fixture_project_boundary_apply": True,
                "ready_for_runtime_spatial_matching": False,
                "ready_for_lookup_api_enablement": False,
                "ready_for_android_behavior_change": False,
            },
            "output_files": output_files(output_dir),
        }
        write_outputs(output_dir, audit, rows)
        print(json.dumps(audit, indent=2, sort_keys=True, default=json_default))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
