#!/usr/bin/env python3
"""Stage parsed LGD CSV geography rows into normalized JSONL without DB writes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{str(k): ("" if v is None else str(v).strip()) for k, v in row.items()} for row in csv.DictReader(handle)]


def _first(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return None


def _pins(value: str | None) -> list[str]:
    if not value:
        return []
    pins = []
    for token in value.replace(";", ",").replace("|", ",").split(","):
        token = token.strip()
        if token:
            pins.append(token)
    return sorted(set(pins))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _stage_districts(rows: list[dict[str, str]], *, tenant_country_code: str, default_state_code: str, default_state_name: str) -> list[dict[str, Any]]:
    staged = []
    for row in rows:
        lgd_code = _first(row, "lgd_code", "district_lgd_code", "district_code")
        staged.append({
            "entity_type": "DISTRICT",
            "country_code": tenant_country_code,
            "state_code": default_state_code,
            "state_name": default_state_name,
            "lgd_code": lgd_code,
            "canonical_name": _first(row, "canonical_name", "district_name", "name"),
            "census_name": _first(row, "census_name"),
            "source_row": row,
        })
    return staged


def _stage_blocks(rows: list[dict[str, str]], *, tenant_country_code: str, default_state_code: str, default_state_name: str) -> list[dict[str, Any]]:
    staged = []
    for row in rows:
        staged.append({
            "entity_type": "SUB_DISTRICT_OR_BLOCK",
            "country_code": tenant_country_code,
            "state_code": default_state_code,
            "state_name": default_state_name,
            "district_lgd_code": _first(row, "district_lgd_code", "district_code"),
            "lgd_code": _first(row, "lgd_code", "block_lgd_code", "sub_district_lgd_code"),
            "canonical_name": _first(row, "canonical_name", "block_name", "sub_district_name", "name"),
            "source_row": row,
        })
    return staged


def _stage_villages(rows: list[dict[str, str]], *, tenant_country_code: str, default_state_code: str, default_state_name: str) -> list[dict[str, Any]]:
    staged = []
    for row in rows:
        staged.append({
            "entity_type": "LOCALITY_OR_VILLAGE",
            "country_code": tenant_country_code,
            "state_code": default_state_code,
            "state_name": default_state_name,
            "district_lgd_code": _first(row, "district_lgd_code", "district_code"),
            "block_lgd_code": _first(row, "block_lgd_code", "block_code"),
            "lgd_code": _first(row, "lgd_code", "village_lgd_code", "village_code"),
            "canonical_name": _first(row, "canonical_name", "village_name", "name"),
            "census_name": _first(row, "census_name"),
            "census_village_code": _first(row, "census_village_code"),
            "pin_codes": _pins(_first(row, "pin_codes", "pin_code", "pincode")),
            "source_row": row,
        })
    return staged


def _validate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing_name = sum(1 for row in rows if not row.get("canonical_name"))
    missing_lgd = sum(1 for row in rows if not row.get("lgd_code"))
    duplicate_keys: dict[str, int] = {}
    seen: dict[str, int] = {}
    for row in rows:
        key = f"{row.get('entity_type')}::{row.get('state_code')}::{row.get('district_lgd_code')}::{row.get('block_lgd_code')}::{row.get('lgd_code')}"
        seen[key] = seen.get(key, 0) + 1
    duplicate_keys = {key: count for key, count in seen.items() if count > 1}
    return {
        "row_count": len(rows),
        "missing_canonical_name_count": missing_name,
        "missing_lgd_code_count": missing_lgd,
        "duplicate_key_count": len(duplicate_keys),
        "duplicate_key_examples": list(sorted(duplicate_keys.items()))[:10],
        "critical_error_count": missing_name + missing_lgd + len(duplicate_keys),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage parsed LGD CSVs into normalized JSONL without DB writes.")
    parser.add_argument("--root", default="../data/raw/lgd")
    parser.add_argument("--out-root", default="../data/staged/geography_lgd")
    parser.add_argument("--country-code", default="IN")
    parser.add_argument("--default-state-code", default="09")
    parser.add_argument("--default-state-name", default="Uttar Pradesh")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    root = (script_dir.parent / args.root).resolve()
    out_root = (script_dir.parent / args.out_root).resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = out_root / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    source_files = {
        "districts": root / "up_districts.csv",
        "blocks": root / "up_blocks.csv",
        "villages": root / "up_villages.csv",
    }

    districts = _stage_districts(_read_csv(source_files["districts"]), tenant_country_code=args.country_code, default_state_code=args.default_state_code, default_state_name=args.default_state_name)
    blocks = _stage_blocks(_read_csv(source_files["blocks"]), tenant_country_code=args.country_code, default_state_code=args.default_state_code, default_state_name=args.default_state_name)
    villages = _stage_villages(_read_csv(source_files["villages"]), tenant_country_code=args.country_code, default_state_code=args.default_state_code, default_state_name=args.default_state_name)

    staged_sets = {
        "districts": districts,
        "blocks": blocks,
        "villages": villages,
    }

    outputs = {}
    for name, rows in staged_sets.items():
        path = out_dir / f"{name}.jsonl"
        _write_jsonl(path, rows)
        outputs[name] = {
            "file": str(path),
            "row_count": len(rows),
            "validation": _validate(rows),
        }

    manifest = {
        "schema_version": "lgd_geography_staging_manifest.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "country_code": args.country_code,
        "default_state_code": args.default_state_code,
        "default_state_name": args.default_state_name,
        "source_files": {
            name: {
                "path": str(path),
                "sha256": _sha256_file(path),
            }
            for name, path in source_files.items()
        },
        "outputs": outputs,
        "ready_for_diff_design": all(item["validation"]["critical_error_count"] == 0 for item in outputs.values()),
        "message": "Staging completed without database writes.",
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
