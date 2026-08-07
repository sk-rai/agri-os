#!/usr/bin/env python3
"""Validate staged Survey of India ABDB boundary files.

Read-only. Inspects SOI metadata and shapefile attributes/record counts. Does
not write database rows and does not extract committed geospatial data.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
SOI_DIR = ROOT / "data/staged/boundaries/survey_of_india"
ABDB_DIR = SOI_DIR / "state_district_subdistrict_pan_india"
METADATA_DIR = SOI_DIR / "metadata_abdb"

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soi-dir", type=Path, default=SOI_DIR)
    parser.add_argument("--abdb-dir", type=Path, default=ABDB_DIR)
    parser.add_argument("--metadata-dir", type=Path, default=METADATA_DIR)
    parser.add_argument("--sample-limit", type=int, default=5)
    return parser.parse_args()


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def read_xlsx_rows(path: Path, limit: int = 80) -> list[list[str | None]]:
    def col_letters(cell_ref: str) -> str:
        return re.sub(r"\d+", "", cell_ref or "")

    def col_index(letters: str) -> int:
        total = 0
        for ch in letters:
            if ch.isalpha():
                total = total * 26 + (ord(ch.upper()) - ord("A") + 1)
        return total - 1

    def shared_strings(z: ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in z.namelist():
            return []
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        values = []
        for si in root.findall("main:si", NS):
            texts = [t.text or "" for t in si.findall(".//main:t", NS)]
            values.append("".join(texts))
        return values

    with ZipFile(path) as z:
        shared = shared_strings(z)
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in root.findall(".//main:sheetData/main:row", NS):
            values: list[str | None] = []
            for cell in row.findall("main:c", NS):
                idx = col_index(col_letters(cell.attrib.get("r", "")))
                while len(values) <= idx:
                    values.append(None)
                value_node = cell.find("main:v", NS)
                value = value_node.text if value_node is not None else None
                if cell.attrib.get("t") == "s" and value is not None:
                    value = shared[int(value)]
                values[idx] = value
            rows.append(values)
            if len(rows) >= limit:
                break
        return rows


def metadata_value(rows: list[list[str | None]], path_suffix: str) -> str | None:
    for row in rows:
        if len(row) >= 2 and row[0] and path_suffix in row[0]:
            return row[1]
    return None


def inspect_shapefile(path: Path, sample_limit: int) -> dict[str, Any]:
    try:
        import shapefile
    except Exception as exc:  # noqa: BLE001
        return {
            "path": str(path),
            "readable": False,
            "error": f"pyshp missing or failed: {exc}",
        }

    reader = shapefile.Reader(str(path))
    fields = [
        {"name": f[0], "type": f[1], "size": f[2], "decimal": f[3]}
        for f in reader.fields
        if f[0] != "DeletionFlag"
    ]
    names = [f["name"] for f in fields]
    samples = [dict(zip(names, rec)) for rec in reader.records()[:sample_limit]]
    lgd_fields = [name for name in names if "LGD" in name.upper()]
    records = list(reader.iterRecords())
    invalid_lgd_counts = {}
    for field in lgd_fields:
        invalid_lgd_counts[field] = sum(
            1
            for rec in records
            if not str(rec[field] or "").strip()
            or str(rec[field] or "").strip().upper() in {"NOT AVAILABLE", "NA", "N/A", "NULL"}
        )

    return {
        "path": str(path),
        "readable": True,
        "shape_type": reader.shapeTypeName,
        "record_count": len(reader),
        "bbox": list(reader.bbox),
        "fields": fields,
        "lgd_fields": lgd_fields,
        "invalid_lgd_counts": invalid_lgd_counts,
        "sample_records": samples,
    }


def sidecars(path: Path) -> dict[str, Any]:
    stem = path.with_suffix("")
    prj = stem.with_suffix(".prj")
    return {
        "shp": path.exists(),
        "dbf": stem.with_suffix(".dbf").exists(),
        "shx": stem.with_suffix(".shx").exists(),
        "prj": prj.exists(),
        "cpg": stem.with_suffix(".cpg").exists(),
        "qmd": stem.with_suffix(".qmd").exists(),
        "xml": stem.with_suffix(".shp.xml").exists(),
        "size_mb": round(path.stat().st_size / 1024 / 1024, 2),
        "prj_text": prj.read_text(errors="ignore")[:500] if prj.exists() else None,
    }


def main() -> int:
    args = parse_args()

    metadata = {}
    for path in sorted(args.metadata_dir.glob("*.xlsx")):
        rows = read_xlsx_rows(path)
        metadata[path.name] = {
            "dataset_file_name": metadata_value(rows, "(Dataset file name"),
            "short_description": metadata_value(rows, "(Short dataset description"),
            "metadata_identifier": metadata_value(rows, "MD_Metadata . metadataIdentifier . MD_Identifier . code"),
            "metadata_description": metadata_value(rows, "MD_Metadata . metadataIdentifier . MD_Identifier . description"),
            "publication_date": metadata_value(rows, "MD_Metadata . dateInfo . CI_Date . date"),
            "owner": metadata_value(rows, "MD_Metadata . contact . CI_Responsibility . party . CI_Organisation . name"),
            "credit": metadata_value(rows, "MD_Metadata . identificationInfo . MD_DataIdentification . credit"),
            "scale_denominator": metadata_value(rows, "MD_Metadata . identificationInfo . MD_DataIdentification . spatialResolution"),
            "level_of_detail": metadata_value(rows, "MD_Metadata . identificationInfo . MD_DataIdentification . levelOfDetail"),
        }

    shapefiles = {}
    for shp in sorted(args.abdb_dir.rglob("*.shp")):
        inspected = inspect_shapefile(shp, args.sample_limit)
        inspected["sidecars"] = sidecars(shp)
        shapefiles[str(shp.relative_to(args.soi_dir))] = inspected

    district_layers = [
        item for item in shapefiles.values()
        if "District Boundary.shp" in item["path"] and "Sub_district" not in item["path"]
    ]
    district = district_layers[0] if district_layers else {}

    district_fields = {field["name"] for field in district.get("fields", [])} if district else set()
    required_district_fields = {"STATE_UT", "STATE_LGD", "DISTRICT", "DIST_LGD"}
    district_invalid_lgd = district.get("invalid_lgd_counts", {}) if district else {}

    readiness = {
        "metadata_present": bool(metadata),
        "state_district_subdistrict_shapefiles_present": len(shapefiles) >= 3,
        "district_layer_present": bool(district),
        "district_layer_has_lgd_fields": required_district_fields.issubset(district_fields),
        "district_layer_has_some_invalid_lgd": any(count > 0 for count in district_invalid_lgd.values()),
        "acceptable_as_official_geometry_source_for_review": bool(district)
        and required_district_fields.issubset(district_fields),
        "safe_for_automatic_db_import": False,
    }

    result = {
        "schema_version": "survey_of_india_boundary_source_validation.v1",
        "mode": "READ_ONLY_SOURCE_VALIDATION",
        "external_calls_made": False,
        "db_writes_made": False,
        "soi_dir": str(args.soi_dir),
        "metadata": metadata,
        "shapefiles": shapefiles,
        "readiness": readiness,
        "recommendation": [
            "Treat SOI ABDB as preferred official boundary geometry source for review.",
            "Keep backend LGD master canonical for code/name/state truth.",
            "Exclude NOT AVAILABLE/blank/disputed LGD rows from automatic mapping.",
            "Compare SOI district geometry against BharatAtlas before replacing geometry source.",
            "Do not change land-intelligence behavior until reviewed mappings are promoted.",
        ],
    }

    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if readiness["acceptable_as_official_geometry_source_for_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
