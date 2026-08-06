#!/usr/bin/env python3
"""Review BharatAtlas LGD district boundary source status.

Read-only. This script inspects the staged BharatAtlas district GeoJSON and
emits a source/provenance decision for backend overlay use.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BHARATLAS_DISTRICTS = ROOT / "data/staged/boundaries/bharatlas_lgd/LGD_Districts.geojson"

SOURCE_REVIEW = {
    "source_name": "BharatAtlas LGD Districts",
    "source_url": "https://bharatlas.com/view/lgd_districts",
    "source_status": "UNOFFICIAL_REPUBLICATION",
    "source_role": "PROVISIONAL_BOUNDARY_GEOMETRY_FOR_REVIEW",
    "reported_upstream_sources": [
        "Local Government Directory (LGD)",
        "Survey of India (SOI)",
        "ISRO / NRSC Bhuvan",
        "NIC / Bharat Maps",
    ],
    "allowed_uses": [
        "dry-run overlay candidate generation",
        "manual-review QA",
        "pipeline development",
    ],
    "disallowed_claims": [
        "GOVT_SOURCE",
        "OFFICIAL_BOUNDARY",
        "AUTHORITATIVE_BOUNDARY",
        "production-trusted mapping without review",
    ],
}

REQUIRED_FIELDS = ["state_lgd", "dist_lgd", "stcode11", "dtcode11", "stname", "dtname"]


def load_geojson(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - CLI review reports source issues
        return None, [f"unable_to_read_geojson: {exc}"]

    errors = []
    if data.get("type") != "FeatureCollection":
        errors.append(f"root_type_is_not_feature_collection: {data.get('type')}")
    if not isinstance(data.get("features"), list):
        errors.append("features_is_not_list")
    return data, errors


def main() -> int:
    errors = []
    data = None
    if not BHARATLAS_DISTRICTS.exists():
        errors.append("missing_bharatlas_lgd_districts_geojson")
    else:
        data, load_errors = load_geojson(BHARATLAS_DISTRICTS)
        errors.extend(load_errors)

    features = data.get("features", []) if data else []
    property_keys = Counter()
    geometry_types = Counter()
    non_empty_required_counts = Counter()
    state_codes = set()
    district_codes = set()

    for feature in features:
        properties = feature.get("properties") or {}
        property_keys.update(properties.keys())
        geometry_types[(feature.get("geometry") or {}).get("type")] += 1
        for field in REQUIRED_FIELDS:
            if properties.get(field) not in (None, ""):
                non_empty_required_counts[field] += 1
        if properties.get("state_lgd"):
            state_codes.add(str(properties["state_lgd"]))
        if properties.get("dist_lgd"):
            district_codes.add(str(properties["dist_lgd"]))

    missing_required_fields = [
        field
        for field in REQUIRED_FIELDS
        if field not in property_keys or non_empty_required_counts[field] == 0
    ]
    readiness = {
        "file_exists": BHARATLAS_DISTRICTS.exists(),
        "readable_geojson": data is not None and not errors,
        "feature_count_nonzero": len(features) > 0,
        "expected_feature_count_observed": len(features) == 785,
        "required_lgd_fields_present": not missing_required_fields,
        "polygon_geometry_present": set(geometry_types).issubset({"Polygon", "MultiPolygon"}),
        "acceptable_for_dry_run_candidates": (
            data is not None
            and not errors
            and len(features) > 0
            and not missing_required_fields
            and set(geometry_types).issubset({"Polygon", "MultiPolygon"})
        ),
        "acceptable_as_authoritative_source": False,
        "ready_for_db_import_without_review": False,
    }
    result = {
        "schema_version": "bharatlas_boundary_source_review.v1",
        "mode": "READ_ONLY_SOURCE_REVIEW",
        "external_calls_made": False,
        "db_writes_made": False,
        "boundary_file": str(BHARATLAS_DISTRICTS),
        "source_review": SOURCE_REVIEW,
        "file_summary": {
            "exists": BHARATLAS_DISTRICTS.exists(),
            "size_bytes": BHARATLAS_DISTRICTS.stat().st_size if BHARATLAS_DISTRICTS.exists() else 0,
            "feature_count": len(features),
            "state_code_count": len(state_codes),
            "district_code_count": len(district_codes),
            "geometry_types": dict(sorted(geometry_types.items())),
            "sample_property_keys": sorted(property_keys)[:60],
            "required_fields": REQUIRED_FIELDS,
            "required_field_non_empty_counts": dict(sorted(non_empty_required_counts.items())),
            "missing_required_fields": missing_required_fields,
        },
        "errors": errors,
        "decision": {
            "use_for_current_overlay_candidates": readiness["acceptable_for_dry_run_candidates"],
            "import_confidence_if_used_later": "POLYGON_DERIVED_DISTRICT_OVERLAY_REVIEW",
            "review_status_if_used_later": "MANUAL_REVIEW",
            "must_record_unofficial_republication": True,
            "must_not_mark_govt_source": True,
        },
        "readiness": readiness,
        "next_actions": [
            "Record BharatAtlas as provisional boundary geometry if candidates are later imported.",
            "Keep candidate rows MANUAL_REVIEW.",
            "Review low-overlap districts before import.",
            "Prefer direct Survey of India/Bharat Maps source if authoritative production use is required.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if readiness["acceptable_for_dry_run_candidates"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
