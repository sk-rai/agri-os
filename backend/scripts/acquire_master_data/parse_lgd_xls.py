"""Parse LGD XML-based .xls files and convert to CSV.

The LGD website exports data as XML Spreadsheet (SpreadsheetML) format,
not binary Excel. This script parses them using xml.etree.ElementTree.

Usage:
    cd backend
    source ../venv/bin/activate
    python scripts/acquire_master_data/parse_lgd_xls.py

Output:
    data/raw/lgd/up_districts.csv
    data/raw/lgd/up_blocks.csv
    data/raw/lgd/up_villages.csv
"""

import sys
import csv
import xml.etree.ElementTree as ET
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "lgd"

# XML namespaces used in SpreadsheetML
NS = {
    "ss": "urn:schemas-microsoft-com:office:spreadsheet",
    "o": "urn:schemas-microsoft-com:office:office",
    "x": "urn:schemas-microsoft-com:office:excel",
}


def find_xls_file(pattern):
    """Find the XLS file matching a pattern in RAW_DIR."""
    for f in RAW_DIR.iterdir():
        if f.suffix == ".xls" and pattern in f.name.lower():
            return f
    return None


def parse_spreadsheet_xml(filepath, max_rows=None):
    """Parse SpreadsheetML XML and return list of rows (list of strings).

    For large files, uses iterparse to avoid loading entire DOM.
    """
    print(f"  Parsing: {filepath.name} ({filepath.stat().st_size / 1024 / 1024:.1f} MB)")

    rows = []
    current_row = []
    in_data = False
    row_count = 0

    # Use iterparse for memory efficiency on large files
    for event, elem in ET.iterparse(filepath, events=("start", "end")):
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

        if event == "start" and tag == "Row":
            current_row = []
        elif event == "end" and tag == "Data":
            current_row.append(elem.text or "")
        elif event == "end" and tag == "Row":
            if current_row:
                rows.append(current_row)
                row_count += 1
                if max_rows and row_count >= max_rows:
                    break
                if row_count % 50000 == 0:
                    print(f"    ... {row_count} rows parsed")
            # Clear element to free memory
            elem.clear()
        elif event == "end":
            elem.clear()

    print(f"  Total rows: {row_count}")
    return rows


def save_csv(filepath, rows, fieldnames):
    """Save rows to CSV."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved {len(rows)} rows to {filepath.name}")


def find_header_row(rows):
    """Find the actual header row (skip title rows like 'Local Government Directory')."""
    for i, row in enumerate(rows):
        row_text = " ".join(row).lower()
        # Header row has multiple columns AND contains keywords like 'code' + 'name'
        if len(row) >= 3 and "code" in row_text and "name" in row_text:
            return i
        # Also match 'S.No.' pattern
        if len(row) >= 3 and ("s.no" in row_text or "sr.no" in row_text):
            return i
    # If nothing found, try row with most columns
    max_cols = 0
    max_idx = 1
    for i, row in enumerate(rows[:10]):
        if len(row) > max_cols:
            max_cols = len(row)
            max_idx = i
    return max_idx


def map_columns(header):
    """Map column indices by header text. Handles duplicate column names."""
    col_map = {}
    for i, col in enumerate(header):
        col_lower = col.lower().strip()
        # Only store first occurrence of each key
        if col_lower not in col_map:
            col_map[col_lower] = i
        else:
            # Store duplicates with suffix
            col_map[f"{col_lower}__{i}"] = i
    return col_map


def parse_districts():
    """Parse district XLS file."""
    filepath = find_xls_file("districtofspecificstate")
    if not filepath:
        print("  ERROR: District XLS file not found")
        return []

    rows = parse_spreadsheet_xml(filepath)
    if not rows:
        return []

    # Find header row
    header_idx = find_header_row(rows)
    header = rows[header_idx]
    print(f"  Header (row {header_idx}): {header}")

    # Build column map
    col_map = map_columns(header)
    print(f"  Columns: {col_map}")

    # Find relevant column indices
    code_idx = None
    name_idx = None
    for key, idx in col_map.items():
        if "district code" in key or key == "district code":
            code_idx = idx
        elif "district name" in key and "local" not in key:
            name_idx = idx

    # Fallback: first column with 'code', first with 'name'
    if code_idx is None:
        for key, idx in col_map.items():
            if "code" in key:
                code_idx = idx
                break
    if name_idx is None:
        for key, idx in col_map.items():
            if "name" in key:
                name_idx = idx
                break

    print(f"  Using: code_idx={code_idx}, name_idx={name_idx}")

    districts = []
    for row in rows[header_idx + 1:]:
        if len(row) <= max(code_idx or 0, name_idx or 0):
            continue
        lgd_code = row[code_idx].strip() if code_idx is not None else ""
        name = row[name_idx].strip() if name_idx is not None else ""
        if lgd_code and name and not lgd_code.lower().startswith("district"):
            districts.append({
                "lgd_code": lgd_code,
                "canonical_name": name,
                "census_name": name,
            })

    return districts


def parse_blocks():
    """Parse sub-district (block/tehsil) XLS file."""
    filepath = find_xls_file("subdistrictofspecificstate")
    if not filepath:
        print("  ERROR: Sub-district XLS file not found")
        return []

    rows = parse_spreadsheet_xml(filepath)
    if not rows:
        return []

    header_idx = find_header_row(rows)
    header = rows[header_idx]
    print(f"  Header (row {header_idx}): {header}")
    col_map = map_columns(header)
    print(f"  Columns: {col_map}")

    # Find indices
    block_code_idx = None
    dist_code_idx = None
    name_idx = None
    for key, idx in col_map.items():
        if "subdistrict code" in key or "sub-district code" in key or "sub district code" in key:
            if block_code_idx is None:
                block_code_idx = idx
        elif "district code" in key and "sub" not in key:
            if dist_code_idx is None:
                dist_code_idx = idx
        elif ("subdistrict name" in key or "sub-district name" in key or "sub district name" in key):
            if name_idx is None:
                name_idx = idx

    # If name_idx still None, look for first 'name' column after the code columns
    if name_idx is None:
        for key, idx in col_map.items():
            if "name" in key and idx > (block_code_idx or 0):
                name_idx = idx
                break

    print(f"  Using: block_code_idx={block_code_idx}, dist_code_idx={dist_code_idx}, name_idx={name_idx}")

    blocks = []
    for row in rows[header_idx + 1:]:
        max_idx = max(filter(None, [block_code_idx, dist_code_idx, name_idx]), default=0)
        if len(row) <= max_idx:
            continue
        lgd_code = row[block_code_idx].strip() if block_code_idx is not None else ""
        dist_code = row[dist_code_idx].strip() if dist_code_idx is not None else ""
        name = row[name_idx].strip() if name_idx is not None else ""
        if lgd_code and name and not lgd_code.lower().startswith("sub"):
            blocks.append({
                "lgd_code": lgd_code,
                "district_lgd_code": dist_code,
                "canonical_name": name,
            })

    return blocks


def parse_villages():
    """Parse village XLS file (large — ~100K+ rows)."""
    filepath = find_xls_file("villageofspecificstate")
    if not filepath:
        print("  ERROR: Village XLS file not found")
        return []

    rows = parse_spreadsheet_xml(filepath)
    if not rows:
        return []

    header_idx = find_header_row(rows)
    header = rows[header_idx]
    print(f"  Header (row {header_idx}): {header}")
    col_map = map_columns(header)
    print(f"  Columns: {col_map}")

    # Find indices
    village_code_idx = None
    block_code_idx = None
    dist_code_idx = None
    name_idx = None
    for key, idx in col_map.items():
        if "village code" in key and village_code_idx is None:
            village_code_idx = idx
        elif ("sub-district code" in key or "subdistrict code" in key or "sub district code" in key) and block_code_idx is None:
            block_code_idx = idx
        elif "district code" in key and "sub" not in key and dist_code_idx is None:
            dist_code_idx = idx
        elif "village name" in key and name_idx is None:
            name_idx = idx

    # Fallback for name
    if name_idx is None:
        for key, idx in col_map.items():
            if "name" in key and "district" not in key and "sub" not in key:
                name_idx = idx
                break

    print(f"  Using: village_code={village_code_idx}, block_code={block_code_idx}, dist_code={dist_code_idx}, name={name_idx}")

    villages = []
    for row in rows[header_idx + 1:]:
        max_idx = max(filter(None, [village_code_idx, block_code_idx, dist_code_idx, name_idx]), default=0)
        if len(row) <= max_idx:
            continue
        lgd_code = row[village_code_idx].strip() if village_code_idx is not None else ""
        block_code = row[block_code_idx].strip() if block_code_idx is not None else ""
        dist_code = row[dist_code_idx].strip() if dist_code_idx is not None else ""
        name = row[name_idx].strip() if name_idx is not None else ""
        if lgd_code and name and not lgd_code.lower().startswith("village"):
            villages.append({
                "lgd_code": lgd_code,
                "block_lgd_code": block_code,
                "district_lgd_code": dist_code,
                "canonical_name": name,
                "pin_codes": "",
            })

    return villages


if __name__ == "__main__":
    print("=" * 60)
    print("Parsing LGD XLS files for Uttar Pradesh")
    print("=" * 60)

    # Parse districts first (small file, helps us understand column layout)
    print("\n[1] Parsing districts...")
    districts = parse_districts()
    if districts:
        save_csv(
            RAW_DIR / "up_districts.csv",
            districts,
            ["lgd_code", "canonical_name", "census_name"],
        )

    # Parse blocks/sub-districts
    print("\n[2] Parsing blocks/sub-districts...")
    blocks = parse_blocks()
    if blocks:
        save_csv(
            RAW_DIR / "up_blocks.csv",
            blocks,
            ["lgd_code", "district_lgd_code", "canonical_name"],
        )

    # Parse villages (large file — may take a minute)
    print("\n[3] Parsing villages (this may take a few minutes)...")
    villages = parse_villages()
    if villages:
        save_csv(
            RAW_DIR / "up_villages.csv",
            villages,
            ["lgd_code", "block_lgd_code", "district_lgd_code", "canonical_name", "pin_codes"],
        )

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary:")
    print(f"  Districts: {len(districts)}")
    print(f"  Blocks:    {len(blocks)}")
    print(f"  Villages:  {len(villages)}")
    print(f"\nNext: python scripts/acquire_master_data/load_geography_up.py --reset")
    print(f"{'=' * 60}")
