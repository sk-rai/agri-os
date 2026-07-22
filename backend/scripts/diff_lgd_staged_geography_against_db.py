#!/usr/bin/env python3
"""Read-only diff of staged LGD geography JSONL against current DB rows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal
from app.modules.master_data.models import GeographyBlock, GeographyDistrict, GeographyVillage


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _latest_manifest(staged_root: Path) -> Path | None:
    manifests = sorted(staged_root.glob("*/manifest.json"))
    return manifests[-1] if manifests else None


def _ensure_manifest(staged_root: Path, *, auto_stage: bool) -> Path | None:
    manifest = _latest_manifest(staged_root)
    if manifest or not auto_stage:
        return manifest
    script_dir = Path(__file__).resolve().parent
    subprocess.run([sys.executable, str(script_dir / "stage_lgd_parsed_csv_geography.py")], check=True)
    return _latest_manifest(staged_root)


def _codes(rows: list[dict[str, Any]], key: str = "lgd_code") -> set[str]:
    return {str(row.get(key)) for row in rows if row.get(key)}


def _db_codes(db, model) -> set[str]:
    return {str(value) for (value,) in db.query(model.lgd_code).filter(model.is_active == True).all() if value}


def _name_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {str(row.get("lgd_code")): str(row.get("canonical_name")) for row in rows if row.get("lgd_code")}


def _db_name_map(db, model) -> dict[str, str]:
    return {str(code): str(name) for code, name in db.query(model.lgd_code, model.canonical_name).filter(model.is_active == True).all() if code}


def _diff_resource(name: str, staged_rows: list[dict[str, Any]], db_code_set: set[str], db_names: dict[str, str]) -> dict[str, Any]:
    staged_code_set = _codes(staged_rows)
    staged_names = _name_map(staged_rows)

    new_codes = sorted(staged_code_set - db_code_set)
    missing_in_stage = sorted(db_code_set - staged_code_set)
    common = sorted(staged_code_set & db_code_set)

    changed_name_examples = []
    for code in common:
        staged_name = (staged_names.get(code) or "").strip().lower()
        db_name = (db_names.get(code) or "").strip().lower()
        if staged_name and db_name and staged_name != db_name:
            changed_name_examples.append({
                "lgd_code": code,
                "staged_name": staged_names.get(code),
                "db_name": db_names.get(code),
            })
            if len(changed_name_examples) >= 10:
                break

    return {
        "resource": name,
        "staged_count": len(staged_rows),
        "db_active_count": len(db_code_set),
        "new_count": len(new_codes),
        "missing_in_stage_count": len(missing_in_stage),
        "common_count": len(common),
        "changed_name_example_count": len(changed_name_examples),
        "new_code_examples": new_codes[:10],
        "missing_in_stage_examples": missing_in_stage[:10],
        "changed_name_examples": changed_name_examples,
        "matches_current_db": len(new_codes) == 0 and len(missing_in_stage) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff staged LGD geography JSONL against current DB rows without writes.")
    parser.add_argument("--staged-root", default="../data/staged/geography_lgd")
    parser.add_argument("--manifest")
    parser.add_argument("--no-auto-stage", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    staged_root = (script_dir.parent / args.staged_root).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else _ensure_manifest(staged_root, auto_stage=not args.no_auto_stage)

    if not manifest_path or not manifest_path.exists():
        print(json.dumps({
            "schema_version": "lgd_staged_geography_db_diff.v1",
            "status": "NO_STAGING_MANIFEST_FOUND",
            "message": "Run stage_lgd_parsed_csv_geography.py first.",
        }, indent=2, sort_keys=True))
        return 0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out_dir = manifest_path.parent

    staged = {
        "districts": _load_jsonl(out_dir / "districts.jsonl"),
        "blocks": _load_jsonl(out_dir / "blocks.jsonl"),
        "villages": _load_jsonl(out_dir / "villages.jsonl"),
    }

    db = SessionLocal()
    try:
        resources = [
            _diff_resource("districts", staged["districts"], _db_codes(db, GeographyDistrict), _db_name_map(db, GeographyDistrict)),
            _diff_resource("blocks", staged["blocks"], _db_codes(db, GeographyBlock), _db_name_map(db, GeographyBlock)),
            _diff_resource("villages", staged["villages"], _db_codes(db, GeographyVillage), _db_name_map(db, GeographyVillage)),
        ]
    finally:
        db.close()

    result = {
        "schema_version": "lgd_staged_geography_db_diff.v1",
        "status": "DIFFED",
        "staging_manifest": str(manifest_path),
        "source_staging_schema_version": manifest.get("schema_version"),
        "resources": resources,
        "matches_current_db": all(item["matches_current_db"] for item in resources),
        "is_read_only": True,
        "next_actions": [
            "If this matches, keep apply mode disabled until all-India source files are staged and reviewed.",
            "For all-India expansion, expect new_count > 0 outside the current state and require admin-approved apply.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
