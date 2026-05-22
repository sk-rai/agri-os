"""Load UP geography data from LGD CSV/Excel files into the database.

Reads files downloaded from https://lgdirectory.gov.in and inserts into
geography_states, geography_districts, geography_blocks, geography_villages.

Supports multiple LGD export formats — auto-detects column names.
Idempotent: uses upsert-by-lgd_code (skips existing records).

Usage:
    cd backend
    source ../venv/bin/activate
    python scripts/acquire_master_data/load_geography_up.py [--reset]

Options:
    --reset  Clear existing UP geography data before loading
"""

import sys
import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.master_data.models import (
    GeographyState,
    GeographyDistrict,
    GeographyBlock,
    GeographyVillage,
)

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "lgd"


# --- Column name mapping ---
# LGD exports use various column names. We map them to our internal names.
# Add new mappings here if LGD changes their export format.

DISTRICT_CODE_COLS = [
    "lgd_code", "district code", "districtcode", "dist_code",
    "district_code", "district lgd code", "dt_code",
]
DISTRICT_NAME_COLS = [
    "canonical_name", "district name(in english)", "district name (in english)",
    "districtname", "district_name", "district name", "dt_name",
    "district name(english)", "district name (english)",
]
BLOCK_CODE_COLS = [
    "lgd_code", "block code", "blockcode", "block_code",
    "sub district code", "subdistrictcode", "sub_district_code",
    "block lgd code", "subdistrict code",
]
BLOCK_NAME_COLS = [
    "canonical_name", "block name(in english)", "block name (in english)",
    "blockname", "block_name", "block name",
    "sub district name(in english)", "sub district name (in english)",
    "subdistrictname", "sub_district_name", "subdistrict name",
]
BLOCK_DISTRICT_CODE_COLS = [
    "district_lgd_code", "district code", "districtcode", "dist_code",
    "district_code",
]
VILLAGE_CODE_COLS = [
    "lgd_code", "village code", "villagecode", "village_code",
    "village lgd code",
]
VILLAGE_NAME_COLS = [
    "canonical_name", "village name(in english)", "village name (in english)",
    "villagename", "village_name", "village name",
    "village name(english)", "village name (english)",
]
VILLAGE_LOCAL_NAME_COLS = [
    "village name(in local)", "village name (in local)",
    "village name(local)", "local_name",
]
VILLAGE_BLOCK_CODE_COLS = [
    "block_lgd_code", "block code", "blockcode", "block_code",
    "sub district code", "subdistrictcode", "subdistrict code",
]
VILLAGE_DISTRICT_CODE_COLS = [
    "district_lgd_code", "district code", "districtcode", "dist_code",
    "district_code",
]
VILLAGE_PIN_COLS = [
    "pin_codes", "pincode", "pin code", "pin", "pin_code",
]


def find_column(headers, candidates):
    """Find the first matching column name (case-insensitive)."""
    headers_lower = {h.lower().strip(): h for h in headers}
    for candidate in candidates:
        if candidate.lower() in headers_lower:
            return headers_lower[candidate.lower()]
    return None


def find_lgd_file(prefix):
    """Find a CSV or Excel file matching the prefix in RAW_DIR."""
    for ext in ["csv", "CSV", "xlsx", "XLSX", "xls"]:
        matches = list(RAW_DIR.glob(f"*{prefix}*.{ext}"))
        if matches:
            return matches[0]
    # Also try exact name
    for ext in ["csv", "xlsx"]:
        path = RAW_DIR / f"up_{prefix}.{ext}"
        if path.exists():
            return path
    return None


def read_csv_or_excel(filepath):
    """Read a CSV or Excel file and return list of dicts."""
    ext = filepath.suffix.lower()
    if ext == ".csv":
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return list(reader), reader.fieldnames
    elif ext in (".xlsx", ".xls"):
        try:
            import openpyxl
        except ImportError:
            print("  ERROR: openpyxl needed for Excel files.")
            print("  Run: pip install openpyxl")
            return [], []
        wb = openpyxl.load_workbook(filepath, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return [], []
        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[0])]
        data = []
        for row in rows[1:]:
            data.append(dict(zip(headers, [str(v).strip() if v else "" for v in row])))
        return data, headers
    else:
        print(f"  ERROR: Unsupported file format: {ext}")
        return [], []


def now():
    return datetime.now(timezone.utc)


def reset_up_data(db: Session):
    """Clear all UP geography data for fresh reload."""
    state = db.query(GeographyState).filter_by(lgd_code="9").first()
    if state:
        # Delete in reverse order (villages → blocks → districts → state)
        db.query(GeographyVillage).filter(
            GeographyVillage.district_id.in_(
                db.query(GeographyDistrict.id).filter_by(state_id=state.id)
            )
        ).delete(synchronize_session=False)
        db.query(GeographyBlock).filter(
            GeographyBlock.district_id.in_(
                db.query(GeographyDistrict.id).filter_by(state_id=state.id)
            )
        ).delete(synchronize_session=False)
        db.query(GeographyDistrict).filter_by(state_id=state.id).delete()
        db.query(GeographyState).filter_by(id=state.id).delete()
        db.commit()
        print("  Cleared existing UP data")


def load_state(db: Session):
    """Create UP state record if not exists."""
    existing = db.query(GeographyState).filter_by(lgd_code="9").first()
    if existing:
        print(f"  State already exists: {existing.canonical_name}")
        return existing

    state = GeographyState(
        id=uuid.uuid4(),
        lgd_code="9",
        canonical_name="Uttar Pradesh",
        census_name="UTTAR PRADESH",
        aliases=[
            {"lang": "hi", "name": "उत्तर प्रदेश"},
            {"lang": "en", "name": "UP"},
        ],
        created_at=now(),
        updated_at=now(),
    )
    db.add(state)
    db.flush()
    print(f"  Created state: {state.canonical_name}")
    return state


def load_districts(db: Session, state_id):
    """Load districts from LGD file (auto-detect format)."""
    filepath = find_lgd_file("district")
    if not filepath:
        print("  ERROR: No district file found in data/raw/lgd/")
        print("  Expected: up_districts.csv or any file with 'district' in name")
        return {}

    print(f"  Reading: {filepath.name}")
    rows, headers = read_csv_or_excel(filepath)
    if not rows:
        print("  ERROR: File is empty")
        return {}

    # Auto-detect columns
    code_col = find_column(headers, DISTRICT_CODE_COLS)
    name_col = find_column(headers, DISTRICT_NAME_COLS)

    if not code_col or not name_col:
        print(f"  ERROR: Could not detect columns. Headers found: {headers}")
        print(f"  Need a code column (tried: {DISTRICT_CODE_COLS[:3]})")
        print(f"  Need a name column (tried: {DISTRICT_NAME_COLS[:3]})")
        return {}

    print(f"  Columns: code={code_col}, name={name_col}")

    district_map = {}
    created = 0
    skipped = 0

    for row in rows:
        lgd_code = str(row.get(code_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        if not lgd_code or not name:
            continue

        existing = db.query(GeographyDistrict).filter_by(lgd_code=lgd_code).first()
        if existing:
            district_map[lgd_code] = existing.id
            skipped += 1
            continue

        district = GeographyDistrict(
            id=uuid.uuid4(),
            lgd_code=lgd_code,
            state_id=state_id,
            canonical_name=name,
            census_name=name,
            aliases=[],
            created_at=now(),
            updated_at=now(),
        )
        db.add(district)
        db.flush()
        district_map[lgd_code] = district.id
        created += 1

    db.commit()
    print(f"  Districts: {created} created, {skipped} skipped")
    return district_map


def load_blocks(db: Session, district_map):
    """Load blocks from LGD file (auto-detect format)."""
    filepath = find_lgd_file("block")
    if not filepath:
        # Also try "sub_district" or "subdistrict"
        filepath = find_lgd_file("sub")
    if not filepath:
        print("  No block/sub-district file found. Skipping.")
        return {}

    print(f"  Reading: {filepath.name}")
    rows, headers = read_csv_or_excel(filepath)
    if not rows:
        print("  File is empty. Skipping blocks.")
        return {}

    # Auto-detect columns
    code_col = find_column(headers, BLOCK_CODE_COLS)
    name_col = find_column(headers, BLOCK_NAME_COLS)
    dist_code_col = find_column(headers, BLOCK_DISTRICT_CODE_COLS)

    if not code_col or not name_col:
        print(f"  ERROR: Could not detect columns. Headers: {headers}")
        return {}

    print(f"  Columns: code={code_col}, name={name_col}, district={dist_code_col}")

    block_map = {}
    created = 0
    skipped = 0
    warnings = 0

    for row in rows:
        lgd_code = str(row.get(code_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        if not lgd_code or not name:
            continue

        existing = db.query(GeographyBlock).filter_by(lgd_code=lgd_code).first()
        if existing:
            block_map[lgd_code] = existing.id
            skipped += 1
            continue

        # Find parent district
        district_id = None
        if dist_code_col:
            dist_code = str(row.get(dist_code_col, "")).strip()
            district_id = district_map.get(dist_code)
            if not district_id:
                district = db.query(GeographyDistrict).filter_by(lgd_code=dist_code).first()
                if district:
                    district_id = district.id

        if not district_id:
            warnings += 1
            continue

        block = GeographyBlock(
            id=uuid.uuid4(),
            lgd_code=lgd_code,
            district_id=district_id,
            canonical_name=name,
            aliases=[],
            created_at=now(),
            updated_at=now(),
        )
        db.add(block)
        db.flush()
        block_map[lgd_code] = block.id
        created += 1

        if created % 100 == 0:
            db.commit()

    db.commit()
    print(f"  Blocks: {created} created, {skipped} skipped, {warnings} warnings")
    return block_map


def load_villages(db: Session, block_map, district_map):
    """Load villages from LGD file (auto-detect format)."""
    filepath = find_lgd_file("village")
    if not filepath:
        print("  No village file found. Skipping.")
        return

    print(f"  Reading: {filepath.name}")
    rows, headers = read_csv_or_excel(filepath)
    if not rows:
        print("  File is empty. Skipping villages.")
        return

    # Auto-detect columns
    code_col = find_column(headers, VILLAGE_CODE_COLS)
    name_col = find_column(headers, VILLAGE_NAME_COLS)
    block_code_col = find_column(headers, VILLAGE_BLOCK_CODE_COLS)
    dist_code_col = find_column(headers, VILLAGE_DISTRICT_CODE_COLS)
    pin_col = find_column(headers, VILLAGE_PIN_COLS)
    local_name_col = find_column(headers, VILLAGE_LOCAL_NAME_COLS)

    if not code_col or not name_col:
        print(f"  ERROR: Could not detect columns. Headers: {headers}")
        return

    print(f"  Columns: code={code_col}, name={name_col}, block={block_code_col}, pin={pin_col}")
    print(f"  Total rows to process: {len(rows)}")

    created = 0
    skipped = 0
    warnings = 0

    for row in rows:
        lgd_code = str(row.get(code_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        if not lgd_code or not name:
            continue

        existing = db.query(GeographyVillage).filter_by(lgd_code=lgd_code).first()
        if existing:
            skipped += 1
            continue

        # Find parent block
        block_id = None
        if block_code_col:
            block_code = str(row.get(block_code_col, "")).strip()
            block_id = block_map.get(block_code)
            if not block_id:
                block = db.query(GeographyBlock).filter_by(lgd_code=block_code).first()
                if block:
                    block_id = block.id

        # Find parent district
        district_id = None
        if dist_code_col:
            dist_code = str(row.get(dist_code_col, "")).strip()
            district_id = district_map.get(dist_code)
            if not district_id:
                district = db.query(GeographyDistrict).filter_by(lgd_code=dist_code).first()
                if district:
                    district_id = district.id

        if not block_id or not district_id:
            warnings += 1
            continue

        # Parse pin codes
        pin_codes = []
        if pin_col and row.get(pin_col):
            raw_pin = str(row[pin_col]).strip()
            if raw_pin and raw_pin != "0" and raw_pin.lower() != "none":
                pin_codes = [p.strip() for p in raw_pin.split(",") if p.strip() and p.strip() != "0"]

        # Parse local name as alias
        aliases = []
        if local_name_col and row.get(local_name_col):
            local_name = str(row[local_name_col]).strip()
            if local_name and local_name != name:
                aliases.append({"lang": "local", "name": local_name})

        village = GeographyVillage(
            id=uuid.uuid4(),
            lgd_code=lgd_code,
            block_id=block_id,
            district_id=district_id,
            canonical_name=name,
            pin_codes=pin_codes if pin_codes else None,
            aliases=aliases if aliases else [],
            created_at=now(),
            updated_at=now(),
        )
        db.add(village)
        created += 1

        # Batch commit for performance
        if created % 1000 == 0:
            db.commit()
            print(f"    ... {created} villages loaded")

    db.commit()
    print(f"  Villages: {created} created, {skipped} skipped, {warnings} warnings")


if __name__ == "__main__":
    print("=" * 60)
    print("Loading UP Geography Data into Database")
    print("=" * 60)

    reset = "--reset" in sys.argv
    detect_only = "--detect" in sys.argv

    # Show what files are available
    print(f"\n  Looking in: {RAW_DIR}")
    found_files = list(RAW_DIR.glob("*"))
    if found_files:
        for f in sorted(found_files):
            size_kb = f.stat().st_size / 1024
            print(f"    {f.name} ({size_kb:.1f} KB)")
    else:
        print("  No files found! Download from lgdirectory.gov.in first.")
        sys.exit(1)

    # Detect mode: just show what columns were found
    if detect_only:
        print("\n[DETECT MODE] Checking file formats...")
        for prefix in ["district", "block", "sub", "village"]:
            filepath = find_lgd_file(prefix)
            if filepath:
                rows, headers = read_csv_or_excel(filepath)
                print(f"\n  {filepath.name}:")
                print(f"    Rows: {len(rows)}")
                print(f"    Headers: {headers}")
                if rows:
                    print(f"    Sample row: {rows[0]}")
        print("\n  If columns look correct, run without --detect to load.")
        sys.exit(0)

    db = SessionLocal()
    try:
        if reset:
            print("\n[RESET] Clearing existing UP data...")
            reset_up_data(db)

        print("\n[1] Loading state...")
        state = load_state(db)

        print("\n[2] Loading districts...")
        district_map = load_districts(db, state.id)

        print("\n[3] Loading blocks...")
        block_map = load_blocks(db, district_map)

        print("\n[4] Loading villages...")
        load_villages(db, block_map, district_map)

        # Print summary
        print(f"\n{'=' * 60}")
        print("Summary:")
        print(f"  States:    {db.query(GeographyState).count()}")
        print(f"  Districts: {db.query(GeographyDistrict).count()}")
        print(f"  Blocks:    {db.query(GeographyBlock).count()}")
        print(f"  Villages:  {db.query(GeographyVillage).count()}")
        print(f"{'=' * 60}")
        print("Done!")
    finally:
        db.close()
