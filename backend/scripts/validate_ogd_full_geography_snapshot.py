#!/usr/bin/env python3
"""Validate OGD LGD-village/PIN and postal PIN raw snapshots without DB writes.

Reads saved JSON pages from fetch_ogd_geography_snapshots.py and emits:
- source coverage counts
- PIN format checks
- duplicate checks
- LGD village/PIN to postal PIN overlap
- normalized staging JSONL files for later diff/apply design

No database writes.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PIN_RE = re.compile(r"^[1-9][0-9]{5}$")

LGD_RESOURCE = "lgd_villages_pin_codes"
POSTAL_RESOURCE = "all_india_pincode_directory"

LGD_REQUIRED = [
    "stateCode",
    "stateNameEnglish",
    "districtCode",
    "districtNameEnglish",
    "subdistrictCode",
    "subdistrictNameEnglish",
    "villageCode",
    "villageNameEnglish",
    "pincode",
]

POSTAL_REQUIRED = [
    "circlename",
    "regionname",
    "divisionname",
    "officename",
    "pincode",
    "officetype",
    "delivery",
    "district",
    "statename",
    "latitude",
    "longitude",
]


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records")
    if not isinstance(records, list):
        return []
    return [row for row in records if isinstance(row, dict)]


def _latest_manifest(root: Path) -> Path:
    manifests = sorted(root.glob("*/manifest.json"))
    if not manifests:
        raise SystemExit(f"No manifest.json found under {root}")
    return manifests[-1]


def _manifest_resource(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    for resource in manifest.get("resources") or []:
        if resource.get("name") == name:
            return resource
    raise SystemExit(f"Resource {name} not found in manifest")


def _page_paths(snapshot_root: Path, resource: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for page in resource.get("pages") or []:
        if page.get("status") != "FETCHED":
            continue
        file_value = page.get("file")
        if not file_value:
            continue
        path = Path(file_value)
        if not path.is_absolute():
            path = snapshot_root.parents[1] / path
        if not path.exists():
            fallback = snapshot_root / resource["name"] / Path(file_value).name
            path = fallback
        if path.exists():
            paths.append(path)
    return sorted(paths)


def _iter_records(paths: list[Path]):
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in _records(payload):
            yield path, row


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _pin(value: Any) -> str:
    return _clean(value).replace(" ", "")


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def _validate_lgd(snapshot_root: Path, resource: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    paths = _page_paths(snapshot_root, resource)
    row_count = 0
    invalid_pin_examples = []
    missing_required = Counter()
    state_counter = Counter()
    district_counter = Counter()
    subdistrict_counter = Counter()
    village_counter = Counter()
    pin_counter = Counter()
    village_pin_counter = Counter()
    state_pin_counter = Counter()
    staged_rows = []

    for path, row in _iter_records(paths):
        row_count += 1
        for key in LGD_REQUIRED:
            if not _clean(row.get(key)):
                missing_required[key] += 1

        pin = _pin(row.get("pincode"))
        if pin and PIN_RE.match(pin):
            pin_counter[pin] += 1
            state_pin_counter[(_clean(row.get("stateCode")), pin)] += 1
        elif len(invalid_pin_examples) < 25:
            invalid_pin_examples.append({"file": str(path), "pincode": pin, "row": {k: _clean(row.get(k)) for k in LGD_REQUIRED}})

        state_key = _clean(row.get("stateCode"))
        district_key = f"{state_key}:{_clean(row.get('districtCode'))}"
        subdistrict_key = f"{district_key}:{_clean(row.get('subdistrictCode'))}"
        village_key = f"{subdistrict_key}:{_clean(row.get('villageCode'))}"
        village_pin_key = f"{village_key}:{pin}"

        if state_key:
            state_counter[state_key] += 1
        if _clean(row.get("districtCode")):
            district_counter[district_key] += 1
        if _clean(row.get("subdistrictCode")):
            subdistrict_counter[subdistrict_key] += 1
        if _clean(row.get("villageCode")):
            village_counter[village_key] += 1
        if pin and PIN_RE.match(pin):
            village_pin_counter[village_pin_key] += 1

        staged_rows.append({
            "source": "OGD_LGD_VILLAGES_PIN_CODES",
            "state_lgd_code": state_key,
            "state_name": _clean(row.get("stateNameEnglish")),
            "district_lgd_code": _clean(row.get("districtCode")),
            "district_name": _clean(row.get("districtNameEnglish")),
            "subdistrict_lgd_code": _clean(row.get("subdistrictCode")),
            "subdistrict_name": _clean(row.get("subdistrictNameEnglish")),
            "village_lgd_code": _clean(row.get("villageCode")),
            "village_name": _clean(row.get("villageNameEnglish")),
            "pin_code": pin if PIN_RE.match(pin) else None,
            "source_row": row,
        })

    duplicate_village_pin = {key: count for key, count in village_pin_counter.items() if count > 1}
    duplicate_village_codes = {key: count for key, count in village_counter.items() if count > 1}

    staged_file = out_dir / "lgd_village_pin_links.jsonl"
    staged_count = _write_jsonl(staged_file, staged_rows)

    return {
        "resource": LGD_RESOURCE,
        "page_count": len(paths),
        "row_count": row_count,
        "reported_total": resource.get("reported_total"),
        "unique_state_count": len(state_counter),
        "unique_district_count": len(district_counter),
        "unique_subdistrict_count": len(subdistrict_counter),
        "unique_village_count": len(village_counter),
        "unique_pin_count": len(pin_counter),
        "missing_required_counts": dict(sorted(missing_required.items())),
        "invalid_pin_count": sum(1 for item in staged_rows if not item.get("pin_code")),
        "invalid_pin_examples": invalid_pin_examples,
        "duplicate_village_code_count": len(duplicate_village_codes),
        "duplicate_village_code_examples": list(sorted(duplicate_village_codes.items()))[:25],
        "duplicate_village_pin_count": len(duplicate_village_pin),
        "duplicate_village_pin_examples": list(sorted(duplicate_village_pin.items()))[:25],
        "top_states_by_rows": state_counter.most_common(20),
        "top_pins_by_lgd_village_links": pin_counter.most_common(20),
        "staged_file": str(staged_file),
        "staged_count": staged_count,
        "pin_set": set(pin_counter.keys()),
    }


def _validate_postal(snapshot_root: Path, resource: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    paths = _page_paths(snapshot_root, resource)
    row_count = 0
    invalid_pin_examples = []
    missing_required = Counter()
    pin_counter = Counter()
    state_counter = Counter()
    office_counter = Counter()
    lat_lng_missing = 0
    staged_rows = []

    for path, row in _iter_records(paths):
        row_count += 1
        for key in POSTAL_REQUIRED:
            if not _clean(row.get(key)):
                missing_required[key] += 1

        pin = _pin(row.get("pincode"))
        if pin and PIN_RE.match(pin):
            pin_counter[pin] += 1
        elif len(invalid_pin_examples) < 25:
            invalid_pin_examples.append({"file": str(path), "pincode": pin, "row": {k: _clean(row.get(k)) for k in POSTAL_REQUIRED}})

        state = _clean(row.get("statename"))
        office = _clean(row.get("officename"))
        if state:
            state_counter[state] += 1
        if office and pin:
            office_counter[f"{pin}:{office.upper()}"] += 1
        if not _clean(row.get("latitude")) or not _clean(row.get("longitude")):
            lat_lng_missing += 1

        staged_rows.append({
            "source": "OGD_ALL_INDIA_PINCODE_DIRECTORY",
            "pin_code": pin if PIN_RE.match(pin) else None,
            "office_name": office,
            "office_type": _clean(row.get("officetype")),
            "delivery_status": _clean(row.get("delivery")),
            "circle_name": _clean(row.get("circlename")),
            "region_name": _clean(row.get("regionname")),
            "division_name": _clean(row.get("divisionname")),
            "postal_district_name": _clean(row.get("district")),
            "postal_state_name": state,
            "latitude": _clean(row.get("latitude")) or None,
            "longitude": _clean(row.get("longitude")) or None,
            "source_row": row,
        })

    duplicate_offices = {key: count for key, count in office_counter.items() if count > 1}

    staged_file = out_dir / "postal_references.jsonl"
    staged_count = _write_jsonl(staged_file, staged_rows)

    return {
        "resource": POSTAL_RESOURCE,
        "page_count": len(paths),
        "row_count": row_count,
        "reported_total": resource.get("reported_total"),
        "unique_pin_count": len(pin_counter),
        "unique_postal_state_count": len(state_counter),
        "missing_required_counts": dict(sorted(missing_required.items())),
        "invalid_pin_count": sum(1 for item in staged_rows if not item.get("pin_code")),
        "invalid_pin_examples": invalid_pin_examples,
        "missing_lat_lng_count": lat_lng_missing,
        "duplicate_pin_office_count": len(duplicate_offices),
        "duplicate_pin_office_examples": list(sorted(duplicate_offices.items()))[:25],
        "top_postal_states_by_rows": state_counter.most_common(20),
        "top_pins_by_post_offices": pin_counter.most_common(20),
        "staged_file": str(staged_file),
        "staged_count": staged_count,
        "pin_set": set(pin_counter.keys()),
    }


def _strip_sets(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {k: _strip_sets(v) for k, v in value.items() if k != "pin_set"}
    if isinstance(value, list):
        return [_strip_sets(v) for v in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate full OGD geography/PIN snapshot without DB writes.")
    parser.add_argument("--raw-root", default="../data/raw/ogd_geography")
    parser.add_argument("--manifest")
    parser.add_argument("--out-root", default="../data/staged/ogd_geography")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    raw_root = (script_dir.parent / args.raw_root).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else _latest_manifest(raw_root)
    snapshot_root = manifest_path.parent

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_root = (script_dir.parent / args.out_root).resolve()
    out_dir = out_root / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    lgd = _validate_lgd(snapshot_root, _manifest_resource(manifest, LGD_RESOURCE), out_dir)
    postal = _validate_postal(snapshot_root, _manifest_resource(manifest, POSTAL_RESOURCE), out_dir)

    lgd_pins = lgd["pin_set"]
    postal_pins = postal["pin_set"]

    overlap = {
        "lgd_unique_pin_count": len(lgd_pins),
        "postal_unique_pin_count": len(postal_pins),
        "common_pin_count": len(lgd_pins & postal_pins),
        "lgd_pins_missing_from_postal_count": len(lgd_pins - postal_pins),
        "postal_pins_without_lgd_village_link_count": len(postal_pins - lgd_pins),
        "lgd_pins_missing_from_postal_examples": sorted(lgd_pins - postal_pins)[:50],
        "postal_pins_without_lgd_village_link_examples": sorted(postal_pins - lgd_pins)[:50],
    }

    result = {
        "schema_version": "ogd_full_geography_snapshot_validation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "snapshot_status": manifest.get("status"),
        "is_read_only": True,
        "outputs_dir": str(out_dir),
        "lgd_villages_pin_codes": lgd,
        "all_india_pincode_directory": postal,
        "pin_overlap": overlap,
        "ready_for_apply_design": (
            lgd["row_count"] > 0
            and postal["row_count"] > 0
            and lgd["invalid_pin_count"] == 0
            and postal["invalid_pin_count"] == 0
        ),
        "next_actions": [
            "Review counts and overlap before designing DB apply.",
            "Use LGD rows for village-to-PIN links.",
            "Use postal rows for PIN/post-office references.",
            "Do not infer LGD village identity from postal office names without review.",
        ],
    }

    report_path = out_dir / "validation_report.json"
    report_path.write_text(json.dumps(_strip_sets(result), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps(_strip_sets(result), indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
