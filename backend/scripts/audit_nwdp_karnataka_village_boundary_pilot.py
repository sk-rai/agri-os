#!/usr/bin/env python3
"""Read-only Karnataka pilot audit for NWDP/GSI village boundary GeoJSON.

This script answers the first practical ingestion question:

Can the Karnataka village-boundary attributes be crosswalked to our existing
LGD geography hierarchy by code, or are they name/fuzzy/manual-review only?

Safety:
- Downloads only Karnataka GeoJSON/GeoJSON ZIP when requested or when no local file is supplied.
- Writes only to the chosen output/cache path.
- Does not write to the database.
- Optional DB read crosswalk is disabled unless --with-db-crosswalk is passed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

MANIFEST_SCRIPT = SCRIPT_DIR / "audit_nwdp_village_boundary_resources.py"
DEFAULT_CACHE = Path("/tmp/nwdp-karnataka-village-boundary.geojson")

CODE_HINTS = [
    "lgd",
    "village_code",
    "villagecode",
    "vill_code",
    "vcode",
    "vlcode",
    "district_code",
    "districtcode",
    "dist_code",
    "subdistrict_code",
    "subdistrictcode",
    "tehsil_code",
    "taluk_code",
    "block_code",
    "census",
]
VILLAGE_NAME_HINTS = ["village", "vill", "vil_name", "village_name", "name"]
DISTRICT_NAME_HINTS = ["district", "dist", "district_name", "dist_name"]
SUBDISTRICT_NAME_HINTS = ["subdistrict", "sub_district", "tehsil", "taluk", "block"]


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _fetch_bytes(url: str, timeout: int) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "agri-os-nwdp-karnataka-boundary-pilot/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        content_type = response.headers.get("content-type", "")
    return body, content_type


def _looks_like_json(body: bytes) -> bool:
    stripped = body.lstrip()
    return stripped.startswith(b"{") or stripped.startswith(b"[")


def _looks_like_zip(body: bytes) -> bool:
    return body[:4] == b"PK\x03\x04"


def _extract_geojson_from_zip(body: bytes) -> tuple[bytes | None, dict[str, Any]]:
    info: dict[str, Any] = {
        "archive_detected": True,
        "members": [],
        "selected_member": None,
    }
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = archive.namelist()
            info["members"] = members[:80]
            candidates = [
                name
                for name in members
                if name.lower().endswith((".geojson", ".json"))
            ]
            if not candidates:
                return None, info
            selected = candidates[0]
            info["selected_member"] = selected
            return archive.read(selected), info
    except Exception as exc:
        info["error"] = exc.__class__.__name__
        info["message"] = str(exc)
        return None, info


def _extract_download_candidates(resource_html: str, base_url: str) -> list[str]:
    hrefs = re.findall(r'''href=["']([^"']+)["']''', resource_html, flags=re.IGNORECASE)
    candidates = []
    for href in hrefs:
        absolute = urllib.parse.urljoin(base_url, href)
        lowered = absolute.lower()
        if "geojson" in lowered or "/download/" in lowered or "format=geojson" in lowered or lowered.endswith(".zip"):
            candidates.append(absolute)

    def score(url: str) -> tuple[int, int, int]:
        lowered = url.lower()
        return (
            5 if "/download/" in lowered else 0,
            4 if lowered.endswith(".zip") else 0,
            3 if "geojson" in lowered else 0,
        )

    return sorted(dict.fromkeys(candidates), key=score, reverse=True)


def _fetch_url(url: str, output: Path, timeout: int) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    body, content_type = _fetch_bytes(url, timeout)
    resolved_url = url
    resolution: dict[str, Any] = {
        "initial_url": url,
        "initial_content_type": content_type,
        "resource_page_detected": not _looks_like_json(body) and not _looks_like_zip(body),
        "download_candidates": [],
        "extracted_from_zip": False,
        "archive_info": None,
    }

    if _looks_like_zip(body):
        extracted, archive_info = _extract_geojson_from_zip(body)
        resolution["archive_info"] = archive_info
        if extracted is not None and _looks_like_json(extracted):
            body = extracted
            content_type = "application/geo+json; extracted-from-zip"
            resolution["extracted_from_zip"] = True

    elif not _looks_like_json(body):
        page_text = body.decode("utf-8", errors="replace")
        candidates = _extract_download_candidates(page_text, url)
        resolution["download_candidates"] = candidates[:12]
        for candidate in candidates:
            candidate_body, candidate_type = _fetch_bytes(candidate, timeout)
            resolution["last_candidate_url"] = candidate
            resolution["last_candidate_content_type"] = candidate_type

            if _looks_like_json(candidate_body):
                body = candidate_body
                content_type = candidate_type
                resolved_url = candidate
                break

            if _looks_like_zip(candidate_body):
                extracted, archive_info = _extract_geojson_from_zip(candidate_body)
                resolution["archive_info"] = archive_info
                if extracted is not None and _looks_like_json(extracted):
                    body = extracted
                    content_type = "application/geo+json; extracted-from-zip"
                    resolved_url = candidate
                    resolution["extracted_from_zip"] = True
                    break

    output.write_bytes(body)
    return {
        "url": resolved_url,
        "path": str(output),
        "size_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "content_type": content_type,
        "resolved_from_resource_page": resolved_url != url,
        "resolution": resolution,
    }


def _load_manifest_url(timeout: int) -> str | None:
    if not MANIFEST_SCRIPT.exists():
        return None

    import importlib.util

    spec = importlib.util.spec_from_file_location("nwdp_manifest", MANIFEST_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    raw_html = module._fetch_html(module.DATASET_URL, timeout)
    parsed = module._parse_resources(raw_html, module.DATASET_URL)

    candidates = [
        row
        for row in parsed["resources"]
        if row.get("state_or_ut") == "Karnataka" and row.get("format") == "GeoJSON" and row.get("url")
    ]
    if not candidates:
        return None
    return str(candidates[0]["url"])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_geojson(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def _properties(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties")
    return props if isinstance(props, dict) else {}


def _geometry(feature: dict[str, Any]) -> dict[str, Any]:
    geom = feature.get("geometry")
    return geom if isinstance(geom, dict) else {}


def _candidate_fields(keys: list[str], hints: list[str]) -> list[str]:
    result = []
    for key in keys:
        key_norm = _norm(key)
        if any(_norm(hint) in key_norm for hint in hints):
            result.append(key)
    return sorted(set(result))


def _string_values(features: list[dict[str, Any]], field: str, limit: int = 10) -> list[str]:
    values = []
    for feature in features:
        value = _properties(feature).get(field)
        if value is None or value == "":
            continue
        text = str(value)
        if text not in values:
            values.append(text)
        if len(values) >= limit:
            break
    return values


def _numeric_like_count(features: list[dict[str, Any]], field: str) -> int:
    count = 0
    for feature in features:
        value = _properties(feature).get(field)
        if value is None:
            continue
        if re.fullmatch(r"\d+", str(value).strip()):
            count += 1
    return count


def _collect_bbox_from_coords(coords: Any, bbox: list[float] | None = None) -> list[float] | None:
    if bbox is None:
        bbox = [180.0, 90.0, -180.0, -90.0]
    if isinstance(coords, list):
        if len(coords) >= 2 and all(isinstance(x, (int, float)) for x in coords[:2]):
            lng = float(coords[0])
            lat = float(coords[1])
            bbox[0] = min(bbox[0], lng)
            bbox[1] = min(bbox[1], lat)
            bbox[2] = max(bbox[2], lng)
            bbox[3] = max(bbox[3], lat)
        else:
            for child in coords:
                _collect_bbox_from_coords(child, bbox)
    return bbox


def _audit_geojson(path: Path, sample_limit: int) -> dict[str, Any]:
    payload = _load_geojson(path)
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        return {
            "healthy": False,
            "error": "NOT_FEATURE_COLLECTION",
            "top_level_type": payload.get("type") if isinstance(payload, dict) else type(payload).__name__,
        }

    all_keys = sorted({key for feature in features for key in _properties(feature).keys()})
    geom_types = Counter(str(_geometry(feature).get("type") or "MISSING") for feature in features)

    null_counts = {key: 0 for key in all_keys}
    distinct_counts: dict[str, set[str]] = {key: set() for key in all_keys}
    for feature in features:
        props = _properties(feature)
        for key in all_keys:
            value = props.get(key)
            if value is None or value == "":
                null_counts[key] += 1
            else:
                distinct_counts[key].add(str(value)[:240])

    code_fields = _candidate_fields(all_keys, CODE_HINTS)
    village_name_fields = _candidate_fields(all_keys, VILLAGE_NAME_HINTS)
    district_name_fields = _candidate_fields(all_keys, DISTRICT_NAME_HINTS)
    subdistrict_name_fields = _candidate_fields(all_keys, SUBDISTRICT_NAME_HINTS)

    bbox = None
    empty_geometry_count = 0
    for feature in features:
        geom = _geometry(feature)
        coords = geom.get("coordinates")
        if not coords:
            empty_geometry_count += 1
            continue
        bbox = _collect_bbox_from_coords(coords, bbox)

    sample_features = []
    for feature in features[:sample_limit]:
        props = _properties(feature)
        sample_features.append({
            "properties": {key: ("" if value is None else str(value)[:160]) for key, value in props.items()},
            "geometry_type": _geometry(feature).get("type"),
        })

    key_field_profiles = []
    for key in all_keys:
        numeric_like = _numeric_like_count(features, key)
        key_field_profiles.append({
            "field": key,
            "null_count": null_counts[key],
            "distinct_count_capped": len(distinct_counts[key]),
            "numeric_like_count": numeric_like,
            "sample_values": _string_values(features, key, 8),
            "looks_like_code": key in code_fields or numeric_like >= max(1, int(len(features) * 0.8)),
            "looks_like_village_name": key in village_name_fields,
            "looks_like_district_name": key in district_name_fields,
            "looks_like_subdistrict_name": key in subdistrict_name_fields,
        })

    exact_lgd_candidate_fields = [
        field for field in code_fields
        if "lgd" in _norm(field) or "villagecode" in _norm(field) or _norm(field) in {"vcode", "vlcode"}
    ]

    if exact_lgd_candidate_fields:
        crosswalk_case = "CASE_A_OR_B_CODE_CANDIDATES_PRESENT"
    elif village_name_fields and district_name_fields:
        crosswalk_case = "CASE_C_SCOPED_NAME_MATCH_PROBABLY_REQUIRED"
    else:
        crosswalk_case = "CASE_D_WEAK_OR_UNDOCUMENTED_ATTRIBUTES"

    return {
        "healthy": True,
        "top_level_type": payload.get("type"),
        "feature_count": len(features),
        "property_field_count": len(all_keys),
        "property_fields": all_keys,
        "geometry_type_counts": dict(sorted(geom_types.items())),
        "empty_geometry_count": empty_geometry_count,
        "computed_bbox_raw_coordinates": bbox,
        "coordinate_system_warning": "Coordinates appear projected/non-WGS84 if bbox exceeds lon/lat ranges; identify CRS before point-in-polygon use." if bbox and (bbox[0] < -180 or bbox[2] > 180 or bbox[1] < -90 or bbox[3] > 90) else None,
        "candidate_fields": {
            "code_fields": code_fields,
            "exact_lgd_candidate_fields": exact_lgd_candidate_fields,
            "village_name_fields": village_name_fields,
            "district_name_fields": district_name_fields,
            "subdistrict_name_fields": subdistrict_name_fields,
        },
        "crosswalk_case": crosswalk_case,
        "field_profiles": key_field_profiles,
        "sample_features": sample_features,
    }


def _db_crosswalk_summary(audit: dict[str, Any], source_path: Path, sample_limit: int) -> dict[str, Any]:
    try:
        from sqlalchemy import create_engine, text
    except Exception as exc:
        return {
            "attempted": True,
            "healthy": False,
            "error": exc.__class__.__name__,
            "message": str(exc),
            "note": "Optional DB read crosswalk requires SQLAlchemy.",
        }

    database_url = os.getenv("DATABASE_URL")
    settings_import = {"attempted": False}

    if not database_url:
        settings_import["attempted"] = True
        try:
            if str(BACKEND_ROOT) not in sys.path:
                sys.path.insert(0, str(BACKEND_ROOT))
            from app.core.config import settings
            database_url = getattr(settings, "database_url", None) or getattr(settings, "DATABASE_URL", None)
            settings_import["healthy"] = True
        except Exception as exc:
            settings_import.update({
                "healthy": False,
                "error": exc.__class__.__name__,
                "message": str(exc),
            })

    if not database_url:
        return {
            "attempted": True,
            "healthy": False,
            "error": "DATABASE_URL_MISSING",
            "settings_import": settings_import,
            "note": "Set DATABASE_URL or run from an environment where app.core.config is importable.",
        }

    fields = audit.get("candidate_fields") or {}
    candidate = next(iter(fields.get("exact_lgd_candidate_fields") or []), None)

    if not candidate:
        return {
            "attempted": True,
            "healthy": True,
            "crosswalk_attempted": False,
            "reason": "No exact LGD/village-code candidate field detected.",
        }

    features = _load_geojson(source_path).get("features") or []
    values = []
    for feature in features:
        value = _properties(feature).get(candidate)
        if value is not None and str(value).strip():
            values.append(str(value).strip())
        if len(values) >= sample_limit:
            break

    engine = create_engine(database_url)
    matched = 0
    rows = []
    with engine.connect() as conn:
        columns = conn.execute(
            text("""
                select column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = 'geography_villages'
            """)
        ).scalars().all()
        column_set = {str(column) for column in columns}

        wanted = [
            "id",
            "lgd_code",
            "name",
            "village_name",
            "village_name_english",
            "display_name",
            "district_id",
            "block_id",
            "sub_district_id",
            "subdistrict_id",
            "state_id",
        ]
        selected_columns = [column for column in wanted if column in column_set]
        if "lgd_code" not in column_set:
            return {
                "attempted": True,
                "healthy": False,
                "crosswalk_attempted": False,
                "error": "LGD_CODE_COLUMN_MISSING",
                "available_columns": sorted(column_set),
            }

        if not selected_columns:
            selected_columns = ["lgd_code"]

        select_sql = ", ".join(selected_columns)
        for value in values:
            result = conn.execute(
                text(f"""
                    select {select_sql}
                    from geography_villages
                    where cast(lgd_code as text) = :value
                    limit 3
                """),
                {"value": value},
            ).mappings().all()
            if result:
                matched += 1
            rows.append({
                "value": value,
                "match_count": len(result),
                "matches": [
                    {str(key): (None if row[key] is None else str(row[key])) for key in row.keys()}
                    for row in result
                ],
            })

    return {
        "attempted": True,
        "healthy": True,
        "crosswalk_attempted": True,
        "candidate_field": candidate,
        "available_columns": sorted(column_set),
        "selected_columns": selected_columns,
        "sample_value_count": len(values),
        "matched_sample_values": matched,
        "sample_matches": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Karnataka pilot audit for NWDP village boundary GeoJSON.")
    parser.add_argument("--geojson", help="Path to existing Karnataka GeoJSON file.")
    parser.add_argument("--url", help="Explicit Karnataka resource or direct download URL. If omitted, the NWDP manifest page is parsed.")
    parser.add_argument("--cache-path", default=str(DEFAULT_CACHE), help="Where to save downloaded/extracted GeoJSON.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--with-db-crosswalk", action="store_true", help="Attempt optional read-only sample crosswalk against geography_villages.")
    parser.add_argument("--output", help="Optional path to write JSON result.")
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).isoformat()
    download = None

    if args.geojson:
        geojson_path = Path(args.geojson)
        if not geojson_path.exists():
            print(json.dumps({"schema_version": "nwdp_karnataka_village_boundary_pilot_audit.v1", "healthy": False, "error": "GEOJSON_NOT_FOUND", "path": str(geojson_path)}, indent=2))
            return 0
    else:
        url = args.url or _load_manifest_url(args.timeout)
        if not url:
            print(json.dumps({"schema_version": "nwdp_karnataka_village_boundary_pilot_audit.v1", "healthy": False, "error": "KARNATAKA_GEOJSON_URL_NOT_FOUND"}, indent=2))
            return 0
        geojson_path = Path(args.cache_path)
        download = _fetch_url(url, geojson_path, args.timeout)

    file_summary = {
        "path": str(geojson_path),
        "size_bytes": geojson_path.stat().st_size,
        "sha256": _sha256(geojson_path),
    }

    try:
        audit = _audit_geojson(geojson_path, args.sample_limit)
    except Exception as exc:
        audit = {"healthy": False, "error": exc.__class__.__name__, "message": str(exc)}

    db_crosswalk = {"attempted": False}
    if args.with_db_crosswalk and audit.get("healthy"):
        db_crosswalk = _db_crosswalk_summary(audit, geojson_path, args.sample_limit)

    candidate_fields = audit.get("candidate_fields") or {}
    readiness = {
        "safe_read_only": True,
        "db_writes_attempted": False,
        "download_limited_to_karnataka_geojson": not bool(args.geojson),
        "has_exact_lgd_candidate_fields": bool(candidate_fields.get("exact_lgd_candidate_fields")),
        "has_village_name_fields": bool(candidate_fields.get("village_name_fields")),
        "has_district_name_fields": bool(candidate_fields.get("district_name_fields")),
        "ready_for_ingestion": False,
    }

    result = {
        "schema_version": "nwdp_karnataka_village_boundary_pilot_audit.v1",
        "generated_at": generated_at,
        "source": {
            "portal": "National Water Data Portal",
            "dataset": "Village Boundary",
            "producer_agency": "Geological Survey of India",
            "state_or_ut": "Karnataka",
            "format": "GeoJSON",
        },
        "claim_boundary": "Pilot inspects reference village-boundary geometry and attributes only; it does not establish cadastral parcel truth or ownership.",
        "download": download,
        "file": file_summary,
        "geojson_audit": audit,
        "db_crosswalk": db_crosswalk,
        "readiness": readiness,
        "next_actions": [
            "Review candidate identifier fields for LGD compatibility.",
            "If LGD village codes are absent, assess scoped district/subdistrict/village name matching risk.",
            "Validate geometry with a geospatial library before any ingestion.",
            "Do not load all-India boundaries until the manifest caveat is resolved or reviewed.",
        ],
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
