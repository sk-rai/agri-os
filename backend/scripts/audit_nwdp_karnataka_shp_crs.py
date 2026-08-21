#!/usr/bin/env python3
"""Read-only CRS audit for the NWDP/GSI Karnataka village-boundary SHP resource."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import re
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
MANIFEST_SCRIPT = SCRIPT_DIR / "audit_nwdp_village_boundary_resources.py"
DEFAULT_CACHE = Path("/tmp/nwdp-karnataka-village-boundary-shp.zip")
DEFAULT_OUTPUT = Path("/tmp/nwdp-karnataka-boundary-shp-crs.json")


class HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def fetch_bytes(url: str, timeout: int) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "agri-os-nwdp-karnataka-shp-crs-audit/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        content_type = response.headers.get("content-type", "")
    return body, content_type


def looks_like_zip(body: bytes) -> bool:
    return body[:4] == b"PK\x03\x04"


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()

def load_karnataka_shp_url(timeout: int) -> str | None:
    if not MANIFEST_SCRIPT.exists():
        return None

    spec = importlib.util.spec_from_file_location("nwdp_manifest", MANIFEST_SCRIPT)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    raw_html = module._fetch_html(module.DATASET_URL, timeout)
    parsed = module._parse_resources(raw_html, module.DATASET_URL)

    for row in parsed.get("resources") or []:
        if row.get("state_or_ut") == "Karnataka" and row.get("format") == "SHP" and row.get("url"):
            return str(row["url"])

    return None


def download_candidates(resource_html: str, base_url: str) -> list[str]:
    parser = HrefParser()
    parser.feed(resource_html)

    candidates: list[str] = []
    for href in parser.hrefs:
        absolute = urllib.parse.urljoin(base_url, href)
        lowered = absolute.lower()
        if "/download/" in lowered or "shp" in lowered or lowered.endswith(".zip"):
            candidates.append(absolute)

    def score(url: str) -> tuple[int, int, int]:
        lowered = url.lower()
        return (
            5 if "/download/" in lowered else 0,
            4 if lowered.endswith(".zip") else 0,
            3 if "shp" in lowered else 0,
        )

    return sorted(dict.fromkeys(candidates), key=score, reverse=True)


def fetch_shp_zip(url: str, output: Path, timeout: int) -> dict[str, Any]:
    body, content_type = fetch_bytes(url, timeout)
    resolved_url = url

    resolution: dict[str, Any] = {
        "initial_url": url,
        "initial_content_type": content_type,
        "resource_page_detected": not looks_like_zip(body),
        "download_candidates": [],
    }

    if not looks_like_zip(body):
        html = body.decode("utf-8", errors="replace")
        candidates = download_candidates(html, url)
        resolution["download_candidates"] = candidates[:12]

        for candidate in candidates:
            candidate_body, candidate_type = fetch_bytes(candidate, timeout)
            resolution["last_candidate_url"] = candidate
            resolution["last_candidate_content_type"] = candidate_type

            if looks_like_zip(candidate_body):
                body = candidate_body
                content_type = candidate_type
                resolved_url = candidate
                break

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(body)

    return {
        "url": resolved_url,
        "path": str(output),
        "size_bytes": len(body),
        "sha256": sha256_bytes(body),
        "content_type": content_type,
        "resolved_from_resource_page": resolved_url != url,
        "resolution": resolution,
    }

def extract_name(pattern_name: str, text: str) -> str | None:
    marker = pattern_name + '["'
    start = text.find(marker)
    if start < 0:
        return None
    start = start + len(marker)
    end = text.find('"', start)
    if end < 0:
        return None
    return text[start:end]


def crs_inference(prj_text: str | None) -> dict[str, Any]:
    text_value = prj_text or ""
    lowered = text_value.lower()

    authority = []
    for name, code in re.findall(r'AUTHORITY\["([^"]+)","([^"]+)"\]', text_value):
        authority.append({"name": name, "code": code})

    return {
        "has_prj": bool(text_value),
        "projected_cs_name": extract_name("PROJCS", text_value),
        "geographic_cs_name": extract_name("GEOGCS", text_value),
        "projection_name": extract_name("PROJECTION", text_value),
        "datum_name": extract_name("DATUM", text_value),
        "spheroid_name": extract_name("SPHEROID", text_value),
        "authority_candidates": authority,
        "mentions_wgs84": "wgs_1984" in lowered or "wgs 84" in lowered or "wgs84" in lowered,
        "mentions_utm": "transverse_mercator" in lowered or "utm" in lowered,
        "mentions_lambert": "lambert" in lowered,
        "mentions_albers": "albers" in lowered,
        "is_projected": "projcs[" in lowered,
    }


def inspect_zip(path: Path, sample_limit: int) -> dict[str, Any]:
    body = path.read_bytes()

    if not looks_like_zip(body):
        return {
            "healthy": False,
            "archive_detected": False,
            "error": "NOT_ZIP",
            "sha256": sha256_bytes(body),
            "size_bytes": len(body),
        }

    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members = archive.namelist()
        lower_members = [name.lower() for name in members]
        prj_members = [name for name in members if name.lower().endswith(".prj")]

        selected_prj_member = prj_members[0] if prj_members else None
        prj_text = None
        prj_sha256 = None

        if selected_prj_member:
            prj_bytes = archive.read(selected_prj_member)
            prj_text = prj_bytes.decode("utf-8", errors="replace").strip()
            prj_sha256 = sha256_bytes(prj_bytes)

        extensions = Counter(Path(name).suffix.lower() or "<none>" for name in members)

        return {
            "healthy": True,
            "archive_detected": True,
            "member_count": len(members),
            "members": members[:sample_limit],
            "extensions": dict(sorted(extensions.items())),
            "required_shapefile_components": {
                "has_shp": any(name.endswith(".shp") for name in lower_members),
                "has_shx": any(name.endswith(".shx") for name in lower_members),
                "has_dbf": any(name.endswith(".dbf") for name in lower_members),
                "has_prj": bool(prj_members),
            },
            "prj_members": prj_members,
            "selected_prj_member": selected_prj_member,
            "selected_prj_sha256": prj_sha256,
            "selected_prj_text": prj_text,
            "crs_inference": crs_inference(prj_text),
        }

def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Karnataka SHP CRS audit for NWDP village boundaries.")
    parser.add_argument("--url", help="Explicit Karnataka SHP resource or direct ZIP URL. If omitted, the NWDP manifest page is parsed.")
    parser.add_argument("--cache-path", default=str(DEFAULT_CACHE), help="Where to save the downloaded Karnataka SHP ZIP.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to write JSON result.")
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).isoformat()
    url = args.url or load_karnataka_shp_url(args.timeout)

    if not url:
        result = {
            "schema_version": "nwdp_karnataka_shp_crs_audit.v1",
            "generated_at": generated_at,
            "healthy": False,
            "error": "KARNATAKA_SHP_URL_NOT_FOUND",
            "safe_read_only": True,
        }
    else:
        download = fetch_shp_zip(url, Path(args.cache_path), args.timeout)
        archive = inspect_zip(Path(args.cache_path), args.sample_limit)
        crs = archive.get("crs_inference") or {}

        result = {
            "schema_version": "nwdp_karnataka_shp_crs_audit.v1",
            "generated_at": generated_at,
            "source": {
                "portal": "National Water Data Portal",
                "dataset": "Village Boundary",
                "producer_agency": "Geological Survey of India",
                "state_or_ut": "Karnataka",
                "format": "SHP",
            },
            "claim_boundary": "CRS audit inspects source archive metadata only; it does not validate topology, ingest geometry, or authorize runtime point-in-polygon use.",
            "download": download,
            "archive": archive,
            "readiness": {
                "safe_read_only": True,
                "db_writes_attempted": False,
                "downloads_limited_to_karnataka_shp": True,
                "shp_zip_healthy": bool(archive.get("healthy")),
                "prj_found": bool((archive.get("required_shapefile_components") or {}).get("has_prj")),
                "crs_name_found": bool(crs.get("projected_cs_name") or crs.get("geographic_cs_name")),
                "projected_crs_indicated": bool(crs.get("is_projected")),
                "ready_for_transform_planning": bool(archive.get("healthy") and crs.get("has_prj")),
                "ready_for_runtime_spatial_matching": False,
            },
            "next_actions": [
                "Confirm EPSG/CRS identity from .prj with a geospatial library such as pyproj/GDAL.",
                "Transform a small sample to WGS84 and verify Karnataka lon/lat bounds before point-in-polygon use.",
                "Keep CRS and village-code reconciliation separate: CRS may be solvable even while crosswalk remains review-gated.",
                "Do not ingest or run runtime spatial matching until transform and boundary-crosswalk policy are reviewed.",
            ],
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
