#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402

OUT_DIR = Path("/tmp/boundary-geometry-repair-tiny-fixture-apply-regression")
ROLLBACK_TOKEN = "boundary-geometry-repair-tiny-fixture-regression"
FIXTURE_SOURCE = "boundary_geometry_repair_tiny_fixture_regression"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
REPAIR_METHOD = "TINY_FIXTURE_BOUNDARY_GEOMETRY_REPAIR_APPLY"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str))
    if not condition:
        raise AssertionError(label)


def ensure_table(db) -> None:
    db.execute(text("""
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
    db.execute(text("""
        create unique index if not exists ux_boundary_geometry_repair_events_fixture_token
        on geography_boundary_geometry_repair_events(source_feature_id, rollback_token, repair_method)
    """))
    db.commit()


def counts(db) -> dict[str, int]:
    ensure_table(db)
    row = db.execute(text("""
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


def as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def choose_source_feature(db) -> dict:
    row = db.execute(text("""
        select
          sf.id::text as source_feature_id,
          c.id::text as candidate_id,
          sf.metadata as old_metadata
        from geography_boundary_import_batches b
        join geography_boundary_source_features sf on sf.import_batch_id = b.id
        join geography_boundary_crosswalk_candidates c on c.source_feature_id = sf.id
        where b.source_system = :source_system
          and coalesce(sf.geometry_validation_status, 'UNKNOWN') not in ('VALID', 'VALIDATED', 'VALID_WITH_WARNINGS')
          and coalesce(sf.eligible_for_runtime_after_promotion, false) = false
          and c.candidate_bucket = 'DIRECT_VLCODE_MATCH'
          and c.review_status = 'AUTO_CANDIDATE'
          and c.promotion_status = 'NOT_PROMOTED'
          and c.is_active = false
        order by c.created_at, c.id
        limit 1
    """), {"source_system": SOURCE_SYSTEM}).mappings().first()
    if not row:
        raise RuntimeError("No invalid/runtime-ineligible fixture source feature candidate found")
    return dict(row)


def mark_fixture(db, feature: dict) -> None:
    metadata = as_dict(feature.get("old_metadata"))
    metadata["fixture_source"] = FIXTURE_SOURCE
    metadata["fixture_regression_candidate_id"] = feature["candidate_id"]
    db.execute(text("""
        update geography_boundary_source_features
        set metadata = cast(:metadata as jsonb), updated_at = now()
        where id = :source_feature_id
    """), {
        "source_feature_id": feature["source_feature_id"],
        "metadata": json.dumps(metadata, sort_keys=True),
    })
    db.commit()


def restore_fixture(db, feature: dict) -> None:
    db.execute(text("""
        delete from geography_boundary_geometry_repair_events
        where source_feature_id = :source_feature_id
           or rollback_token = :rollback_token
           or repair_method = :repair_method
    """), {
        "source_feature_id": feature["source_feature_id"],
        "rollback_token": ROLLBACK_TOKEN,
        "repair_method": REPAIR_METHOD,
    })
    db.execute(text("""
        update geography_boundary_source_features
        set metadata = cast(:metadata as jsonb), updated_at = now()
        where id = :source_feature_id
    """), {
        "source_feature_id": feature["source_feature_id"],
        "metadata": json.dumps(as_dict(feature.get("old_metadata")), sort_keys=True),
    })
    db.commit()


def run_apply(source_feature_id: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([
        sys.executable,
        str(ROOT / "backend/scripts/apply_boundary_geometry_repair_tiny_fixture.py"),
        "--source-feature-id",
        source_feature_id,
        "--rollback-token",
        ROLLBACK_TOKEN,
        "--output-dir",
        str(OUT_DIR),
        *args,
    ], cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=240)


def read_audit() -> dict:
    return json.loads((OUT_DIR / "boundary_geometry_repair_tiny_fixture_apply_audit.json").read_text(encoding="utf-8"))


def main() -> int:
    print("=" * 72)
    print("BOUNDARY GEOMETRY REPAIR TINY FIXTURE APPLY REGRESSION")
    print("=" * 72)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    feature = None
    before_all = counts(db)

    try:
        feature = choose_source_feature(db)
        mark_fixture(db, feature)
        before_apply = counts(db)

        missing = run_apply(feature["source_feature_id"])
        check(missing.returncode != 0, "Missing apply exits non-zero", missing.stdout[-2000:])
        audit = read_audit()
        check(audit["error"] == "EXPLICIT_APPLY_FLAG_REQUIRED", "Explicit apply flag is required", audit)
        check(audit["counts_unchanged"] is True, "Missing apply writes no rows", audit)

        first = run_apply(
            feature["source_feature_id"],
            "--apply",
            "--enable-geometry-repair-metadata",
            "--classification-reviewed",
            "--admin-confirmation",
            "--applied-by",
            "boundary-geometry-repair-tiny-fixture-regression",
        )
        if first.stdout:
            print(first.stdout)
        if first.stderr:
            print(first.stderr)
        check(first.returncode == 0, "Tiny fixture repair apply exits zero", {"returncode": first.returncode, "stderr": first.stderr[-2000:]})

        audit = read_audit()
        summary = audit["summary"]
        guardrails = audit["guardrails"]
        policy = audit["policy"]

        check(audit["schema_version"] == "boundary_geometry_repair_tiny_fixture_apply.v1", "Schema version is stable", audit)
        check(audit["healthy"] is True, "Apply is healthy", audit)
        check(summary["inserted_repair_event_count"] == 1, "Apply inserts one repair metadata event", summary)
        check(summary["idempotent_skipped_repair_event_count"] == 0, "First apply has no idempotent skip", summary)

        after_first = counts(db)
        check(after_first["active_tiny_fixture_repair_event_rows"] == before_apply["active_tiny_fixture_repair_event_rows"] + 1, "Tiny fixture repair event is active", {"before": before_apply, "after": after_first})
        check(after_first["source_feature_rows"] == before_apply["source_feature_rows"], "Apply does not create/delete source features", {"before": before_apply, "after": after_first})
        check(after_first["valid_source_feature_rows"] == before_apply["valid_source_feature_rows"], "Apply does not change geometry validation status", {"before": before_apply, "after": after_first})
        check(after_first["runtime_eligible_source_feature_rows"] == before_apply["runtime_eligible_source_feature_rows"], "Apply does not change runtime eligibility", {"before": before_apply, "after": after_first})
        check(after_first["boundary_candidate_rows"] == before_apply["boundary_candidate_rows"], "Apply does not create/delete candidates", {"before": before_apply, "after": after_first})
        check(after_first["active_boundary_candidate_rows"] == before_apply["active_boundary_candidate_rows"], "Apply does not activate candidates", {"before": before_apply, "after": after_first})
        check(after_first["promoted_boundary_candidate_rows"] == before_apply["promoted_boundary_candidate_rows"], "Apply does not promote candidates", {"before": before_apply, "after": after_first})
        check(after_first["runtime_feature_rows"] == before_apply["runtime_feature_rows"], "Apply writes no runtime features", {"before": before_apply, "after": after_first})
        check(after_first["runtime_crosswalk_rows"] == before_apply["runtime_crosswalk_rows"], "Apply writes no runtime crosswalks", {"before": before_apply, "after": after_first})

        check(policy["tiny_fixture_only"] is True, "Policy is tiny-fixture only", policy)
        check(policy["broad_apply_supported"] is False, "Broad apply remains unsupported", policy)
        check(policy["target_table"] == "geography_boundary_geometry_repair_events", "Target table is explicit", policy)

        check(guardrails["repair_event_rows_written"] is True, "Apply writes only repair event row", guardrails)
        check(guardrails["geometry_repair_attempted"] is False, "Apply does not repair geometry", guardrails)
        check(guardrails["geometry_validation_status_changed"] is False, "Apply does not change validation status", guardrails)
        check(guardrails["source_runtime_eligibility_changed"] is False, "Apply does not change runtime eligibility", guardrails)
        check(guardrails["source_features_changed"] is False, "Apply does not mutate source feature geometry/status", guardrails)
        check(guardrails["boundary_candidates_promoted"] is False, "Apply promotes no candidates", guardrails)
        check(guardrails["boundary_candidates_activated"] is False, "Apply activates no candidates", guardrails)
        check(guardrails["runtime_tables_written"] is False, "Apply writes no runtime tables", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Apply keeps runtime lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Apply keeps Android unchanged", guardrails)
        check(guardrails["lgd_geography_overwritten"] is False, "Apply does not overwrite LGD", guardrails)

        second = run_apply(
            feature["source_feature_id"],
            "--apply",
            "--enable-geometry-repair-metadata",
            "--classification-reviewed",
            "--admin-confirmation",
        )
        check(second.returncode == 0, "Second apply exits zero", {"returncode": second.returncode, "stderr": second.stderr[-2000:]})
        audit = read_audit()
        check(audit["summary"]["inserted_repair_event_count"] == 0, "Second apply is idempotent", audit["summary"])
        check(audit["summary"]["idempotent_skipped_repair_event_count"] == 1, "Second apply reports idempotent skip", audit["summary"])

        rollback = run_apply(feature["source_feature_id"], "--rollback", "--applied-by", "boundary-geometry-repair-tiny-fixture-regression")
        if rollback.stdout:
            print(rollback.stdout)
        if rollback.stderr:
            print(rollback.stderr)
        check(rollback.returncode == 0, "Rollback exits zero", {"returncode": rollback.returncode, "stderr": rollback.stderr[-2000:]})
        audit = read_audit()
        check(audit["mode"] == "TINY_FIXTURE_BOUNDARY_GEOMETRY_REPAIR_ROLLBACK", "Rollback mode is explicit", audit)
        check(audit["summary"]["rolled_back_event_count"] == 1, "Rollback deactivates fixture repair event", audit["summary"])

        check((OUT_DIR / "boundary_geometry_repair_tiny_fixture_apply_audit.json").exists(), "Audit JSON is written", str(OUT_DIR))
        check((OUT_DIR / "boundary_geometry_repair_tiny_fixture_apply_rows.csv").exists(), "Rows CSV is written", str(OUT_DIR))

        return 0
    finally:
        if feature:
            restore_fixture(db, feature)
            after_cleanup = counts(db)
            check(after_cleanup["tiny_fixture_repair_event_rows"] == 0, "Fixture repair events are cleaned", after_cleanup)
            check(after_cleanup["active_tiny_fixture_repair_event_rows"] == 0, "Active fixture repair events are cleaned", after_cleanup)
            check(after_cleanup["source_feature_rows"] == before_all["source_feature_rows"], "Source feature row count returns to baseline", {"before": before_all, "after": after_cleanup})
            check(after_cleanup["boundary_candidate_rows"] == before_all["boundary_candidate_rows"], "Boundary candidate row count returns to baseline", {"before": before_all, "after": after_cleanup})
            check(after_cleanup["runtime_feature_rows"] == before_all["runtime_feature_rows"], "Runtime feature count returns to baseline", {"before": before_all, "after": after_cleanup})
            check(after_cleanup["runtime_crosswalk_rows"] == before_all["runtime_crosswalk_rows"], "Runtime crosswalk count returns to baseline", {"before": before_all, "after": after_cleanup})
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
