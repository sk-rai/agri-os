#!/usr/bin/env python3
"""Resumable bounded-worker orchestrator for boundary geometry dry-runs."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_SCRIPT = (
    ROOT
    / "backend/scripts/"
    "report_boundary_geometry_validation_repair_dry_run.py"
)
DEFAULT_RAW_DIR = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/"
    "20260824T110250Z"
)
DEFAULT_OUTPUT_DIR = Path(
    "/tmp/boundary-geometry-validation-repair-all-states"
)

SCHEMA_VERSION = (
    "boundary_geometry_validation_repair_all_states.v1"
)
STATE_REPORT_SCHEMA = (
    "boundary_geometry_validation_repair_dry_run.v1"
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def state_report_path(output_dir: Path, slug: str) -> Path:
    return (
        output_dir
        / "states"
        / slug
        / f"{slug}_geometry_validation_repair_dry_run.json"
    )


def completed_report(
    output_dir: Path,
    slug: str,
) -> dict[str, Any] | None:
    path = state_report_path(output_dir, slug)

    if not path.is_file():
        return None

    try:
        data = load_json(path)
    except Exception:
        return None

    if data.get("schema_version") != STATE_REPORT_SCHEMA:
        return None

    if data.get("mode") != (
        "READ_ONLY_GEOMETRY_VALIDATION_REPAIR_DRY_RUN"
    ):
        return None

    if not isinstance(data.get("summary"), dict):
        return None

    return data


def state_slugs(raw_dir: Path) -> list[str]:
    return sorted(path.stem for path in raw_dir.glob("*.geojson"))


def run_state(
    slug: str,
    raw_dir: Path,
    output_dir: Path,
    sample_limit: int,
    force: bool,
) -> dict[str, Any]:
    existing = None if force else completed_report(output_dir, slug)

    if existing is not None:
        return {
            "state_slug": slug,
            "execution_status": "RESUMED",
            "returncode": 0 if existing.get("healthy") else 1,
            "report": existing,
            "stderr": "",
        }

    state_output_dir = output_dir / "states" / slug
    state_output_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [
            sys.executable,
            str(REPORT_SCRIPT),
            "--state-slug",
            slug,
            "--raw-dir",
            str(raw_dir),
            "--output-dir",
            str(state_output_dir),
            "--sample-limit",
            str(sample_limit),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    report_path = state_report_path(output_dir, slug)
    report = None
    error = None

    if report_path.is_file():
        try:
            report = load_json(report_path)
        except Exception as exc:
            error = f"REPORT_PARSE_ERROR: {exc}"
    else:
        error = "REPORT_NOT_WRITTEN"

    report_valid = bool(
        report
        and report.get("schema_version") == STATE_REPORT_SCHEMA
        and isinstance(report.get("summary"), dict)
    )

    if report_valid:
        execution_status = (
            "COMPLETED"
            if report.get("healthy")
            else "COMPLETED_WITH_BLOCKERS"
        )
    else:
        execution_status = "FAILED"

    return {
        "state_slug": slug,
        "execution_status": execution_status,
        "returncode": proc.returncode,
        "report": report,
        "stderr": proc.stderr[-4000:],
        "error": error,
    }


def state_row(result: dict[str, Any]) -> dict[str, Any]:
    report = result.get("report") or {}
    summary = report.get("summary") or {}
    classifications = report.get("classification_counts") or {}

    return {
        "state_slug": result["state_slug"],
        "execution_status": result["execution_status"],
        "report_healthy": bool(report.get("healthy")),
        "returncode": result.get("returncode"),
        "feature_count": int(summary.get("feature_count") or 0),
        "source_valid_count": int(
            summary.get("source_valid_count") or 0
        ),
        "source_invalid_count": int(
            summary.get("source_invalid_count") or 0
        ),
        "validated_no_repair_count": int(
            classifications.get("VALIDATED_NO_REPAIR") or 0
        ),
        "repairable_make_valid_count": int(
            summary.get("repairable_make_valid_count") or 0
        ),
        "manual_review_count": int(
            summary.get("manual_review_count") or 0
        ),
        "reimport_or_crs_review_count": int(
            summary.get("reimport_or_crs_review_count") or 0
        ),
        "transformed_valid_count": int(
            summary.get("transformed_valid_count") or 0
        ),
        "transformed_inside_india_count": int(
            summary.get("transformed_inside_india_count") or 0
        ),
        "error": result.get("error"),
        "stderr": result.get("stderr") or "",
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "state_slug",
        "execution_status",
        "report_healthy",
        "returncode",
        "feature_count",
        "source_valid_count",
        "source_invalid_count",
        "validated_no_repair_count",
        "repairable_make_valid_count",
        "manual_review_count",
        "reimport_or_crs_review_count",
        "transformed_valid_count",
        "transformed_inside_india_count",
        "error",
        "stderr",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--states",
        default="",
        help="Comma-separated state slugs; default is every GeoJSON file.",
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--sample-limit", type=int, default=100)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if not REPORT_SCRIPT.is_file():
        raise SystemExit(f"REPORT_SCRIPT_NOT_FOUND: {REPORT_SCRIPT}")

    available = state_slugs(args.raw_dir)

    requested = [
        value.strip()
        for value in args.states.split(",")
        if value.strip()
    ]

    selected = requested or available
    missing = sorted(set(selected) - set(available))

    if missing:
        print(json.dumps({
            "healthy": False,
            "error": "STATE_SOURCE_NOT_FOUND",
            "missing_state_slugs": missing,
        }, indent=2))
        return 1

    workers = max(1, min(int(args.workers), 4, len(selected)))

    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                run_state,
                slug,
                args.raw_dir,
                args.output_dir,
                args.sample_limit,
                args.force,
            ): slug
            for slug in selected
        }

        for future in as_completed(futures):
            slug = futures[future]

            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "state_slug": slug,
                    "execution_status": "FAILED",
                    "returncode": None,
                    "report": None,
                    "stderr": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }

            results.append(result)

            report = result.get("report") or {}
            summary = report.get("summary") or {}

            print(json.dumps({
                "state_slug": slug,
                "execution_status": result["execution_status"],
                "feature_count": summary.get("feature_count", 0),
                "source_invalid_count": summary.get(
                    "source_invalid_count",
                    0,
                ),
                "repairable_make_valid_count": summary.get(
                    "repairable_make_valid_count",
                    0,
                ),
                "manual_review_count": summary.get(
                    "manual_review_count",
                    0,
                ),
            }))

    rows = sorted(
        (state_row(result) for result in results),
        key=lambda row: row["state_slug"],
    )

    failed = [
        row for row in rows
        if row["execution_status"] == "FAILED"
    ]
    blocker_states = [
        row for row in rows
        if (
            row["manual_review_count"] > 0
            or row["reimport_or_crs_review_count"] > 0
        )
    ]

    summary = {
        "selected_state_count": len(selected),
        "completed_state_count": sum(
            row["execution_status"] in {
                "COMPLETED",
                "COMPLETED_WITH_BLOCKERS",
                "RESUMED",
            }
            for row in rows
        ),
        "resumed_state_count": sum(
            row["execution_status"] == "RESUMED"
            for row in rows
        ),
        "failed_state_count": len(failed),
        "states_with_review_blockers_count": len(blocker_states),
        "feature_count": sum(
            row["feature_count"] for row in rows
        ),
        "source_valid_count": sum(
            row["source_valid_count"] for row in rows
        ),
        "source_invalid_count": sum(
            row["source_invalid_count"] for row in rows
        ),
        "validated_no_repair_count": sum(
            row["validated_no_repair_count"] for row in rows
        ),
        "repairable_make_valid_count": sum(
            row["repairable_make_valid_count"] for row in rows
        ),
        "manual_review_count": sum(
            row["manual_review_count"] for row in rows
        ),
        "reimport_or_crs_review_count": sum(
            row["reimport_or_crs_review_count"] for row in rows
        ),
        "transformed_valid_count": sum(
            row["transformed_valid_count"] for row in rows
        ),
        "transformed_inside_india_count": sum(
            row["transformed_inside_india_count"] for row in rows
        ),
    }

    json_path = (
        args.output_dir
        / "boundary_geometry_validation_repair_national_summary.json"
    )
    csv_path = (
        args.output_dir
        / "boundary_geometry_validation_repair_by_state.csv"
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "healthy": len(failed) == 0,
        "mode": (
            "READ_ONLY_RESUMABLE_BOUNDARY_GEOMETRY_"
            "VALIDATION_REPAIR_ORCHESTRATOR"
        ),
        "configuration": {
            "raw_dir": str(args.raw_dir),
            "output_dir": str(args.output_dir),
            "workers": workers,
            "sample_limit": args.sample_limit,
            "force": args.force,
            "selected_states": selected,
        },
        "summary": summary,
        "state_rows": rows,
        "readiness": {
            "ready_for_admin_national_validation_review": (
                len(failed) == 0
            ),
            "ready_for_broad_geometry_repair_apply": False,
            "ready_for_selected_runtime_promotion_apply": False,
            "ready_for_runtime_lookup_enablement": False,
            "ready_for_android_behavior_change": False,
        },
        "guardrails": {
            "db_writes_attempted": False,
            "source_files_changed": False,
            "source_features_changed": False,
            "geometry_repair_persisted": False,
            "geometry_validation_status_changed": False,
            "source_runtime_eligibility_changed": False,
            "boundary_candidates_promoted": False,
            "boundary_candidates_activated": False,
            "runtime_tables_written": False,
            "runtime_lookup_enabled": False,
            "android_behavior_changed": False,
            "lgd_geography_overwritten": False,
        },
        "output_files": {
            "json": str(json_path),
            "csv": str(csv_path),
        },
    }

    json_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
    write_csv(csv_path, rows)

    print(json.dumps({
        "schema_version": report["schema_version"],
        "healthy": report["healthy"],
        "mode": report["mode"],
        "summary": summary,
        "readiness": report["readiness"],
        "guardrails": report["guardrails"],
        "output_files": report["output_files"],
    }, indent=2))

    return 0 if len(failed) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
