#!/usr/bin/env python3
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
from scripts.report_boundary_geometry_repair_classification import SOURCE_SYSTEM  # noqa: E402

SCHEMA_VERSION = "boundary_geometry_repair_tiny_fixture_apply.v1"
FIXTURE_SOURCE = "boundary_geometry_repair_tiny_fixture_regression"
REPAIR_METHOD = "TINY_FIXTURE_BOUNDARY_GEOMETRY_REPAIR_APPLY"


def jdefault(value: Any) -> str:
    return str(value)


def ensure_table(conn) -> None:
    conn.execute(text("""
        create table if not exists geography_boundary_geometry_repair_events (
          id uuid primary key,
          source_feature_id uuid not null,
          import_batch_id uuid,
          source_system varchar not null,
          state_or_ut varchar,
          district varchar,
          repair_action varchar not null,
          repair_status varchar not null,
          before_geometry_validation_status varchar,
          after_geometry_validation_status varchar,
          before_runtime_eligibility boolean,
          after_runtime_eligibility boolean,
          repair_method varchar not null,
          rollback_token varchar not null,
          dry_run_report jsonb not null default '{}'::jsonb,
          apply_report jsonb not null default '{}'::jsonb,
          rollback_report jsonb not null default '{}'::jsonb,
          applied_by varchar,
          applied_at timestamptz,
          rolled_back_by varchar,
          rolled_back_at timestamptz,
          metadata jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          is_active boolean not null default true,
          version varchar not null default 'v1.0'
        )
    """))
    conn.execute(text("""
        create unique index if not exists ux_boundary_geometry_repair_events_fixture_token
        on geography_boundary_geometry_repair_events(source_feature_id, rollback_token, repair_method)
    """))


def table_counts(conn) -> dict[str, int]:
    ensure_table(conn)
    row = conn.execute(text("""
        select
          (select count(*)::bigint from geography_boundary_geometry_repair_events) as repair_event_rows,
          (select count(*)::bigint from geography_boundary_geometry_repair_events where is_active = true) as active_repair_event_rows,
          (select count(*)::bigint from geography_boundary_geometry_repair_events where repair_method = :repair_method) as tiny_fixture_repair_event_rows,
          (select count(*)::bigint from geography_boundary_geometry_repair_events where repair_method = :repair_method and is_active = true) as active_tiny_fixture_repair_event_rows,
          (select count(*)::bigint from geography_boundary_source_features) as source_feature_rows,
          (select count(*)::bigint from geography_boundary_source_features where geometry_validation_status in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')) as valid_source_feature_rows,
          (select count(*)::bigint from geography_boundary_source_features where eligible_for_runtime_after_promotion = true) as runtime_eligible_source_feature_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates) as boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where is_active = true) as active_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_crosswalk_candidates where promotion_status = 'PROMOTED') as promoted_boundary_candidate_rows,
          (select count(*)::bigint from geography_boundary_runtime_features) as runtime_feature_rows,
          (select count(*)::bigint from geography_boundary_runtime_crosswalks) as runtime_crosswalk_rows
    """), {"repair_method": REPAIR_METHOD}).mappings().one()
    return {k: int(v or 0) for k, v in dict(row).items()}


def output_files(output_dir: Path) -> dict[str, str]:
    return {
        "json": str(output_dir / "boundary_geometry_repair_tiny_fixture_apply_audit.json"),
        "csv": str(output_dir / "boundary_geometry_repair_tiny_fixture_apply_rows.csv"),
    }


def guardrails(wrote_event: bool) -> dict[str, bool]:
    return {
        "db_writes_attempted": wrote_event,
        "repair_event_rows_written": wrote_event,
        "geometry_repair_attempted": False,
        "geometry_validation_status_changed": False,
        "source_runtime_eligibility_changed": False,
        "source_features_changed": False,
        "boundary_candidates_promoted": False,
        "boundary_candidates_activated": False,
        "runtime_boundary_features_written": False,
        "runtime_boundary_crosswalks_written": False,
        "runtime_tables_written": False,
        "runtime_lookup_enabled": False,
        "android_behavior_changed": False,
        "lgd_geography_overwritten": False,
    }


def policy() -> dict[str, Any]:
    return {
        "tiny_fixture_only": True,
        "broad_apply_supported": False,
        "target_table": "geography_boundary_geometry_repair_events",
        "source_feature_geometry_write_allowed": False,
        "geometry_validation_status_write_allowed": False,
        "source_runtime_eligibility_write_allowed": False,
        "candidate_promotion_allowed": False,
        "candidate_activation_allowed": False,
        "runtime_table_write_allowed": False,
        "runtime_lookup_enablement_allowed": False,
        "android_behavior_change_allowed": False,
    }


def write_outputs(output_dir: Path, audit: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "boundary_geometry_repair_tiny_fixture_apply_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True, default=jdefault) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "boundary_geometry_repair_tiny_fixture_apply_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "event_id", "source_feature_id", "candidate_id", "repair_action",
            "repair_status", "action", "reason", "rollback_token"
        ], extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_candidate(conn, source_feature_id: str) -> dict[str, Any] | None:
    row = conn.execute(text("""
        select
          sf.id::text as source_feature_id,
          b.id::text as import_batch_id,
          b.source_system,
          coalesce(sf.source_state_name, b.state_or_ut) as state_or_ut,
          sf.source_district_name as district,
          sf.geometry_validation_status as before_geometry_validation_status,
          coalesce(sf.eligible_for_runtime_after_promotion, false) as before_runtime_eligibility,
          sf.metadata,
          c.id::text as candidate_id
        from geography_boundary_source_features sf
        join geography_boundary_import_batches b on b.id = sf.import_batch_id
        left join geography_boundary_crosswalk_candidates c on c.source_feature_id = sf.id
        where sf.id = :source_feature_id
          and b.source_system = :source_system
        order by c.created_at nulls last, c.id
        limit 1
    """), {"source_feature_id": source_feature_id, "source_system": SOURCE_SYSTEM}).mappings().first()
    if not row:
        return None
    data = dict(row)
    metadata = data.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    data["metadata"] = metadata if isinstance(metadata, dict) else {}
    return data


def fail(output_dir: Path, args: argparse.Namespace, error: str, before: dict[str, int], after: dict[str, int], candidate=None) -> int:
    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": "TINY_FIXTURE_BOUNDARY_GEOMETRY_REPAIR_APPLY",
        "error": error,
        "source_feature_id": args.source_feature_id,
        "apply_requested": bool(args.apply),
        "rollback_requested": bool(args.rollback),
        "rollback_token": args.rollback_token or None,
        "candidate": candidate,
        "before_counts": before,
        "after_counts": after,
        "counts_unchanged": before == after,
        "policy": policy(),
        "guardrails": guardrails(False),
        "output_files": output_files(output_dir),
    }
    write_outputs(output_dir, audit, [])
    print(json.dumps(audit, indent=2, sort_keys=True, default=jdefault))
    return 1


def event_id(source_feature_id: str, rollback_token: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"agri-os:{SCHEMA_VERSION}:{source_feature_id}:{rollback_token}"))


def apply_event(conn, candidate: dict[str, Any], args: argparse.Namespace) -> tuple[int, int, list[dict[str, Any]]]:
    eid = event_id(candidate["source_feature_id"], args.rollback_token)
    result = conn.execute(text("""
        insert into geography_boundary_geometry_repair_events (
          id, source_feature_id, import_batch_id, source_system, state_or_ut, district,
          repair_action, repair_status, before_geometry_validation_status,
          after_geometry_validation_status, before_runtime_eligibility,
          after_runtime_eligibility, repair_method, rollback_token,
          dry_run_report, apply_report, applied_by, applied_at, metadata, is_active, version
        )
        values (
          :id, :source_feature_id, :import_batch_id, :source_system, :state_or_ut, :district,
          :repair_action, 'CLASSIFIED_FOR_REPAIR', :before_geometry_validation_status,
          :before_geometry_validation_status, :before_runtime_eligibility,
          :before_runtime_eligibility, :repair_method, :rollback_token,
          cast(:dry_run_report as jsonb), cast(:apply_report as jsonb), :applied_by,
          now(), cast(:metadata as jsonb), true, 'v1.0'
        )
        on conflict (source_feature_id, rollback_token, repair_method) do nothing
    """), {
        "id": eid,
        "source_feature_id": candidate["source_feature_id"],
        "import_batch_id": candidate.get("import_batch_id"),
        "source_system": candidate.get("source_system") or SOURCE_SYSTEM,
        "state_or_ut": candidate.get("state_or_ut"),
        "district": candidate.get("district"),
        "repair_action": args.repair_action,
        "before_geometry_validation_status": candidate.get("before_geometry_validation_status"),
        "before_runtime_eligibility": bool(candidate.get("before_runtime_eligibility")),
        "repair_method": REPAIR_METHOD,
        "rollback_token": args.rollback_token,
        "dry_run_report": json.dumps({"candidate": candidate, "policy": policy()}, default=jdefault),
        "apply_report": json.dumps({"schema_version": SCHEMA_VERSION, "rollback_token": args.rollback_token}, default=jdefault),
        "applied_by": args.applied_by,
        "metadata": json.dumps({"fixture_source": FIXTURE_SOURCE, "candidate_id": candidate.get("candidate_id")}, default=jdefault),
    })
    inserted = int(result.rowcount or 0)
    return inserted, 0 if inserted else 1, [{
        "event_id": eid,
        "source_feature_id": candidate["source_feature_id"],
        "candidate_id": candidate.get("candidate_id"),
        "repair_action": args.repair_action,
        "repair_status": "CLASSIFIED_FOR_REPAIR",
        "action": "INSERTED" if inserted else "SKIPPED",
        "reason": "tiny fixture repair metadata event" if inserted else "idempotent existing repair event",
        "rollback_token": args.rollback_token,
    }]


def rollback_event(conn, args: argparse.Namespace) -> tuple[int, list[dict[str, Any]]]:
    existing = [dict(r) for r in conn.execute(text("""
        select id::text as event_id, source_feature_id::text as source_feature_id,
               null::text as candidate_id, repair_action, repair_status, rollback_token
        from geography_boundary_geometry_repair_events
        where source_feature_id = :source_feature_id
          and rollback_token = :rollback_token
          and repair_method = :repair_method
          and is_active = true
    """), {
        "source_feature_id": args.source_feature_id,
        "rollback_token": args.rollback_token,
        "repair_method": REPAIR_METHOD,
    }).mappings()]
    count = conn.execute(text("""
        update geography_boundary_geometry_repair_events
        set is_active = false,
            repair_status = 'ROLLED_BACK',
            rolled_back_by = :applied_by,
            rolled_back_at = now(),
            rollback_report = jsonb_build_object('schema_version', :schema_version, 'rollback_token', :rollback_token),
            updated_at = now()
        where source_feature_id = :source_feature_id
          and rollback_token = :rollback_token
          and repair_method = :repair_method
          and is_active = true
    """), {
        "source_feature_id": args.source_feature_id,
        "rollback_token": args.rollback_token,
        "repair_method": REPAIR_METHOD,
        "applied_by": args.applied_by,
        "schema_version": SCHEMA_VERSION,
    }).rowcount or 0
    for row in existing:
        row["action"] = "ROLLED_BACK"
        row["reason"] = "tiny fixture repair event rollback"
    return int(count), existing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-feature-id", required=True)
    parser.add_argument("--output-dir", default="/tmp/boundary-geometry-repair-tiny-fixture-apply")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--enable-geometry-repair-metadata", action="store_true")
    parser.add_argument("--classification-reviewed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    parser.add_argument("--rollback-token", default="")
    parser.add_argument("--repair-action", default="REPAIR_OR_REIMPORT_INVALID_GEOMETRY")
    parser.add_argument("--applied-by", default="tiny-fixture-regression")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    engine = create_engine(load_settings_url())

    with engine.begin() as conn:
        before = table_counts(conn)
        candidate = load_candidate(conn, args.source_feature_id)
        after_failure = table_counts(conn)

        if not candidate:
            return fail(output_dir, args, "SOURCE_FEATURE_NOT_FOUND", before, after_failure)
        if candidate.get("metadata", {}).get("fixture_source") != FIXTURE_SOURCE:
            return fail(output_dir, args, "ONLY_TINY_FIXTURE_SOURCE_FEATURES_SUPPORTED", before, after_failure, candidate)
        if not args.rollback_token:
            return fail(output_dir, args, "ROLLBACK_TOKEN_REQUIRED", before, after_failure, candidate)

        if args.rollback:
            rolled_back, rows = rollback_event(conn, args)
            after = table_counts(conn)
            audit = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "healthy": True,
                "mode": "TINY_FIXTURE_BOUNDARY_GEOMETRY_REPAIR_ROLLBACK",
                "source_feature_id": args.source_feature_id,
                "rollback_token": args.rollback_token,
                "candidate": candidate,
                "summary": {"rolled_back_event_count": rolled_back},
                "before_counts": before,
                "after_counts": after,
                "policy": policy(),
                "guardrails": guardrails(rolled_back > 0),
                "output_files": output_files(output_dir),
            }
            write_outputs(output_dir, audit, rows)
            print(json.dumps(audit, indent=2, sort_keys=True, default=jdefault))
            return 0

        if not args.apply:
            return fail(output_dir, args, "EXPLICIT_APPLY_FLAG_REQUIRED", before, after_failure, candidate)
        if not args.enable_geometry_repair_metadata:
            return fail(output_dir, args, "ENABLE_GEOMETRY_REPAIR_METADATA_POLICY_FLAG_REQUIRED", before, after_failure, candidate)
        if not args.classification_reviewed:
            return fail(output_dir, args, "CLASSIFICATION_REVIEW_REQUIRED", before, after_failure, candidate)
        if not args.admin_confirmation:
            return fail(output_dir, args, "ADMIN_CONFIRMATION_REQUIRED", before, after_failure, candidate)

        inserted, skipped, rows = apply_event(conn, candidate, args)
        after = table_counts(conn)
        audit = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "healthy": True,
            "mode": "TINY_FIXTURE_BOUNDARY_GEOMETRY_REPAIR_APPLY",
            "source_feature_id": args.source_feature_id,
            "rollback_token": args.rollback_token,
            "candidate": candidate,
            "summary": {
                "planned_repair_event_count": 1,
                "inserted_repair_event_count": inserted,
                "idempotent_skipped_repair_event_count": skipped,
            },
            "before_counts": before,
            "after_counts": after,
            "policy": policy(),
            "guardrails": guardrails(inserted > 0),
            "output_files": output_files(output_dir),
        }
        write_outputs(output_dir, audit, rows)
        print(json.dumps(audit, indent=2, sort_keys=True, default=jdefault))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
