#!/usr/bin/env python3
"""Tiny-fixture boundary validation metadata apply with exact rollback."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import engine  # noqa: E402

SCHEMA_VERSION = "boundary_geometry_validation_metadata_tiny_fixture_apply.v1"
FIXTURE_ID = "9a18114f-5350-5173-97df-f24e1e64c30b"
STATE_SLUG = "andaman_and_nicobar_islands"
STATE_NAME = "Andaman and Nicobar Islands"
SOURCE_SHA256 = (
    "46236e51de89a034b99863600b9f46d24a4ed3e01905362fc90ac4b73de20591"
)
SOURCE_PATH = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/20260824T110250Z/"
    "andaman_and_nicobar_islands.geojson"
)
MARKER = "tiny_fixture_validation_metadata_apply"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-feature-id", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--rollback-token", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--applied-by", default="admin-regression")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument(
        "--enable-validation-metadata-write",
        action="store_true",
    )
    parser.add_argument("--dry-run-reviewed", action="store_true")
    parser.add_argument("--admin-confirmation", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def counts(conn) -> dict[str, int]:
    row = conn.execute(text("""
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
          (select count(*) from geography_boundary_crosswalk_candidates)
            as candidate_rows,
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
    """)).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def load_row(conn, feature_id: str) -> dict[str, Any] | None:
    row = conn.execute(text("""
        select
          sf.id::text as source_feature_id,
          sf.import_batch_id::text as import_batch_id,
          sf.source_feature_index,
          sf.source_vlcode,
          sf.source_geometry_hash,
          sf.source_bbox,
          sf.transformed_bbox,
          sf.transformed_centroid,
          sf.geometry_validation_status,
          sf.eligible_for_runtime_after_promotion,
          sf.metadata,
          b.source_system,
          b.state_or_ut
        from geography_boundary_source_features sf
        join geography_boundary_import_batches b
          on b.id = sf.import_batch_id
        where sf.id = cast(:feature_id as uuid)
    """), {"feature_id": feature_id}).mappings().first()
    return dict(row) if row else None


def run_plan(output_dir: Path) -> dict[str, Any]:
    plan_dir = output_dir / "dry_run"
    command = [
        sys.executable,
        str(
            ROOT
            / "backend/scripts/"
            "plan_boundary_geometry_validation_metadata_dry_run.py"
        ),
        "--state-slug",
        STATE_SLUG,
        "--state-or-ut",
        STATE_NAME,
        "--limit",
        "1",
        "--output-dir",
        str(plan_dir),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    path = (
        plan_dir
        / "andaman_and_nicobar_islands_validation_metadata_dry_run.json"
    )
    if completed.returncode != 0 or not path.is_file():
        raise RuntimeError(
            f"DRY_RUN_FAILED: {completed.stderr[-1000:]}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def guardrails(action: str) -> dict[str, bool]:
    wrote = action in {"APPLIED", "ROLLED_BACK"}
    return {
        "db_writes_attempted": wrote,
        "source_files_changed": False,
        "source_features_changed": wrote,
        "validation_metadata_written": action == "APPLIED",
        "validation_metadata_rolled_back": action == "ROLLED_BACK",
        "geometry_repair_persisted": False,
        "source_runtime_eligibility_changed": False,
        "boundary_candidates_promoted": False,
        "boundary_candidates_activated": False,
        "runtime_tables_written": False,
        "runtime_lookup_enabled": False,
        "lgd_geography_overwritten": False,
        "android_behavior_changed": False,
    }


def outputs(
    output_dir: Path,
    audit: dict[str, Any],
    row: dict[str, Any] | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / (
        "boundary_validation_metadata_tiny_fixture_apply_audit.json"
    )
    csv_path = output_dir / (
        "boundary_validation_metadata_tiny_fixture_apply_rows.csv"
    )
    audit["output_files"] = {
        "json": str(json_path),
        "csv": str(csv_path),
    }
    json_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    fields = [
        "source_feature_id",
        "source_feature_index",
        "source_vlcode",
        "action",
        "before_status",
        "after_status",
        "rollback_token",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        if row:
            writer.writerow({key: row.get(key) for key in fields})


def reject(
    args: argparse.Namespace,
    error: str,
    before: dict[str, int],
) -> int:
    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": False,
        "mode": "TINY_FIXTURE_VALIDATION_METADATA_APPLY",
        "error": error,
        "action": "REJECTED",
        "before_counts": before,
        "after_counts": before,
        "guardrails": guardrails("REJECTED"),
    }
    outputs(args.output_dir, audit, None)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 1


def main() -> int:
    args = arguments()

    with engine.begin() as conn:
        before = counts(conn)
        current = load_row(conn, args.source_feature_id)

        if args.apply == args.rollback:
            return reject(
                args,
                "EXACTLY_ONE_OF_APPLY_OR_ROLLBACK_REQUIRED",
                before,
            )
        if args.source_feature_id != FIXTURE_ID:
            return reject(args, "TINY_FIXTURE_ID_REQUIRED", before)
        if not current:
            return reject(args, "SOURCE_FEATURE_NOT_FOUND", before)
        if current["source_system"] != "NWDP_GSI_VILLAGE_BOUNDARY":
            return reject(args, "SOURCE_SYSTEM_MISMATCH", before)
        if current["state_or_ut"].lower() != STATE_NAME.lower():
            return reject(args, "STATE_SCOPE_MISMATCH", before)
        if args.source_sha256.lower() != SOURCE_SHA256:
            return reject(args, "SOURCE_CHECKSUM_CONFIRMATION_MISMATCH", before)
        if sha256_file(SOURCE_PATH) != SOURCE_SHA256:
            return reject(args, "SOURCE_FILE_CHECKSUM_MISMATCH", before)
        if not args.enable_validation_metadata_write:
            return reject(
                args,
                "ENABLE_VALIDATION_METADATA_WRITE_REQUIRED",
                before,
            )
        if not args.dry_run_reviewed:
            return reject(args, "DRY_RUN_REVIEW_REQUIRED", before)
        if not args.admin_confirmation:
            return reject(args, "ADMIN_CONFIRMATION_REQUIRED", before)

        metadata = current.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        marker = metadata.get(MARKER)

        if args.rollback:
            if not isinstance(marker, dict):
                return reject(args, "ROLLBACK_METADATA_NOT_FOUND", before)
            if marker.get("rollback_token") != args.rollback_token:
                return reject(args, "ROLLBACK_TOKEN_MISMATCH", before)

            original = marker["original"]
            result = conn.execute(text("""
                update geography_boundary_source_features
                set
                  source_geometry_hash = :source_geometry_hash,
                  source_bbox = cast(:source_bbox as jsonb),
                  transformed_bbox = cast(:transformed_bbox as jsonb),
                  transformed_centroid =
                    cast(:transformed_centroid as jsonb),
                  geometry_validation_status = :status,
                  metadata = cast(:metadata as jsonb)
                where id = cast(:feature_id as uuid)
            """), {
                "feature_id": FIXTURE_ID,
                "source_geometry_hash":
                    original["source_geometry_hash"],
                "source_bbox":
                    json.dumps(original["source_bbox"]),
                "transformed_bbox":
                    json.dumps(original["transformed_bbox"]),
                "transformed_centroid":
                    json.dumps(original["transformed_centroid"]),
                "status":
                    original["geometry_validation_status"],
                "metadata":
                    json.dumps(original["metadata"]),
            })
            action = "ROLLED_BACK"
            changed = int(result.rowcount or 0)
            plan = None

        else:
            if isinstance(marker, dict):
                if marker.get("rollback_token") != args.rollback_token:
                    return reject(
                        args,
                        "ACTIVE_FIXTURE_ROLLBACK_TOKEN_MISMATCH",
                        before,
                    )
                action = "IDEMPOTENT_NO_OP"
                changed = 0
                plan = marker.get("plan")
            else:
                if current["geometry_validation_status"] != "NOT_VALIDATED":
                    return reject(
                        args,
                        "FIXTURE_IS_NOT_NOT_VALIDATED",
                        before,
                    )
                if current["eligible_for_runtime_after_promotion"]:
                    return reject(
                        args,
                        "FIXTURE_RUNTIME_ELIGIBILITY_MUST_BE_FALSE",
                        before,
                    )

                report = run_plan(args.output_dir)
                planned = report["rows"][0]

                if planned["source_feature_id"] != FIXTURE_ID:
                    return reject(args, "DRY_RUN_FIXTURE_MISMATCH", before)
                if (
                    planned["planned_geometry_validation_status"]
                    != "VALIDATED"
                ):
                    return reject(
                        args,
                        "FIXTURE_NOT_SAFELY_VALIDATED",
                        before,
                    )
                if planned["runtime_eligibility_change_planned"]:
                    return reject(
                        args,
                        "RUNTIME_ELIGIBILITY_CHANGE_FORBIDDEN",
                        before,
                    )

                original = {
                    "source_geometry_hash":
                        current["source_geometry_hash"],
                    "source_bbox": current["source_bbox"],
                    "transformed_bbox": current["transformed_bbox"],
                    "transformed_centroid":
                        current["transformed_centroid"],
                    "geometry_validation_status":
                        current["geometry_validation_status"],
                    "metadata": metadata,
                }
                marker_value = {
                    "schema_version": SCHEMA_VERSION,
                    "rollback_token": args.rollback_token,
                    "applied_by": args.applied_by,
                    "applied_at": datetime.now(timezone.utc).isoformat(),
                    "original": original,
                    "plan": planned,
                }
                updated_metadata = dict(metadata)
                updated_metadata[MARKER] = marker_value

                result = conn.execute(text("""
                    update geography_boundary_source_features
                    set
                      source_geometry_hash = :source_geometry_hash,
                      source_bbox = cast(:source_bbox as jsonb),
                      transformed_bbox = cast(:transformed_bbox as jsonb),
                      transformed_centroid =
                        cast(:transformed_centroid as jsonb),
                      geometry_validation_status = 'VALIDATED',
                      metadata = cast(:metadata as jsonb)
                    where id = cast(:feature_id as uuid)
                      and geometry_validation_status = 'NOT_VALIDATED'
                      and eligible_for_runtime_after_promotion = false
                """), {
                    "feature_id": FIXTURE_ID,
                    "source_geometry_hash":
                        planned["source_geometry_hash"],
                    "source_bbox":
                        json.dumps(planned["source_bbox"]),
                    "transformed_bbox":
                        json.dumps(planned["transformed_bbox"]),
                    "transformed_centroid":
                        json.dumps(planned["transformed_centroid"]),
                    "metadata":
                        json.dumps(updated_metadata),
                })
                changed = int(result.rowcount or 0)
                if changed != 1:
                    raise RuntimeError("TINY_FIXTURE_UPDATE_COUNT_MISMATCH")
                action = "APPLIED"
                plan = planned

        after = counts(conn)
        final_row = load_row(conn, FIXTURE_ID)

    audit_row = {
        "source_feature_id": FIXTURE_ID,
        "source_feature_index": current["source_feature_index"],
        "source_vlcode": current["source_vlcode"],
        "action": action,
        "before_status": current["geometry_validation_status"],
        "after_status": final_row["geometry_validation_status"],
        "rollback_token": args.rollback_token,
    }
    audit = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "mode": (
            "TINY_FIXTURE_VALIDATION_METADATA_ROLLBACK"
            if args.rollback
            else "TINY_FIXTURE_VALIDATION_METADATA_APPLY"
        ),
        "error": None,
        "action": action,
        "changed_row_count": changed,
        "rollback_token": args.rollback_token,
        "plan": plan,
        "before_counts": before,
        "after_counts": after,
        "final_row": final_row,
        "policy": {
            "tiny_fixture_only": True,
            "broad_apply_supported": False,
            "runtime_eligibility_write_allowed": False,
            "candidate_write_allowed": False,
            "runtime_table_write_allowed": False,
            "runtime_lookup_enablement_allowed": False,
            "android_behavior_change_allowed": False,
        },
        "guardrails": guardrails(action),
    }
    outputs(args.output_dir, audit, audit_row)
    print(json.dumps(audit, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
