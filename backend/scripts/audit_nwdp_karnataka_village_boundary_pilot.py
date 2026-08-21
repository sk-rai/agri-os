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
import csv
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



def _load_nwdp_vlcode_rows(source_path: Path) -> list[dict[str, str]]:
    features = _load_geojson(source_path).get("features") or []
    rows: list[dict[str, str]] = []
    for feature in features:
        props = _properties(feature)
        vlcode = str(props.get("vlcode") or "").strip()
        rows.append({
            "vlcode": vlcode,
            "village": str(props.get("village") or "").strip(),
            "district": str(props.get("district") or "").strip(),
            "dtcode": str(props.get("dtcode") or "").strip(),
            "subdistrict": str(props.get("subdistric") or "").strip(),
            "sdcode": str(props.get("sdcode") or "").strip(),
            "block": str(props.get("block") or "").strip(),
            "bkcode": str(props.get("bkcode") or "").strip(),
            "src_agency": str(props.get("src_agency") or "").strip(),
            "_raw": props,
        })
    return rows


def _find_soi_reference_files() -> list[Path]:
    roots = [
        BACKEND_ROOT.parent / "data" / "staged" / "boundaries" / "survey_of_india",
        BACKEND_ROOT.parent / "data" / "staged" / "core_stack" / "soi_crosswalk",
    ]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".csv", ".json", ".html", ".txt", ".xlsx"}:
                files.append(path)
    return sorted(files)


def _extract_soi_code_tokens(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "suffix": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "tokens": [],
        "token_count": 0,
        "note": None,
    }

    tokens: set[str] = set()

    if path.suffix.lower() == ".csv":
        try:
            with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
                reader = csv.DictReader(handle)
                headers = reader.fieldnames or []
                code_headers = [
                    header for header in headers
                    if any(hint in _norm(header) for hint in ["lgd", "vlcode", "villagecode", "dtcode", "sdcode", "code"])
                ]
                for row in reader:
                    for header in code_headers:
                        value = str(row.get(header) or "").strip()
                        if value.isdigit():
                            tokens.add(value)
            result["code_headers"] = code_headers
        except Exception as exc:
            result["error"] = exc.__class__.__name__
            result["message"] = str(exc)

    elif path.suffix.lower() == ".json":
        try:
            text_payload = path.read_text(encoding="utf-8", errors="replace")
            payload = json.loads(text_payload)
            compact = json.dumps(payload)
            tokens.update(re.findall(r'"(?:lgd_code|vlcode|village_code|dtcode|sdcode|code)"\s*:\s*"?(\d+)"?', compact, flags=re.IGNORECASE))
        except Exception as exc:
            result["error"] = exc.__class__.__name__
            result["message"] = str(exc)

    else:
        # Do not parse XLSX binary deeply here. This is an inventory-level probe.
        try:
            text_payload = path.read_text(encoding="utf-8", errors="ignore")
            tokens.update(re.findall(r"\b\d{5,6}\b", text_payload))
        except Exception:
            result["note"] = "Binary or unsupported text parse; token extraction skipped."

    result["tokens"] = sorted(tokens)[:200]
    result["token_count"] = len(tokens)
    return result


def _soi_reference_overlap(vlcodes: set[str]) -> dict[str, Any]:
    files = _find_soi_reference_files()
    file_results = []
    union_tokens: set[str] = set()

    for path in files:
        item = _extract_soi_code_tokens(path)
        tokens = set(item.get("tokens") or [])
        union_tokens.update(tokens)
        item["overlap_with_nwdp_vlcode_count_capped"] = len(tokens & vlcodes)
        item["overlap_samples"] = sorted(tokens & vlcodes)[:20]
        file_results.append(item)

    return {
        "attempted": True,
        "reference_file_count": len(files),
        "reference_files": file_results,
        "union_token_count_capped_by_file_samples": len(union_tokens),
        "overlap_with_nwdp_vlcode_count_capped": len(union_tokens & vlcodes),
        "overlap_samples": sorted(union_tokens & vlcodes)[:40],
        "note": "SOI comparison is a lightweight local-reference token overlap, not a full geometry or authoritative code crosswalk.",
    }



def _float_value(value: Any) -> float | None:
    try:
        text = str(value or "").strip()
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _classify_unmatched_rows(rows: list[dict[str, str]], unmatched_codes: set[str], sample_limit: int) -> dict[str, Any]:
    unmatched_rows = [row for row in rows if row["vlcode"] in unmatched_codes]

    by_district = Counter(row["district"] or "UNKNOWN" for row in unmatched_rows)
    by_subdistrict = Counter(
        f'{row["district"] or "UNKNOWN"} / {row["subdistrict"] or "UNKNOWN"}'
        for row in unmatched_rows
    )
    by_bkcode = Counter(row["bkcode"] or "BLANK" for row in unmatched_rows)

    bkcode_zero = [row for row in unmatched_rows if row["bkcode"] in {"0", "0.0"}]
    bkcode_blank = [row for row in unmatched_rows if not row["bkcode"] or row["bkcode"].strip() == ""]

    population_zero = []
    population_nonzero = []
    rural_urban = Counter()
    name_equals_subdistrict = []
    forest_or_beat = []
    town_like = []

    for row in unmatched_rows:
        raw = row.get("_raw") or {}
        pop = _float_value(raw.get("total_population_village\n"))
        if pop == 0:
            population_zero.append(row)
        elif pop is not None and pop > 0:
            population_nonzero.append(row)

        rural_urban[str(raw.get("total_urban_rural") or "UNKNOWN").strip() or "UNKNOWN"] += 1

        village_norm = _norm(row["village"])
        subdistrict_norm = _norm(row["subdistrict"])
        block_norm = _norm(row["block"])

        if village_norm and village_norm in {subdistrict_norm, block_norm}:
            name_equals_subdistrict.append(row)

        if re.search(r"\b(beat|forest|rf|reserve|range)\b", row["village"], flags=re.IGNORECASE):
            forest_or_beat.append(row)

        if row["bkcode"] in {"0", "0.0"} or village_norm in {subdistrict_norm, block_norm}:
            town_like.append(row)

    duplicate_unmatched = [
        row for row in unmatched_rows
        if sum(1 for candidate in unmatched_rows if candidate["vlcode"] == row["vlcode"]) > 1
    ]

    def samples(items: list[dict[str, str]]) -> list[dict[str, str]]:
        return [
            {key: value for key, value in item.items() if key != "_raw"}
            for item in items[:sample_limit]
        ]

    return {
        "unmatched_feature_count": len(unmatched_rows),
        "unmatched_distinct_vlcode_count": len(unmatched_codes),
        "top_unmatched_districts": [{"district": key, "count": value} for key, value in by_district.most_common(20)],
        "top_unmatched_subdistricts": [{"district_subdistrict": key, "count": value} for key, value in by_subdistrict.most_common(25)],
        "top_unmatched_bkcodes": [{"bkcode": key, "count": value} for key, value in by_bkcode.most_common(20)],
        "bkcode_zero_count": len(bkcode_zero),
        "bkcode_blank_count": len(bkcode_blank),
        "population_zero_count": len(population_zero),
        "population_nonzero_count": len(population_nonzero),
        "rural_urban_counts": dict(sorted(rural_urban.items())),
        "name_equals_subdistrict_or_block_count": len(name_equals_subdistrict),
        "forest_or_beat_name_count": len(forest_or_beat),
        "town_like_or_bkcode_zero_count": len(town_like),
        "duplicate_unmatched_feature_count": len(duplicate_unmatched),
        "samples": {
            "bkcode_zero": samples(bkcode_zero),
            "population_zero": samples(population_zero),
            "population_nonzero": samples(population_nonzero),
            "name_equals_subdistrict_or_block": samples(name_equals_subdistrict),
            "forest_or_beat": samples(forest_or_beat),
            "duplicate_unmatched": samples(duplicate_unmatched),
            "general_unmatched": samples(unmatched_rows),
        },
    }




def _name_key(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("&", "and")
    text = re.sub(r"\b(taluk|taluka|tehsil|hobli|village|grama|gram|gp|tq|dist|district)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def _db_name_columns(conn: Any, table_name: str) -> list[str]:
    from sqlalchemy import text

    rows = conn.execute(
        text("""
            select column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = :table_name
        """),
        {"table_name": table_name},
    ).scalars().all()
    return [str(row) for row in rows]


def _first_existing(columns: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None



def _parent_code_drift_audit(source_path: Path, sample_limit: int) -> dict[str, Any]:
    rows = _load_nwdp_vlcode_rows(source_path)

    try:
        from sqlalchemy import create_engine, text
    except Exception as exc:
        return {"attempted": True, "healthy": False, "error": exc.__class__.__name__, "message": str(exc)}

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        try:
            if str(BACKEND_ROOT) not in sys.path:
                sys.path.insert(0, str(BACKEND_ROOT))
            from app.core.config import settings
            database_url = getattr(settings, "database_url", None) or getattr(settings, "DATABASE_URL", None)
        except Exception as exc:
            return {
                "attempted": True,
                "healthy": False,
                "error": "DATABASE_URL_MISSING",
                "settings_import_error": exc.__class__.__name__,
                "settings_import_message": str(exc),
            }

    engine = create_engine(database_url)
    with engine.connect() as conn:
        district_columns = set(_db_name_columns(conn, "geography_districts"))
        block_columns = set(_db_name_columns(conn, "geography_blocks"))
        village_columns = set(_db_name_columns(conn, "geography_villages"))

        district_lgd_col = _first_existing(district_columns, ["lgd_code"])
        district_name_col = _first_existing(district_columns, ["canonical_name", "census_name", "name", "district_name"])
        block_lgd_col = _first_existing(block_columns, ["lgd_code"])
        block_name_col = _first_existing(block_columns, ["canonical_name", "census_name", "name", "block_name"])
        village_lgd_col = _first_existing(village_columns, ["lgd_code"])

        if not district_lgd_col or not block_lgd_col or not village_lgd_col:
            return {
                "attempted": True,
                "healthy": False,
                "error": "REQUIRED_CODE_COLUMNS_MISSING",
                "columns": {
                    "geography_districts": sorted(district_columns),
                    "geography_blocks": sorted(block_columns),
                    "geography_villages": sorted(village_columns),
                },
            }

        district_db_rows = conn.execute(
            text(f"select cast({district_lgd_col} as text) as code, {district_name_col or district_lgd_col} as name from geography_districts where {district_lgd_col} is not null")
        ).mappings().all()
        block_db_rows = conn.execute(
            text(f"select cast({block_lgd_col} as text) as code, {block_name_col or block_lgd_col} as name from geography_blocks where {block_lgd_col} is not null")
        ).mappings().all()
        village_db_rows = conn.execute(
            text(f"select cast({village_lgd_col} as text) as code from geography_villages where {village_lgd_col} is not null")
        ).mappings().all()

    db_district_codes = {str(row["code"]) for row in district_db_rows if row.get("code")}
    db_block_codes = {str(row["code"]) for row in block_db_rows if row.get("code")}
    db_village_codes = {str(row["code"]) for row in village_db_rows if row.get("code")}

    nwdp_dt_codes = {row["dtcode"] for row in rows if row["dtcode"]}
    nwdp_sd_codes = {row["sdcode"] for row in rows if row["sdcode"]}
    nwdp_bk_codes = {row["bkcode"] for row in rows if row["bkcode"]}
    nwdp_vl_codes = {row["vlcode"] for row in rows if row["vlcode"]}

    unmatched_rows = [row for row in rows if row["vlcode"] and row["vlcode"] not in db_village_codes]

    unmatched_parent_patterns = Counter()
    unmatched_by_parent_match = {
        "district_code_matches": 0,
        "district_code_missing": 0,
        "sdcode_matches_block": 0,
        "sdcode_missing_block": 0,
        "bkcode_matches_block": 0,
        "bkcode_missing_block": 0,
        "both_sdcode_or_bkcode_match_block": 0,
        "neither_sdcode_nor_bkcode_match_block": 0,
    }

    samples = {
        "district_matches_block_missing": [],
        "district_missing": [],
        "block_code_matches": [],
        "no_parent_code_match": [],
    }

    for row in unmatched_rows:
        district_match = row["dtcode"] in db_district_codes
        sd_match = row["sdcode"] in db_block_codes
        bk_match = row["bkcode"] in db_block_codes

        if district_match:
            unmatched_by_parent_match["district_code_matches"] += 1
        else:
            unmatched_by_parent_match["district_code_missing"] += 1

        if sd_match:
            unmatched_by_parent_match["sdcode_matches_block"] += 1
        else:
            unmatched_by_parent_match["sdcode_missing_block"] += 1

        if bk_match:
            unmatched_by_parent_match["bkcode_matches_block"] += 1
        else:
            unmatched_by_parent_match["bkcode_missing_block"] += 1

        if sd_match or bk_match:
            unmatched_by_parent_match["both_sdcode_or_bkcode_match_block"] += 1
        else:
            unmatched_by_parent_match["neither_sdcode_nor_bkcode_match_block"] += 1

        pattern = f"dtcode={'Y' if district_match else 'N'}|sdcode={'Y' if sd_match else 'N'}|bkcode={'Y' if bk_match else 'N'}"
        unmatched_parent_patterns[pattern] += 1

        public = {key: value for key, value in row.items() if key != "_raw"}
        if district_match and not (sd_match or bk_match) and len(samples["district_matches_block_missing"]) < sample_limit:
            samples["district_matches_block_missing"].append(public)
        if not district_match and len(samples["district_missing"]) < sample_limit:
            samples["district_missing"].append(public)
        if (sd_match or bk_match) and len(samples["block_code_matches"]) < sample_limit:
            samples["block_code_matches"].append(public)
        if not district_match and not sd_match and not bk_match and len(samples["no_parent_code_match"]) < sample_limit:
            samples["no_parent_code_match"].append(public)

    return {
        "attempted": True,
        "healthy": True,
        "total_features": len(rows),
        "distinct_nwdp_dtcode_count": len(nwdp_dt_codes),
        "distinct_nwdp_sdcode_count": len(nwdp_sd_codes),
        "distinct_nwdp_bkcode_count": len(nwdp_bk_codes),
        "distinct_nwdp_vlcode_count": len(nwdp_vl_codes),
        "backend_district_code_count": len(db_district_codes),
        "backend_block_code_count": len(db_block_codes),
        "backend_village_code_count": len(db_village_codes),
        "district_code_match_count": len(nwdp_dt_codes & db_district_codes),
        "district_code_unmatched_count": len(nwdp_dt_codes - db_district_codes),
        "sdcode_as_block_match_count": len(nwdp_sd_codes & db_block_codes),
        "sdcode_as_block_unmatched_count": len(nwdp_sd_codes - db_block_codes),
        "bkcode_as_block_match_count": len(nwdp_bk_codes & db_block_codes),
        "bkcode_as_block_unmatched_count": len(nwdp_bk_codes - db_block_codes),
        "unmatched_village_feature_count": len(unmatched_rows),
        "unmatched_by_parent_match": unmatched_by_parent_match,
        "unmatched_parent_patterns": [
            {"pattern": key, "count": value}
            for key, value in unmatched_parent_patterns.most_common()
        ],
        "samples": samples,
        "interpretation_hint": "If dtcode mostly matches but sdcode/bkcode do not, village failures are likely under recognized districts but incompatible subdistrict/block code systems or vintages.",
    }



def _scoped_name_match_unmatched(source_path: Path, sample_limit: int) -> dict[str, Any]:
    from sqlalchemy import text

    rows = _load_nwdp_vlcode_rows(source_path)
    vlcodes = {row["vlcode"] for row in rows if row["vlcode"]}

    try:
        from sqlalchemy import create_engine, text
    except Exception as exc:
        return {"attempted": True, "healthy": False, "error": exc.__class__.__name__, "message": str(exc)}

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        try:
            if str(BACKEND_ROOT) not in sys.path:
                sys.path.insert(0, str(BACKEND_ROOT))
            from app.core.config import settings
            database_url = getattr(settings, "database_url", None) or getattr(settings, "DATABASE_URL", None)
        except Exception as exc:
            return {
                "attempted": True,
                "healthy": False,
                "error": "DATABASE_URL_MISSING",
                "settings_import_error": exc.__class__.__name__,
                "settings_import_message": str(exc),
            }

    engine = create_engine(database_url)
    with engine.connect() as conn:
        village_columns = set(_db_name_columns(conn, "geography_villages"))
        district_columns = set(_db_name_columns(conn, "geography_districts"))
        block_columns = set(_db_name_columns(conn, "geography_blocks"))

        village_name_col = _first_existing(village_columns, ["canonical_name", "census_name", "name", "village_name", "display_name", "name_en", "name_english"])
        village_lgd_col = _first_existing(village_columns, ["lgd_code"])
        village_district_col = _first_existing(village_columns, ["district_id"])
        village_block_col = _first_existing(village_columns, ["block_id", "sub_district_id", "subdistrict_id"])

        district_name_col = _first_existing(district_columns, ["canonical_name", "census_name", "name", "district_name", "display_name", "name_en", "name_english"])
        district_id_col = _first_existing(district_columns, ["id"])
        district_lgd_col = _first_existing(district_columns, ["lgd_code"])

        block_name_col = _first_existing(block_columns, ["canonical_name", "census_name", "name", "block_name", "subdistrict_name", "display_name", "name_en", "name_english"])
        block_id_col = _first_existing(block_columns, ["id"])
        block_lgd_col = _first_existing(block_columns, ["lgd_code"])

        required = {
            "village_name_col": village_name_col,
            "village_lgd_col": village_lgd_col,
            "village_district_col": village_district_col,
            "district_name_col": district_name_col,
            "district_id_col": district_id_col,
        }
        missing_required = [key for key, value in required.items() if not value]
        if missing_required:
            return {
                "attempted": True,
                "healthy": False,
                "error": "REQUIRED_COLUMNS_MISSING",
                "missing_required": missing_required,
                "available_columns": {
                    "geography_villages": sorted(village_columns),
                    "geography_districts": sorted(district_columns),
                    "geography_blocks": sorted(block_columns),
                },
            }

        db_code_rows = conn.execute(
            text(f"select cast({village_lgd_col} as text) as lgd_code from geography_villages where {village_lgd_col} is not null")
        ).mappings().all()
        db_codes = {str(row["lgd_code"]) for row in db_code_rows if row.get("lgd_code")}
        unmatched_rows = [row for row in rows if row["vlcode"] and row["vlcode"] not in db_codes]

        select_parts = [
            f"v.id as village_id",
            f"cast(v.{village_lgd_col} as text) as village_lgd_code",
            f"v.{village_name_col} as village_name",
            f"d.{district_name_col} as district_name",
        ]
        join_parts = [f"join geography_districts d on d.{district_id_col} = v.{village_district_col}"]

        if village_block_col and block_id_col and block_name_col:
            select_parts.append(f"b.{block_name_col} as block_name")
            join_parts.append(f"left join geography_blocks b on b.{block_id_col} = v.{village_block_col}")
        else:
            select_parts.append("null as block_name")

        query = f"""
            select {", ".join(select_parts)}
            from geography_villages v
            {' '.join(join_parts)}
        """
        db_rows = conn.execute(text(query)).mappings().all()

    index_by_district_village: dict[tuple[str, str], list[dict[str, Any]]] = {}
    index_by_district_block_village: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    for row in db_rows:
        item = {key: (None if row[key] is None else str(row[key])) for key in row.keys()}
        district_key = _name_key(item.get("district_name"))
        block_key = _name_key(item.get("block_name"))
        village_key = _name_key(item.get("village_name"))

        if district_key and village_key:
            index_by_district_village.setdefault((district_key, village_key), []).append(item)
        if district_key and block_key and village_key:
            index_by_district_block_village.setdefault((district_key, block_key, village_key), []).append(item)

    exact_scoped_matches = []
    district_village_matches = []
    no_name_matches = []

    for row in unmatched_rows:
        district_key = _name_key(row["district"])
        subdistrict_key = _name_key(row["subdistrict"])
        block_key = _name_key(row["block"])
        village_key = _name_key(row["village"])

        scoped_candidates = []
        for scope_key in [subdistrict_key, block_key]:
            if scope_key:
                scoped_candidates.extend(index_by_district_block_village.get((district_key, scope_key, village_key), []))

        district_candidates = index_by_district_village.get((district_key, village_key), [])

        row_public = {key: value for key, value in row.items() if key != "_raw"}
        if scoped_candidates:
            exact_scoped_matches.append({"nwdp": row_public, "matches": scoped_candidates[:5]})
        elif district_candidates:
            district_village_matches.append({"nwdp": row_public, "matches": district_candidates[:5]})
        else:
            no_name_matches.append(row_public)

    return {
        "attempted": True,
        "healthy": True,
        "unmatched_input_count": len(unmatched_rows),
        "scoped_district_subdistrict_village_match_count": len(exact_scoped_matches),
        "district_village_match_count": len(district_village_matches),
        "no_name_match_count": len(no_name_matches),
        "name_match_rate_of_unmatched": round((len(exact_scoped_matches) + len(district_village_matches)) / len(unmatched_rows), 6) if unmatched_rows else None,
        "columns": {
            "village_name_col": village_name_col,
            "village_lgd_col": village_lgd_col,
            "village_district_col": village_district_col,
            "village_block_col": village_block_col,
            "district_name_col": district_name_col,
            "block_name_col": block_name_col,
        },
        "samples": {
            "scoped_matches": exact_scoped_matches[:sample_limit],
            "district_village_matches": district_village_matches[:sample_limit],
            "no_name_matches": no_name_matches[:sample_limit],
        },
    }



def _db_full_vlcode_coverage(source_path: Path, sample_limit: int) -> dict[str, Any]:
    rows = _load_nwdp_vlcode_rows(source_path)
    vlcodes = [row["vlcode"] for row in rows if row["vlcode"]]
    vlcode_set = set(vlcodes)
    duplicate_vlcodes = sorted([code for code, count in Counter(vlcodes).items() if count > 1])

    try:
        from sqlalchemy import create_engine, text
    except Exception as exc:
        return {
            "attempted": True,
            "healthy": False,
            "error": exc.__class__.__name__,
            "message": str(exc),
            "note": "Full coverage requires SQLAlchemy.",
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
            settings_import.update({"healthy": False, "error": exc.__class__.__name__, "message": str(exc)})

    if not database_url:
        return {"attempted": True, "healthy": False, "error": "DATABASE_URL_MISSING", "settings_import": settings_import}

    engine = create_engine(database_url)
    with engine.connect() as conn:
        db_rows = conn.execute(
            text("""
                select cast(lgd_code as text) as lgd_code
                from geography_villages
                where lgd_code is not null
            """)
        ).mappings().all()

    db_codes = {str(row["lgd_code"]) for row in db_rows if row.get("lgd_code")}
    matched = sorted(vlcode_set & db_codes)
    unmatched = sorted(vlcode_set - db_codes)

    unmatched_rows = []
    unmatched_set = set(unmatched[: max(sample_limit * 5, sample_limit)])
    for row in rows:
        if row["vlcode"] in unmatched_set:
            unmatched_rows.append(row)
        if len(unmatched_rows) >= sample_limit:
            break

    matched_rows = []
    matched_set = set(matched[: max(sample_limit * 5, sample_limit)])
    for row in rows:
        if row["vlcode"] in matched_set:
            matched_rows.append(row)
        if len(matched_rows) >= sample_limit:
            break

    unmatched_classification = _classify_unmatched_rows(rows, set(unmatched), sample_limit)

    return {
        "attempted": True,
        "healthy": True,
        "total_features": len(rows),
        "non_blank_vlcode_features": len(vlcodes),
        "blank_vlcode_features": len(rows) - len(vlcodes),
        "distinct_vlcode_count": len(vlcode_set),
        "duplicate_vlcode_count": len(duplicate_vlcodes),
        "duplicate_vlcode_samples": duplicate_vlcodes[:sample_limit],
        "backend_lgd_code_count": len(db_codes),
        "matched_vlcode_count": len(matched),
        "unmatched_vlcode_count": len(unmatched),
        "match_rate_distinct_vlcode": round(len(matched) / len(vlcode_set), 6) if vlcode_set else None,
        "matched_samples": matched_rows[:sample_limit],
        "unmatched_samples": unmatched_rows[:sample_limit],
        "soi_reference_overlap": _soi_reference_overlap(vlcode_set),
        "unmatched_classification": unmatched_classification,
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
    parser.add_argument("--full-vlcode-coverage", action="store_true", help="Run read-only full Karnataka vlcode coverage against backend LGD codes and local SOI references.")
    parser.add_argument("--unmatched-name-match", action="store_true", help="For unmatched vlcodes, try read-only scoped normalized name matching against backend geography.")
    parser.add_argument("--parent-code-drift", action="store_true", help="Compare NWDP dtcode/sdcode/bkcode parent codes with backend district/block LGD codes.")
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

    full_vlcode_coverage = {"attempted": False}
    if args.full_vlcode_coverage and audit.get("healthy"):
        full_vlcode_coverage = _db_full_vlcode_coverage(geojson_path, args.sample_limit)

    unmatched_name_match = {"attempted": False}
    if args.unmatched_name_match and audit.get("healthy"):
        unmatched_name_match = _scoped_name_match_unmatched(geojson_path, args.sample_limit)

    parent_code_drift = {"attempted": False}
    if args.parent_code_drift and audit.get("healthy"):
        parent_code_drift = _parent_code_drift_audit(geojson_path, args.sample_limit)

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
        "full_vlcode_coverage": full_vlcode_coverage,
        "unmatched_name_match": unmatched_name_match,
        "parent_code_drift": parent_code_drift,
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
