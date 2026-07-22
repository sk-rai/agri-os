#!/usr/bin/env python3
"""Audit parsed LGD CSV files for staged import readiness without DB writes."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

PIN_RE = re.compile(r"^[1-9][0-9]{5}$")


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _read_csv(path: Path, sample_limit: int) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        samples = []
        row_count = 0
        for row in reader:
            row_count += 1
            if len(samples) < sample_limit:
                samples.append({str(k): ("" if v is None else str(v)[:120]) for k, v in row.items()})
    return {"headers": headers, "row_count": row_count, "samples": samples}


def _find_headers(headers: list[str], *hints: str) -> list[str]:
    normalized = {header: _norm(header) for header in headers}
    matches = []
    for header, norm in normalized.items():
        if any(_norm(hint) in norm for hint in hints):
            matches.append(header)
    return sorted(set(matches))


def _validate_pin_samples(samples: list[dict[str, str]], pin_headers: list[str]) -> list[str]:
    bad: list[str] = []
    for row in samples:
        for header in pin_headers:
            raw = row.get(header, "")
            for token in re.split(r"[,;/|\s]+", str(raw).strip()):
                if token and not PIN_RE.match(token):
                    bad.append(token)
                    if len(bad) >= 10:
                        return bad
    return bad


def _role_readiness(role: str, info: dict[str, Any]) -> dict[str, Any]:
    headers = info["headers"]
    samples = info["samples"]

    lgd_headers = _find_headers(headers, "lgd", "code")
    name_headers = _find_headers(headers, "name", "district", "block", "village")
    parent_headers = _find_headers(headers, "state", "district", "block", "subdistrict")
    pin_headers = _find_headers(headers, "pin", "pincode")

    requirements = {
        "DISTRICTS": {
            "has_name": bool(name_headers),
            "has_lgd_or_code": bool(lgd_headers),
            "has_parent_state_hint": bool(parent_headers),
        },
        "BLOCKS": {
            "has_name": bool(name_headers),
            "has_lgd_or_code": bool(lgd_headers),
            "has_parent_district_hint": bool(parent_headers),
        },
        "VILLAGES": {
            "has_name": bool(name_headers),
            "has_lgd_or_code": bool(lgd_headers),
            "has_parent_hint": bool(parent_headers),
            "pin_values_look_valid": not _validate_pin_samples(samples, pin_headers) if pin_headers else True,
        },
    }.get(role, {})

    return {
        "role": role,
        "row_count": info["row_count"],
        "headers": headers,
        "classified_headers": {
            "lgd_or_code": lgd_headers,
            "name": name_headers,
            "parent": parent_headers,
            "pin": pin_headers,
        },
        "requirements": requirements,
        "ready_for_mapper_design": bool(info["row_count"]) and all(requirements.values()) if requirements else False,
        "invalid_pin_examples": _validate_pin_samples(samples, pin_headers),
        "sample_rows": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit parsed LGD CSV staging readiness.")
    parser.add_argument("--root", default="../data/raw/lgd")
    parser.add_argument("--sample-limit", type=int, default=2)
    args = parser.parse_args()

    root = (Path(__file__).resolve().parent.parent / args.root).resolve()
    targets = {
        "DISTRICTS": root / "up_districts.csv",
        "BLOCKS": root / "up_blocks.csv",
        "VILLAGES": root / "up_villages.csv",
    }

    resources = []
    for role, path in targets.items():
        if not path.exists():
            resources.append({
                "role": role,
                "path": str(path),
                "status": "MISSING",
                "ready_for_mapper_design": False,
            })
            continue
        info = _read_csv(path, args.sample_limit)
        resource = _role_readiness(role, info)
        resource["path"] = str(path)
        resource["status"] = "PRESENT"
        resources.append(resource)

    result = {
        "schema_version": "lgd_parsed_csv_staging_readiness.v1",
        "root": str(root),
        "resources": resources,
        "ready_for_staging_mapper": all(item.get("ready_for_mapper_design") for item in resources),
        "next_actions": [
            "Use these parsed CSV headers to define normalized staging records.",
            "Keep mapper no-DB-write until diff/apply contracts are reviewed.",
            "For all-India CSV/XML files, run local source inventory first and map each file into the same staged shape.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
