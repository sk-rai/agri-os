#!/usr/bin/env python3
"""Read-only candidate planner for NWDP Karnataka village-boundary crosswalks."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_ZIP = Path("/tmp/nwdp-karnataka-village-boundary-shp.zip")
DEFAULT_EXTRACT_DIR = Path("/tmp/nwdp-karnataka-boundary-crosswalk-plan")
DEFAULT_JSON_OUTPUT = Path("/tmp/nwdp-karnataka-boundary-crosswalk-candidates.json")
DEFAULT_CSV_OUTPUT = Path("/tmp/nwdp-karnataka-boundary-crosswalk-candidates.csv")

SPECIAL_NAME_PATTERNS = [
    "river",
    "reservoir",
    "lake",
    "canal",
    "tank",
    "pond",
    "beat",
    "forest",
    "plantation",
]


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def clean(value: Any) -> str:
    return str(value or "").strip()


def is_special_feature(vlcode: str, village: str) -> bool:
    name = village.lower()
    return vlcode == "999999" or any(pattern in name for pattern in SPECIAL_NAME_PATTERNS)


def extract_zip(zip_path: Path, extract_dir: Path) -> dict[str, Any]:
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        members = archive.namelist()
        archive.extractall(extract_dir)

    shp_files = sorted(extract_dir.rglob("*.shp"))
    prj_files = sorted(extract_dir.rglob("*.prj"))

    return {
        "members": members,
        "extract_dir": str(extract_dir),
        "selected_shp": str(shp_files[0]) if shp_files else None,
        "selected_prj": str(prj_files[0]) if prj_files else None,
    }

def load_backend_geography() -> dict[str, Any]:
    from sqlalchemy import create_engine, text

    from app.core.config import settings

    database_url = (
        getattr(settings, "database_url", None)
        or getattr(settings, "DATABASE_URL", None)
        or getattr(settings, "sqlalchemy_database_uri", None)
        or getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
        or getattr(settings, "postgres_url", None)
        or getattr(settings, "POSTGRES_URL", None)
    )

    if not database_url:
        database_url = "postgresql+psycopg2://agri_os:agri_os_dev@localhost:5432/agri_os"

    engine = create_engine(str(database_url))

    with engine.connect() as conn:
        districts = conn.execute(
            text("""
                select id, lgd_code, canonical_name, census_name
                from geography_districts
            """)
        ).mappings().all()

        blocks = conn.execute(
            text("""
                select id, lgd_code, canonical_name, district_id
                from geography_blocks
            """)
        ).mappings().all()

        villages = conn.execute(
            text("""
                select id, lgd_code, census_village_code, canonical_name, census_name, district_id, block_id
                from geography_villages
            """)
        ).mappings().all()

    district_by_code = {}
    for row in districts:
        if row["lgd_code"] is not None:
            district_by_code[str(row["lgd_code"]).strip()] = dict(row)

    block_by_code = {}
    for row in blocks:
        if row["lgd_code"] is not None:
            block_by_code[str(row["lgd_code"]).strip()] = dict(row)

    village_by_lgd = {}
    village_by_census = {}
    villages_by_parent_name = {}
    villages_by_district_name = {}

    for row in villages:
        item = dict(row)
        if item.get("lgd_code") is not None:
            village_by_lgd[str(item["lgd_code"]).strip()] = item

        if item.get("census_village_code") is not None:
            census_key = str(item["census_village_code"]).strip()
            if census_key:
                village_by_census.setdefault(census_key, []).append(item)

        names = [item.get("canonical_name"), item.get("census_name")]
        for name in names:
            name_key = norm(name)
            if not name_key:
                continue
            parent_key = (str(item.get("district_id")), str(item.get("block_id")), name_key)
            district_key = (str(item.get("district_id")), name_key)
            villages_by_parent_name.setdefault(parent_key, []).append(item)
            villages_by_district_name.setdefault(district_key, []).append(item)

    return {
        "district_by_code": district_by_code,
        "block_by_code": block_by_code,
        "village_by_lgd": village_by_lgd,
        "village_by_census": village_by_census,
        "villages_by_parent_name": villages_by_parent_name,
        "villages_by_district_name": villages_by_district_name,
        "counts": {
            "districts": len(districts),
            "blocks": len(blocks),
            "villages": len(villages),
            "village_lgd_codes": len(village_by_lgd),
            "village_census_codes": len(village_by_census),
        },
    }

def source_record(shape_record: Any) -> dict[str, str]:
    record = shape_record.record.as_dict()
    return {
        "stcode": clean(record.get("stcode")),
        "dtcode": clean(record.get("dtcode")),
        "sdcode": clean(record.get("sdcode")),
        "bkcode": clean(record.get("bkcode")),
        "vlcode": clean(record.get("vlcode")),
        "state": clean(record.get("state")),
        "district": clean(record.get("district")),
        "subdistrict": clean(record.get("subdistric")),
        "block": clean(record.get("block")),
        "village": clean(record.get("village")),
        "src_agency": clean(record.get("src_agency")),
    }


def classify_record(src: dict[str, str], geography: dict[str, Any]) -> dict[str, Any]:
    dtcode = src["dtcode"]
    sdcode = src["sdcode"]
    bkcode = src["bkcode"]
    vlcode = src["vlcode"]
    village = src["village"]

    district = geography["district_by_code"].get(dtcode)
    sd_block = geography["block_by_code"].get(sdcode)
    bk_block = geography["block_by_code"].get(bkcode)
    direct_village = geography["village_by_lgd"].get(vlcode)

    parent_block = sd_block or bk_block
    parent_district_id = str(district["id"]) if district else None
    parent_block_id = str(parent_block["id"]) if parent_block else None
    name_key = norm(village)

    special = is_special_feature(vlcode, village)

    if special:
        return {
            "bucket": "SPECIAL_REFERENCE_FEATURE",
            "confidence": "NWDP_SPECIAL_REFERENCE_FEATURE",
            "review_status": "MANUAL_REVIEW",
            "proposed_scope": "district_subdistrict_reference_only",
            "backend_village_id": "",
            "backend_village_lgd_code": "",
            "reason": "special non-village name/code pattern",
        }

    if direct_village:
        parent_consistent = True
        if district and str(direct_village.get("district_id")) != str(district["id"]):
            parent_consistent = False
        if parent_block and str(direct_village.get("block_id")) != str(parent_block["id"]):
            parent_consistent = False

        return {
            "bucket": "DIRECT_VLCODE_MATCH" if parent_consistent else "DIRECT_VLCODE_PARENT_MISMATCH",
            "confidence": "NWDP_DIRECT_VLCODE" if parent_consistent else "NWDP_DIRECT_VLCODE_PARENT_MISMATCH",
            "review_status": "AUTO_CANDIDATE" if parent_consistent else "MANUAL_REVIEW",
            "proposed_scope": "village",
            "backend_village_id": str(direct_village.get("id")),
            "backend_village_lgd_code": str(direct_village.get("lgd_code")),
            "reason": "vlcode matched backend lgd_code" if parent_consistent else "vlcode matched but parent ids differ",
        }

    census_matches = geography["village_by_census"].get(vlcode) or []
    if census_matches:
        exact_parent_census = [
            item for item in census_matches
            if (not parent_district_id or str(item.get("district_id")) == parent_district_id)
            and (not parent_block_id or str(item.get("block_id")) == parent_block_id)
        ]
        chosen = exact_parent_census[0] if exact_parent_census else census_matches[0]
        return {
            "bucket": "CENSUS_VILLAGE_CODE_MATCH" if exact_parent_census else "CENSUS_CODE_AMBIGUOUS",
            "confidence": "NWDP_CENSUS_VILLAGE_CODE",
            "review_status": "MANUAL_REVIEW",
            "proposed_scope": "village_review",
            "backend_village_id": str(chosen.get("id")),
            "backend_village_lgd_code": str(chosen.get("lgd_code")),
            "reason": "source vlcode matched backend census_village_code",
        }

    scoped_matches = []
    if parent_district_id and parent_block_id and name_key:
        scoped_matches = geography["villages_by_parent_name"].get((parent_district_id, parent_block_id, name_key), [])

    if scoped_matches:
        chosen = scoped_matches[0]
        return {
            "bucket": "PARENT_SCOPED_NAME_MATCH" if len(scoped_matches) == 1 else "PARENT_SCOPED_NAME_AMBIGUOUS",
            "confidence": "NWDP_PARENT_SCOPED_NAME",
            "review_status": "MANUAL_REVIEW",
            "proposed_scope": "village_review",
            "backend_village_id": str(chosen.get("id")),
            "backend_village_lgd_code": str(chosen.get("lgd_code")),
            "reason": "parent-scoped normalized village name matched backend",
        }

    district_matches = []
    if parent_district_id and name_key:
        district_matches = geography["villages_by_district_name"].get((parent_district_id, name_key), [])

    if district_matches:
        chosen = district_matches[0]
        return {
            "bucket": "DISTRICT_SCOPED_AMBIGUOUS",
            "confidence": "NWDP_DISTRICT_ONLY_AMBIGUOUS",
            "review_status": "MANUAL_REVIEW",
            "proposed_scope": "district_review",
            "backend_village_id": str(chosen.get("id")),
            "backend_village_lgd_code": str(chosen.get("lgd_code")),
            "reason": "district-scoped name matched but parent block/subdistrict did not",
        }

    if district and parent_block:
        return {
            "bucket": "PARENT_MATCH_VILLAGE_UNRESOLVED",
            "confidence": "NWDP_PARENT_ONLY_VILLAGE_UNRESOLVED",
            "review_status": "MANUAL_REVIEW",
            "proposed_scope": "district_subdistrict",
            "backend_village_id": "",
            "backend_village_lgd_code": "",
            "reason": "parent codes match but village code/name unresolved",
        }

    if district:
        return {
            "bucket": "DISTRICT_ONLY_UNRESOLVED",
            "confidence": "NWDP_DISTRICT_ONLY_AMBIGUOUS",
            "review_status": "MANUAL_REVIEW",
            "proposed_scope": "district",
            "backend_village_id": "",
            "backend_village_lgd_code": "",
            "reason": "district matched but lower geography unresolved",
        }

    return {
        "bucket": "BLOCKED_SOURCE_CAVEAT",
        "confidence": "NWDP_BLOCKED_SOURCE_CAVEAT",
        "review_status": "BLOCKED",
        "proposed_scope": "",
        "backend_village_id": "",
        "backend_village_lgd_code": "",
        "reason": "source parent geography could not be matched",
    }

def run_plan(zip_path: Path, extract_dir: Path, csv_output: Path, sample_limit: int) -> dict[str, Any]:
    try:
        import shapefile
    except Exception as exc:
        return {"healthy": False, "error": "PYSHAPEFILE_NOT_AVAILABLE", "message": str(exc)}

    if not zip_path.exists():
        return {"healthy": False, "error": "SHP_ZIP_NOT_FOUND", "path": str(zip_path)}

    extracted = extract_zip(zip_path, extract_dir)
    if not extracted.get("selected_shp"):
        return {"healthy": False, "error": "SHP_NOT_FOUND", "extracted": extracted}

    geography = load_backend_geography()
    reader = shapefile.Reader(str(extracted["selected_shp"]))

    rows = []
    bucket_counts = Counter()
    review_counts = Counter()
    confidence_counts = Counter()
    proposed_scope_counts = Counter()
    district_bucket_counts = Counter()
    samples_by_bucket: dict[str, list[dict[str, Any]]] = {}

    for index, shape_record in enumerate(reader.iterShapeRecords()):
        src = source_record(shape_record)
        classification = classify_record(src, geography)

        row = {
            "index": index,
            **src,
            **classification,
        }
        rows.append(row)

        bucket = classification["bucket"]
        bucket_counts[bucket] += 1
        review_counts[classification["review_status"]] += 1
        confidence_counts[classification["confidence"]] += 1
        proposed_scope_counts[classification["proposed_scope"]] += 1
        district_bucket_counts[f"{src['district']}|{bucket}"] += 1

        samples = samples_by_bucket.setdefault(bucket, [])
        if len(samples) < sample_limit:
            samples.append(row)

    csv_output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "index",
        "stcode",
        "dtcode",
        "sdcode",
        "bkcode",
        "vlcode",
        "district",
        "subdistrict",
        "block",
        "village",
        "src_agency",
        "bucket",
        "confidence",
        "review_status",
        "proposed_scope",
        "backend_village_id",
        "backend_village_lgd_code",
        "reason",
    ]

    with csv_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    district_bucket_summary = []
    for key, count in district_bucket_counts.most_common(80):
        district, bucket = key.split("|", 1)
        district_bucket_summary.append({
            "district": district,
            "bucket": bucket,
            "count": count,
        })

    return {
        "healthy": True,
        "source_record_count": len(reader),
        "planned_candidate_count": len(rows),
        "backend_geography_counts": geography["counts"],
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "review_status_counts": dict(sorted(review_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "proposed_scope_counts": dict(sorted(proposed_scope_counts.items())),
        "district_bucket_summary_top80": district_bucket_summary,
        "samples_by_bucket": samples_by_bucket,
        "csv_output": str(csv_output),
        "extracted": extracted,
        "readiness": {
            "safe_read_only": True,
            "db_writes_attempted": False,
            "ready_for_manual_review_import_design": True,
            "ready_for_direct_db_ingestion": False,
            "ready_for_runtime_spatial_matching": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only NWDP Karnataka boundary crosswalk candidate planner.")
    parser.add_argument("--zip-path", default=str(DEFAULT_ZIP), help="Path to Karnataka SHP ZIP from CRS audit.")
    parser.add_argument("--extract-dir", default=str(DEFAULT_EXTRACT_DIR), help="Temporary extraction directory.")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--csv-output", default=str(DEFAULT_CSV_OUTPUT))
    parser.add_argument("--sample-limit", type=int, default=12)
    args = parser.parse_args()

    plan = run_plan(
        Path(args.zip_path),
        Path(args.extract_dir),
        Path(args.csv_output),
        args.sample_limit,
    )

    result = {
        "schema_version": "nwdp_karnataka_boundary_crosswalk_candidate_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "portal": "National Water Data Portal",
            "dataset": "Village Boundary",
            "producer_agency": "Geological Survey of India",
            "state_or_ut": "Karnataka",
            "format": "SHP",
        },
        "claim_boundary": "Candidate planner is read-only. It creates review artifacts only and does not ingest geometry, promote crosswalks, or authorize runtime spatial matching.",
        "plan": plan,
    }

    output = Path(args.json_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
