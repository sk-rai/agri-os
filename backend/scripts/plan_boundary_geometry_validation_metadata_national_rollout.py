#!/usr/bin/env python3
"""Read-only national boundary validation-metadata wave planner."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from scripts.plan_boundary_geometry_validation_metadata_bounded_state import (  # noqa: E402
    canonical_checksum,
)
from scripts.report_boundary_geometry_validation_repair_dry_run import (  # noqa: E402
    sha256_file,
)

SCHEMA_VERSION = (
    "boundary_geometry_validation_metadata_"
    "national_rollout_plan.v1"
)
STATE_PLAN_SCHEMA = (
    "boundary_geometry_validation_metadata_"
    "bounded_state_plan.v1"
)
MODE = "READ_ONLY_NATIONAL_VALIDATION_METADATA_WAVE_PLAN"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"

DEFAULT_RAW_DIR = (
    ROOT / "data/raw/nwdp_boundary_all_state/20260824T110250Z"
)
DEFAULT_RUN_ROOT = (
    ROOT
    / "data/staged/core_stack/"
    "boundary_validation_metadata_rollout_runs"
)
STATE_PLANNER = (
    ROOT / "backend/scripts/"
    "plan_boundary_geometry_validation_metadata_bounded_state.py"
)

STATE_SLUG_ALIASES = {
    "dadra_and_nagar_haveli_and_daman_and_diu":
        "dadra_and_nagar_haveli_and_daman_diu",
    "jammu_and_kashmir": "jammu_kashmir",
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Explicit output directory, primarily for regression. "
            "Operational runs should use --run-root and --run-id."
        ),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=DEFAULT_RUN_ROOT,
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--batch-limit", type=int, default=500)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--states",
        default="",
        help="Optional comma-separated source slugs.",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def slugify(value: str) -> str:
    value = value.strip().lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return STATE_SLUG_ALIASES.get(value, value)


def database_inventory() -> tuple[list[dict[str, Any]], dict[str, int]]:
    with SessionLocal() as db:
        states = [
            dict(row)
            for row in db.execute(text("""
                select
                  b.state_or_ut,
                  b.id::text as import_batch_id,
                  count(sf.id)::bigint as source_feature_count,
                  count(*) filter (
                    where sf.geometry_validation_status = 'NOT_VALIDATED'
                  )::bigint as not_validated_count,
                  count(*) filter (
                    where sf.geometry_validation_status = 'VALIDATED'
                  )::bigint as validated_count
                from geography_boundary_import_batches b
                join geography_boundary_source_features sf
                  on sf.import_batch_id = b.id
                where b.source_system = :source_system
                group by b.state_or_ut, b.id
                order by b.state_or_ut, b.id
            """), {"source_system": SOURCE_SYSTEM}).mappings()
        ]

        baseline = dict(db.execute(text("""
            select
              (select count(*) from geography_boundary_source_features)
                as source_feature_rows,
              (select count(*) from geography_boundary_source_features
               where geometry_validation_status = 'NOT_VALIDATED')
                as not_validated_rows,
              (select count(*) from geography_boundary_source_features
               where geometry_validation_status = 'VALIDATED')
                as validated_rows,
              (select count(*) from geography_boundary_source_features
               where eligible_for_runtime_after_promotion = true)
                as runtime_eligible_source_rows,
              (select count(*) from geography_boundary_crosswalk_candidates
               where is_active = true)
                as active_candidate_rows,
              (select count(*) from geography_boundary_crosswalk_candidates
               where promotion_status = 'PROMOTED')
                as promoted_candidate_rows,
              (select count(*) from geography_boundary_runtime_sets)
                as runtime_set_rows,
              (select count(*) from geography_boundary_runtime_features)
                as runtime_feature_rows,
              (select count(*) from geography_boundary_runtime_crosswalks)
                as runtime_crosswalk_rows
        """)).mappings().one())

        db.rollback()

    return states, {
        key: int(value or 0)
        for key, value in baseline.items()
    }


def write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def validate_cached_state_plan(
    *,
    plan: dict[str, Any],
    checkpoint: dict[str, Any],
    state: dict[str, Any],
    slug: str,
    source_sha256: str,
    batch_limit: int,
    database_baseline: dict[str, int],
) -> str | None:
    if checkpoint.get("schema_version") != (
        "boundary_geometry_validation_metadata_"
        "national_state_checkpoint.v1"
    ):
        return "CHECKPOINT_SCHEMA_MISMATCH"

    if plan.get("schema_version") != STATE_PLAN_SCHEMA:
        return "STATE_PLAN_SCHEMA_MISMATCH"
    if plan.get("healthy") is not True:
        return "STATE_PLAN_NOT_HEALTHY"
    if plan.get("database_counts", {}).get("unchanged") is not True:
        return "STATE_PLAN_DATABASE_COUNTS_CHANGED"

    scope = plan.get("scope") or {}
    source = plan.get("source") or {}
    batch = plan.get("batch") or {}
    rows = plan.get("rows") or []

    expected_identity = {
        "state_or_ut": state["state_or_ut"],
        "state_slug": slug,
        "import_batch_id": state["import_batch_id"],
        "source_sha256": source_sha256,
        "source_feature_count": int(state["source_feature_count"]),
        "database_not_validated_count":
            int(state["not_validated_count"]),
        "database_validated_count":
            int(state["validated_count"]),
        "batch_limit": batch_limit,
    }
    if checkpoint.get("identity") != expected_identity:
        return "CHECKPOINT_IDENTITY_MISMATCH"

    if checkpoint.get("database_baseline") != database_baseline:
        return "CHECKPOINT_DATABASE_BASELINE_MISMATCH"

    if (
        scope.get("state_slug") != slug
        or scope.get("state_or_ut") != state["state_or_ut"]
        or scope.get("import_batch_id") != state["import_batch_id"]
        or int(scope.get("cursor_after_index", -2)) != -1
        or int(scope.get("limit", -1)) != batch_limit
    ):
        return "STATE_PLAN_SCOPE_MISMATCH"

    if (
        source.get("sha256") != source_sha256
        or int(source.get("feature_count", -1)) !=
            int(state["source_feature_count"])
    ):
        return "STATE_PLAN_SOURCE_MISMATCH"

    checksum_payload = {
        "schema_version": STATE_PLAN_SCHEMA,
        "state_slug": slug,
        "state_or_ut": state["state_or_ut"],
        "import_batch_id": state["import_batch_id"],
        "source_sha256": source_sha256,
        "geometry_hash_algorithm":
            source.get("geometry_hash_algorithm"),
        "cursor_after_index": -1,
        "limit": batch_limit,
        "rows": rows,
    }
    recomputed_checksum = canonical_checksum(checksum_payload)

    if batch.get("plan_checksum") != recomputed_checksum:
        return "STATE_PLAN_CHECKSUM_MISMATCH"
    if checkpoint.get("plan_checksum") != recomputed_checksum:
        return "CHECKPOINT_PLAN_CHECKSUM_MISMATCH"
    if checkpoint.get("batch_id") != batch.get("batch_id"):
        return "CHECKPOINT_BATCH_ID_MISMATCH"
    if int(batch.get("selected_row_count", -1)) != len(rows):
        return "STATE_PLAN_SELECTED_COUNT_MISMATCH"
    if len(rows) > batch_limit:
        return "STATE_PLAN_BATCH_LIMIT_EXCEEDED"

    return None


def run_state(
    state: dict[str, Any],
    raw_dir: Path,
    output_dir: Path,
    batch_limit: int,
    database_baseline: dict[str, int],
    resume: bool,
    force: bool,
) -> dict[str, Any]:
    state_name = state["state_or_ut"]
    slug = slugify(state_name)
    source_path = raw_dir / f"{slug}.geojson"
    state_dir = output_dir / "states" / slug
    state_dir.mkdir(parents=True, exist_ok=True)

    if not source_path.is_file():
        return {
            "state_or_ut": state_name,
            "state_slug": slug,
            "status": "BLOCKED",
            "error": "SOURCE_FILE_NOT_FOUND",
        }

    source_sha256 = sha256_file(source_path)
    plan_path = (
        state_dir /
        f"{slug}_bounded_validation_metadata_plan.json"
    )
    checkpoint_path = state_dir / "checkpoint.json"
    execution_status = "GENERATED"

    if resume and (plan_path.exists() or checkpoint_path.exists()):
        if not plan_path.is_file() or not checkpoint_path.is_file():
            return {
                "state_or_ut": state_name,
                "state_slug": slug,
                "status": "BLOCKED",
                "execution_status": "CHECKPOINT_REJECTED",
                "source_sha256": source_sha256,
                "error": "INCOMPLETE_STATE_CHECKPOINT",
            }

        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            checkpoint = json.loads(
                checkpoint_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "state_or_ut": state_name,
                "state_slug": slug,
                "status": "BLOCKED",
                "execution_status": "CHECKPOINT_REJECTED",
                "source_sha256": source_sha256,
                "error": f"INVALID_STATE_CHECKPOINT: {exc}",
            }

        checkpoint_error = validate_cached_state_plan(
            plan=plan,
            checkpoint=checkpoint,
            state=state,
            slug=slug,
            source_sha256=source_sha256,
            batch_limit=batch_limit,
            database_baseline=database_baseline,
        )
        if checkpoint_error is not None:
            return {
                "state_or_ut": state_name,
                "state_slug": slug,
                "status": "BLOCKED",
                "execution_status": "CHECKPOINT_REJECTED",
                "source_sha256": source_sha256,
                "error": (
                    "STALE_CACHED_STATE_PLAN: "
                    f"{checkpoint_error}"
                ),
            }

        execution_status = "RESUMED"
    else:
        proc = subprocess.run(
            [
                sys.executable,
                str(STATE_PLANNER),
                "--state-slug", slug,
                "--state-or-ut", state_name,
                "--expected-source-sha256", source_sha256,
                "--cursor-after-index", "-1",
                "--limit", str(batch_limit),
                "--raw-dir", str(raw_dir),
                "--output-dir", str(state_dir),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        if proc.returncode != 0 or not plan_path.is_file():
            return {
                "state_or_ut": state_name,
                "state_slug": slug,
                "status": "FAILED",
                "execution_status": "GENERATION_FAILED",
                "source_sha256": source_sha256,
                "error": proc.stderr[-4000:] or proc.stdout[-4000:],
            }

        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "state_or_ut": state_name,
                "state_slug": slug,
                "status": "FAILED",
                "execution_status": "GENERATION_FAILED",
                "source_sha256": source_sha256,
                "error": f"INVALID_GENERATED_STATE_PLAN: {exc}",
            }
    if (
        plan.get("schema_version") != STATE_PLAN_SCHEMA
        or plan.get("healthy") is not True
        or plan["scope"]["import_batch_id"] !=
            state["import_batch_id"]
        or int(plan["source"]["feature_count"]) !=
            int(state["source_feature_count"])
        or plan["database_counts"]["unchanged"] is not True
    ):
        return {
            "state_or_ut": state_name,
            "state_slug": slug,
            "status": "BLOCKED",
            "source_sha256": source_sha256,
            "error": "STATE_PLAN_INVARIANT_FAILED",
        }

    batch = plan["batch"]
    classification = plan["state_classification"]

    if execution_status == "GENERATED":
        checkpoint = {
            "schema_version": (
                "boundary_geometry_validation_metadata_"
                "national_state_checkpoint.v1"
            ),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "identity": {
                "state_or_ut": state_name,
                "state_slug": slug,
                "import_batch_id": state["import_batch_id"],
                "source_sha256": source_sha256,
                "source_feature_count":
                    int(state["source_feature_count"]),
                "database_not_validated_count":
                    int(state["not_validated_count"]),
                "database_validated_count":
                    int(state["validated_count"]),
                "batch_limit": batch_limit,
            },
            "database_baseline": database_baseline,
            "batch_id": batch["batch_id"],
            "plan_checksum": batch["plan_checksum"],
            "plan_json": str(plan_path),
            "plan_csv": plan["output_files"]["csv"],
        }
        write_json_atomically(checkpoint_path, checkpoint)
    selected = int(batch["selected_row_count"])
    remaining = int(
        batch["remaining_valid_not_validated_count"]
    )

    rollback_token = (
        f"national-validation-metadata-wave-1-"
        f"{slug}-{batch['batch_id']}"
    )

    return {
        "state_or_ut": state_name,
        "state_slug": slug,
        "status": (
            "PLANNED" if selected > 0 else "COMPLETE"
        ),
        "execution_status": execution_status,
        "checkpoint_json": str(checkpoint_path),
        "import_batch_id": state["import_batch_id"],
        "source_feature_count":
            int(state["source_feature_count"]),
        "database_not_validated_count":
            int(state["not_validated_count"]),
        "database_validated_count":
            int(state["validated_count"]),
        "source_sha256": source_sha256,
        "valid_without_repair_count":
            int(classification["valid_without_repair_count"]),
        "repair_required_count":
            int(classification["repair_required_count"]),
        "validation_review_count":
            int(classification["validation_review_count"]),
        "selected_row_count": selected,
        "remaining_eligible_count": remaining,
        "estimated_remaining_batch_count": (
            (remaining + batch_limit - 1) // batch_limit
        ),
        "batch_id": batch["batch_id"],
        "plan_checksum": batch["plan_checksum"],
        "next_cursor_after_index":
            batch["next_cursor_after_index"],
        "rollback_token_proposal": rollback_token,
        "plan_json": str(plan_path),
        "plan_csv": plan["output_files"]["csv"],
        "error": None,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({
        key for row in rows for key in row.keys()
    })
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    options = arguments()

    if not 1 <= options.batch_limit <= 500:
        raise SystemExit("--batch-limit must be between 1 and 500")
    if not 1 <= options.workers <= 4:
        raise SystemExit("--workers must be between 1 and 4")
    if options.resume and options.force:
        raise SystemExit("--resume and --force are mutually exclusive")
    if not STATE_PLANNER.is_file():
        raise SystemExit("STATE_PLANNER_NOT_FOUND")

    if options.output_dir is not None:
        if options.run_id is not None:
            raise SystemExit(
                "--run-id cannot be combined with --output-dir"
            )
        run_id = options.output_dir.name
    else:
        run_id = (
            options.run_id
            or datetime.now(timezone.utc).strftime(
                "%Y%m%dT%H%M%SZ"
            )
        )
        options.output_dir = options.run_root / run_id

    if options.resume and not options.output_dir.exists():
        raise SystemExit("RESUME_RUN_DIRECTORY_NOT_FOUND")
    if (
        options.output_dir.exists()
        and any(options.output_dir.iterdir())
        and not options.resume
        and not options.force
    ):
        raise SystemExit(
            "RUN_DIRECTORY_NOT_EMPTY_USE_RESUME_OR_FORCE"
        )

    states, before = database_inventory()
    sources = sorted(path.stem for path in options.raw_dir.glob("*.geojson"))

    if len(states) != 36 or len(sources) != 36:
        raise SystemExit("NATIONAL_STATE_SOURCE_COUNT_MISMATCH")

    requested = {
        item.strip()
        for item in options.states.split(",")
        if item.strip()
    }

    discovered = {slugify(row["state_or_ut"]) for row in states}
    if requested - discovered:
        raise SystemExit(
            "UNKNOWN_STATE_SLUGS: " +
            ",".join(sorted(requested - discovered))
        )

    selected_states = [
        row for row in states
        if not requested or slugify(row["state_or_ut"]) in requested
    ]

    options.output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    with ThreadPoolExecutor(
        max_workers=min(options.workers, len(selected_states))
    ) as executor:
        futures = {
            executor.submit(
                run_state,
                state,
                options.raw_dir,
                options.output_dir,
                options.batch_limit,
                before,
                options.resume,
                options.force,
            ): state
            for state in selected_states
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda row: row["state_slug"])
    _, after = database_inventory()

    deterministic_states = [
        {
            "state_or_ut": row["state_or_ut"],
            "state_slug": row["state_slug"],
            "status": row["status"],
            "import_batch_id": row.get("import_batch_id"),
            "source_feature_count":
                row.get("source_feature_count"),
            "source_sha256": row.get("source_sha256"),
            "valid_without_repair_count":
                row.get("valid_without_repair_count"),
            "repair_required_count":
                row.get("repair_required_count"),
            "validation_review_count":
                row.get("validation_review_count"),
            "selected_row_count":
                row.get("selected_row_count"),
            "remaining_eligible_count":
                row.get("remaining_eligible_count"),
            "estimated_remaining_batch_count":
                row.get("estimated_remaining_batch_count"),
            "batch_id": row.get("batch_id"),
            "plan_checksum": row.get("plan_checksum"),
            "next_cursor_after_index":
                row.get("next_cursor_after_index"),
            "rollback_token_proposal":
                row.get("rollback_token_proposal"),
            "error": row.get("error"),
        }
        for row in results
    ]
    deterministic = {
        "schema_version": SCHEMA_VERSION,
        "batch_limit": options.batch_limit,
        "states": deterministic_states,
    }
    national_checksum = canonical_checksum(deterministic)

    healthy = (
        before == after
        and all(
            row["status"] in {"PLANNED", "COMPLETE"}
            for row in results
        )
    )

    summary = {
        "selected_state_count": len(results),
        "planned_state_count": sum(
            row["status"] == "PLANNED" for row in results
        ),
        "complete_state_count": sum(
            row["status"] == "COMPLETE" for row in results
        ),
        "failed_or_blocked_state_count": sum(
            row["status"] not in {"PLANNED", "COMPLETE"}
            for row in results
        ),
        "generated_state_count": sum(
            row.get("execution_status") == "GENERATED"
            for row in results
        ),
        "resumed_state_count": sum(
            row.get("execution_status") == "RESUMED"
            for row in results
        ),
        "checkpoint_rejected_state_count": sum(
            row.get("execution_status") ==
                "CHECKPOINT_REJECTED"
            for row in results
        ),
        "selected_row_count": sum(
            int(row.get("selected_row_count") or 0)
            for row in results
        ),
        "remaining_eligible_count": sum(
            int(row.get("remaining_eligible_count") or 0)
            for row in results
        ),
        "repair_required_count": sum(
            int(row.get("repair_required_count") or 0)
            for row in results
        ),
        "validation_review_count": sum(
            int(row.get("validation_review_count") or 0)
            for row in results
        ),
        "estimated_remaining_batch_count": sum(
            int(row.get("estimated_remaining_batch_count") or 0)
            for row in results
        ),
    }

    json_path = (
        options.output_dir /
        "national_validation_metadata_wave_plan.json"
    )
    csv_path = (
        options.output_dir /
        "national_validation_metadata_wave_plan.csv"
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": healthy,
        "mode": MODE,
        "configuration": {
            "run_id": run_id,
            "run_root": str(options.run_root),
            "raw_dir": str(options.raw_dir),
            "output_dir": str(options.output_dir),
            "resume": options.resume,
            "batch_limit": options.batch_limit,
            "workers": options.workers,
            "selected_states": [
                row["state_slug"] for row in results
            ],
            "force": options.force,
        },
        "database_counts": {
            "before": before,
            "after": after,
            "unchanged": before == after,
        },
        "summary": summary,
        "states": results,
        "national_plan_checksum": national_checksum,
        "readiness": {
            "ready_for_plan_review": healthy,
            "ready_for_national_apply": False,
            "ready_for_geometry_repair_apply": False,
            "ready_for_runtime_promotion": False,
            "ready_for_runtime_lookup": False,
            "ready_for_android_behavior_change": False,
        },
        "guardrails": {
            "database_writes_attempted": False,
            "validation_metadata_written": False,
            "geometry_repair_persisted": False,
            "runtime_eligibility_changed": False,
            "candidate_activation_changed": False,
            "candidate_promotion_changed": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
        },
        "output_files": {
            "json": str(json_path),
            "csv": str(csv_path),
        },
    }

    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_csv(csv_path, results)

    print(json.dumps({
        "healthy": healthy,
        "mode": MODE,
        "summary": summary,
        "database_counts": report["database_counts"],
        "national_plan_checksum": national_checksum,
        "output_files": report["output_files"],
        "guardrails": report["guardrails"],
    }, indent=2, sort_keys=True))

    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
