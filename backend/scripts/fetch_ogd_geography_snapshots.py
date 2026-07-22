#!/usr/bin/env python3
"""Fetch raw OGD geography/PIN-code snapshots without database writes.

This script is acquisition-only. It saves source JSON pages plus a manifest so
later staging/import work can be deterministic and auditable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_URL = "https://api.data.gov.in/resource"

RESOURCES = {
    "lgd_villages_pin_codes": {
        "resource_id": "f17a1608-5f10-4610-bb50-a63c80d83974",
        "label": "Local Government Directory (LGD) - Villages with PIN Codes",
        "license": "Government Open Data License - India",
    },
    "all_india_pincode_directory": {
        "resource_id": "5c2f62fe-5afa-4119-a499-fec9d604d5bd",
        "label": "All India Pincode Directory till last month",
        "license": "Government Open Data License - India",
    },
}


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _records(payload: dict[str, Any]) -> list[Any]:
    records = payload.get("records")
    return records if isinstance(records, list) else []


def _request_page(resource_id: str, *, api_key: str, offset: int, limit: int, timeout: int) -> tuple[int, dict[str, Any], bytes]:
    query = urllib.parse.urlencode({
        "api-key": api_key,
        "format": "json",
        "offset": str(offset),
        "limit": str(limit),
    })
    url = f"{BASE_URL}/{resource_id}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "agri-os-ogd-geography-fetcher/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        payload = json.loads(body.decode("utf-8"))
        return response.status, payload, body


def _fetch_resource(name: str, spec: dict[str, str], *, api_key: str, out_dir: Path, page_limit: int, max_pages: int, sleep_seconds: float, timeout: int, dry_run: bool) -> dict[str, Any]:
    resource_id = spec["resource_id"]
    resource_dir = out_dir / name
    resource_dir.mkdir(parents=True, exist_ok=True)

    pages: list[dict[str, Any]] = []
    total_records_seen = 0
    detected_total = None
    offset = 0

    for page_index in range(max_pages):
        if dry_run:
            pages.append({
                "page_index": page_index,
                "offset": offset,
                "limit": page_limit,
                "status": "DRY_RUN_NOT_FETCHED",
                "target_url": f"{BASE_URL}/{resource_id}?api-key=<redacted>&format=json&offset={offset}&limit={page_limit}",
            })
            break

        try:
            status_code, payload, raw_body = _request_page(resource_id, api_key=api_key, offset=offset, limit=page_limit, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body_preview = exc.read().decode("utf-8", errors="replace")[:1000]
            pages.append({
                "page_index": page_index,
                "offset": offset,
                "limit": page_limit,
                "status": "HTTP_ERROR",
                "status_code": exc.code,
                "body_preview": body_preview,
            })
            break

        page_bytes = _json_bytes(payload)
        page_name = f"page_{page_index:05d}_offset_{offset}.json"
        page_path = resource_dir / page_name
        page_path.write_bytes(page_bytes)

        records = _records(payload)
        detected_total = payload.get("total", detected_total)
        total_records_seen += len(records)

        pages.append({
            "page_index": page_index,
            "offset": offset,
            "limit": page_limit,
            "status": "FETCHED",
            "status_code": status_code,
            "record_count": len(records),
            "payload_count": payload.get("count"),
            "payload_total": payload.get("total"),
            "file": str(page_path.relative_to(out_dir.parent.parent.parent)),
            "sha256": _sha256_bytes(page_bytes),
            "raw_response_sha256": _sha256_bytes(raw_body),
        })

        if len(records) < page_limit:
            break

        offset += page_limit
        if sleep_seconds:
            time.sleep(sleep_seconds)

    return {
        "name": name,
        "resource_id": resource_id,
        "label": spec["label"],
        "license": spec["license"],
        "page_count": len(pages),
        "records_seen": total_records_seen,
        "reported_total": detected_total,
        "pages": pages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch raw OGD geography snapshots without DB writes.")
    parser.add_argument("--resource", choices=sorted(RESOURCES.keys()) + ["all"], default="all")
    parser.add_argument("--page-limit", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-root", default="../data/raw/ogd_geography")
    args = parser.parse_args()

    api_key = os.getenv("DATA_GOV_IN_API_KEY") or os.getenv("OGD_API_KEY")
    generated_at = datetime.now(timezone.utc)
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    out_root = (Path(__file__).resolve().parent.parent / args.out_root).resolve()
    out_dir = out_root / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = RESOURCES if args.resource == "all" else {args.resource: RESOURCES[args.resource]}

    if not api_key and not args.dry_run:
        manifest = {
            "schema_version": "ogd_geography_raw_snapshot_manifest.v1",
            "generated_at": generated_at.isoformat(),
            "status": "API_KEY_MISSING",
            "message": "Set DATA_GOV_IN_API_KEY or run with --dry-run. No source pages were fetched.",
            "resources_requested": list(selected.keys()),
            "output_dir": str(out_dir),
        }
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_bytes(_json_bytes(manifest))
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    resources = [
        _fetch_resource(
            name,
            spec,
            api_key=api_key or "DRY_RUN",
            out_dir=out_dir,
            page_limit=args.page_limit,
            max_pages=args.max_pages,
            sleep_seconds=args.sleep_seconds,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )
        for name, spec in selected.items()
    ]

    manifest = {
        "schema_version": "ogd_geography_raw_snapshot_manifest.v1",
        "generated_at": generated_at.isoformat(),
        "status": "DRY_RUN" if args.dry_run else "FETCHED",
        "api_key_status": "PRESENT_REDACTED" if api_key else "DRY_RUN_NOT_REQUIRED",
        "base_url": BASE_URL,
        "page_limit": args.page_limit,
        "max_pages": args.max_pages,
        "output_dir": str(out_dir),
        "resources": resources,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest))
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
