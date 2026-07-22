#!/usr/bin/env python3
"""Read-only probe for India OGD geography/PIN-code resources.

This script does not write to the database. It is safe to run before import work.
If DATA_GOV_IN_API_KEY is missing, it prints setup guidance and exits 0.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE_URL = "https://api.data.gov.in/resource"

RESOURCES = {
    "lgd_villages_pin_codes": {
        "resource_id": "f17a1608-5f10-4610-bb50-a63c80d83974",
        "label": "Local Government Directory (LGD) - Villages with PIN Codes",
        "role": "canonical_lgd_village_pin_reference",
        "license": "Government Open Data License - India",
    },
    "all_india_pincode_directory": {
        "resource_id": "5c2f62fe-5afa-4119-a499-fec9d604d5bd",
        "label": "All India Pincode Directory till last month",
        "role": "india_post_postal_reference",
        "license": "Government Open Data License - India",
    },
}


def _field_names(payload: dict[str, Any]) -> list[str]:
    fields = payload.get("field") or payload.get("fields") or []
    names: list[str] = []
    if isinstance(fields, list):
        for item in fields:
            if isinstance(item, dict):
                name = item.get("id") or item.get("name") or item.get("label")
                if name:
                    names.append(str(name))
            elif item:
                names.append(str(item))
    return names


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records")
    if isinstance(records, list):
        return [row for row in records if isinstance(row, dict)]
    return []


def _truncated_sample(records: list[dict[str, Any]], include_sample: bool) -> dict[str, Any] | None:
    if not include_sample or not records:
        return None
    sample: dict[str, Any] = {}
    for key, value in records[0].items():
        text = "" if value is None else str(value)
        sample[str(key)] = text[:160]
    return sample


def _probe_resource(name: str, spec: dict[str, str], *, api_key: str, limit: int, timeout: int, include_sample: bool) -> dict[str, Any]:
    resource_id = spec["resource_id"]
    query = urllib.parse.urlencode({
        "api-key": api_key,
        "format": "json",
        "offset": "0",
        "limit": str(limit),
    })
    url = f"{BASE_URL}/{resource_id}?{query}"

    request = urllib.request.Request(url, headers={"User-Agent": "agri-os-geography-readiness-probe/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.status
            body = response.read()
            payload = json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:800]
        return {
            "name": name,
            "resource_id": resource_id,
            "label": spec["label"],
            "healthy": False,
            "status_code": exc.code,
            "error": "HTTP_ERROR",
            "body_preview": body,
        }
    except Exception as exc:
        return {
            "name": name,
            "resource_id": resource_id,
            "label": spec["label"],
            "healthy": False,
            "error": exc.__class__.__name__,
            "message": str(exc),
        }

    records = _records(payload)
    return {
        "name": name,
        "resource_id": resource_id,
        "label": spec["label"],
        "role": spec["role"],
        "license": spec["license"],
        "healthy": status_code == 200,
        "status_code": status_code,
        "total": payload.get("total"),
        "count": payload.get("count"),
        "offset": payload.get("offset"),
        "limit": limit,
        "field_count": len(_field_names(payload)),
        "field_names": _field_names(payload),
        "record_count": len(records),
        "sample_record_keys": sorted(records[0].keys()) if records else [],
        "sample_record": _truncated_sample(records, include_sample),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe OGD India geography resources without database writes.")
    parser.add_argument("--limit", type=int, default=1, help="Maximum rows to fetch from each resource.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument("--include-sample", action="store_true", help="Include one truncated sample record for schema inspection.")
    args = parser.parse_args()

    api_key = os.getenv("DATA_GOV_IN_API_KEY") or os.getenv("OGD_API_KEY")
    generated_at = datetime.now(timezone.utc).isoformat()

    if not api_key:
        print(json.dumps({
            "schema_version": "ogd_geography_source_probe.v1",
            "generated_at": generated_at,
            "api_key_status": "MISSING",
            "healthy": False,
            "message": "Set DATA_GOV_IN_API_KEY after generating a data.gov.in API key. No network probe was attempted.",
            "resources": [
                {
                    "name": name,
                    "resource_id": spec["resource_id"],
                    "label": spec["label"],
                    "probe_url_template": f"{BASE_URL}/{spec['resource_id']}?api-key=<redacted>&format=json&offset=0&limit={args.limit}",
                }
                for name, spec in RESOURCES.items()
            ],
        }, indent=2, sort_keys=True))
        return 0

    results = [
        _probe_resource(name, spec, api_key=api_key, limit=args.limit, timeout=args.timeout, include_sample=args.include_sample)
        for name, spec in RESOURCES.items()
    ]
    print(json.dumps({
        "schema_version": "ogd_geography_source_probe.v1",
        "generated_at": generated_at,
        "api_key_status": "PRESENT_REDACTED",
        "healthy": all(item.get("healthy") for item in results),
        "resources": results,
        "runtime_decision": "Use these APIs for acquisition/refresh/probe jobs, then replicate validated snapshots locally for app runtime.",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
