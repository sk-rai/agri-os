#!/usr/bin/env python3
"""Validate locally saved OGD geography raw snapshots without database writes."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

PIN_RE = re.compile(r"^[1-9][0-9]{5}$")

PIN_KEY_HINTS = {"pincode", "pin_code", "pin", "officepincode"}
LGD_KEY_HINTS = {"lgd", "village_code", "localbody_code", "village_lgd_code"}
NAME_KEY_HINTS = {"village", "villagename", "office_name", "officename", "district", "statename", "state"}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records")
    if isinstance(records, list):
        return [row for row in records if isinstance(row, dict)]
    return []


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(key).lower())


def _classify_keys(keys: list[str]) -> dict[str, list[str]]:
    normalized = {key: _normalize_key(key) for key in keys}
    pin_keys = [key for key, norm in normalized.items() if norm in PIN_KEY_HINTS or "pincode" in norm or norm.endswith("pin")]
    lgd_keys = [key for key, norm in normalized.items() if "lgd" in norm or norm in LGD_KEY_HINTS]
    name_keys = [key for key, norm in normalized.items() if any(hint in norm for hint in NAME_KEY_HINTS)]
    return {
        "pin_keys": sorted(set(pin_keys)),
        "lgd_code_keys": sorted(set(lgd_keys)),
        "name_keys": sorted(set(name_keys)),
    }


def _pin_values(record: dict[str, Any], pin_keys: list[str]) -> list[str]:
    values: list[str] = []
    for key in pin_keys:
        value = record.get(key)
        if value is None:
            continue
        for token in re.split(r"[,;/|\s]+", str(value).strip()):
            token = token.strip()
            if token:
                values.append(token)
    return values


def _validate_resource_pages(manifest_dir: Path, resource: dict[str, Any]) -> dict[str, Any]:
    key_counter: Counter[str] = Counter()
    invalid_pin_examples: list[dict[str, Any]] = []
    page_summaries: list[dict[str, Any]] = []
    total_records = 0

    for page in resource.get("pages") or []:
        if page.get("status") != "FETCHED" or not page.get("file"):
            page_summaries.append({
                "page_index": page.get("page_index"),
                "status": page.get("status"),
                "record_count": page.get("record_count", 0),
            })
            continue

        page_file = manifest_dir.parent.parent.parent / page["file"]
        if not page_file.exists():
            page_summaries.append({
                "page_index": page.get("page_index"),
                "status": "PAGE_FILE_MISSING",
                "file": page.get("file"),
            })
            continue

        payload = _load_json(page_file)
        records = _records(payload)
        total_records += len(records)

        for record in records:
            key_counter.update(str(key) for key in record.keys())

        key_info = _classify_keys(list(key_counter.keys()))
        for record in records[:100]:
            for value in _pin_values(record, key_info["pin_keys"]):
                if not PIN_RE.match(value):
                    invalid_pin_examples.append({"value": value, "record_keys": sorted(record.keys())[:12]})
                    if len(invalid_pin_examples) >= 10:
                        break
            if len(invalid_pin_examples) >= 10:
                break

        page_summaries.append({
            "page_index": page.get("page_index"),
            "status": "VALIDATED",
            "record_count": len(records),
            "field_count": len(records[0].keys()) if records else 0,
        })

    key_info = _classify_keys(list(key_counter.keys()))
    return {
        "name": resource.get("name"),
        "resource_id": resource.get("resource_id"),
        "status": "VALIDATED" if total_records else "NO_FETCHED_RECORDS",
        "record_count": total_records,
        "field_count": len(key_counter),
        "field_names": sorted(key_counter.keys()),
        "classified_fields": key_info,
        "invalid_pin_example_count": len(invalid_pin_examples),
        "invalid_pin_examples": invalid_pin_examples,
        "page_summaries": page_summaries,
        "readiness": {
            "has_pin_field": bool(key_info["pin_keys"]),
            "has_lgd_code_field": bool(key_info["lgd_code_keys"]),
            "has_name_field": bool(key_info["name_keys"]),
            "safe_for_staging_design": total_records > 0 and bool(key_info["name_keys"]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate raw OGD geography snapshot manifests/pages.")
    parser.add_argument("manifest", nargs="?", help="Path to manifest.json. Defaults to newest under ../data/raw/ogd_geography.")
    args = parser.parse_args()

    if args.manifest:
        manifest_path = Path(args.manifest).resolve()
    else:
        raw_root = (Path(__file__).resolve().parent.parent / "../data/raw/ogd_geography").resolve()
        manifests = sorted(raw_root.glob("*/manifest.json"))
        manifest_path = manifests[-1] if manifests else None

    if not manifest_path or not manifest_path.exists():
        print(json.dumps({
            "schema_version": "ogd_geography_snapshot_validation.v1",
            "status": "NO_MANIFEST_FOUND",
            "message": "Run fetch_ogd_geography_snapshots.py first.",
        }, indent=2, sort_keys=True))
        return 0

    manifest = _load_json(manifest_path)
    resources = manifest.get("resources") if isinstance(manifest.get("resources"), list) else []

    result = {
        "schema_version": "ogd_geography_snapshot_validation.v1",
        "manifest": str(manifest_path),
        "manifest_status": manifest.get("status"),
        "source_manifest_schema_version": manifest.get("schema_version"),
        "resource_count": len(resources),
        "resources": [
            _validate_resource_pages(manifest_path.parent, resource)
            for resource in resources
            if isinstance(resource, dict)
        ],
        "next_actions": [
            "Generate DATA_GOV_IN_API_KEY and fetch at least one page from each resource." if not resources else "Review classified fields before implementing staging transforms.",
            "Keep validation no-DB-write until diff/apply behavior is reviewed.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
