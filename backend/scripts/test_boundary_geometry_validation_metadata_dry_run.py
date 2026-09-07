#!/usr/bin/env python3

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal

SCRIPT = (
    ROOT / "backend/scripts/"
    "plan_boundary_geometry_validation_metadata_dry_run.py"
)
SOURCE = (
    ROOT / "data/raw/nwdp_boundary_all_state/20260824T110250Z/"
    "andaman_and_nicobar_islands.geojson"
)


def check(condition, label, value=None):
    if not condition:
        print(f"FAIL {label}")
        if value is not None:
            print(json.dumps(value, indent=2, default=str))
        raise AssertionError(label)
    print(f"PASS {label}")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def db_counts():
    with SessionLocal() as db:
        return dict(db.execute(text("""
            select
              count(*)::bigint as rows,
              count(*) filter (
                where geometry_validation_status = 'VALIDATED'
              )::bigint as validated,
              count(*) filter (
                where geometry_validation_status = 'NOT_VALIDATED'
              )::bigint as not_validated,
              count(*) filter (
                where eligible_for_runtime_after_promotion = true
              )::bigint as runtime_eligible
            from geography_boundary_source_features
        """)).mappings().one())


def main():
    print("=" * 72)
    print("BOUNDARY GEOMETRY VALIDATION METADATA DRY-RUN REGRESSION")
    print("=" * 72)

    before_db = db_counts()
    before_hash = digest(SOURCE)
    before_mtime = SOURCE.stat().st_mtime_ns

    with tempfile.TemporaryDirectory(
        prefix="boundary-validation-metadata-"
    ) as temp:
        output = Path(temp)

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--state-slug",
                "andaman_and_nicobar_islands",
                "--state-or-ut",
                "Andaman and Nicobar Islands",
                "--limit",
                "100",
                "--output-dir",
                str(output),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=180,
        )

        check(proc.returncode == 0, "Dry-run exits zero", {
            "stderr": proc.stderr[-2000:],
        })

        path = (
            output
            / "andaman_and_nicobar_islands_"
              "validation_metadata_dry_run.json"
        )
        csv_path = (
            output
            / "andaman_and_nicobar_islands_"
              "validation_metadata_dry_run.csv"
        )

        check(path.is_file(), "JSON audit is written")
        check(csv_path.is_file(), "CSV audit is written")

        data = json.loads(path.read_text())
        summary = data["summary"]

        check(
            data["schema_version"]
            == "boundary_geometry_validation_metadata_dry_run.v1",
            "Schema version is stable",
        )
        check(data["healthy"] is True, "Plan is healthy")
        check(
            data["mode"]
            == "READ_ONLY_BOUNDARY_VALIDATION_METADATA_DRY_RUN",
            "Mode is read-only",
        )
        check(
            data["source"]["geometry_hash_algorithm"]
            == "NWDP_GEOJSON_GEOMETRY_CANONICAL_V1",
            "Hash policy is versioned",
        )
        check(summary["selected_row_count"] == 100, "Selects 100 rows")
        check(summary["validated_count"] == 99, "Plans 99 validated")
        check(
            summary["repair_required_count"] == 1,
            "Plans one repair-required row",
        )
        check(
            summary["validation_review_count"] == 0,
            "Plans no manual review",
        )
        check(
            summary["runtime_eligibility_change_planned_count"] == 0,
            "Plans no runtime eligibility changes",
        )

        repair = [
            row for row in data["rows"]
            if row["planned_geometry_validation_status"]
            == "REPAIR_REQUIRED"
        ]
        check(len(repair) == 1, "Emits one repair-required row")
        check(
            repair[0]["source_feature_index"] == 4,
            "Repair-required fixture index is stable",
        )
        check(
            repair[0]["transformed_bbox"] is None
            and repair[0]["transformed_centroid"] is None,
            "Unsafe transformed metadata is withheld",
        )

        validated = [
            row for row in data["rows"]
            if row["planned_geometry_validation_status"] == "VALIDATED"
        ]
        check(
            all(
                row["transformed_bbox"] is not None
                and row["transformed_centroid"] is not None
                for row in validated
            ),
            "Validated rows contain transformed metadata",
        )

        for key, value in data["guardrails"].items():
            check(value is False, f"Guardrail remains false: {key}")

    check(db_counts() == before_db, "Database counts are unchanged")
    check(digest(SOURCE) == before_hash, "Source checksum is unchanged")
    check(
        SOURCE.stat().st_mtime_ns == before_mtime,
        "Source modification time is unchanged",
    )

    body = SCRIPT.read_text().lower()
    for fragment in (
        "insert into geography_",
        "update geography_",
        "delete from geography_",
        "truncate geography_",
    ):
        check(fragment not in body, f"No mutation SQL: {fragment}")

    print("=" * 72)
    print("BOUNDARY GEOMETRY VALIDATION METADATA DRY-RUN REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
