"""Load UP geography data from CSV files into the database.

Reads CSV files produced by fetch_lgd_up.py and inserts into
geography_states, geography_districts, geography_blocks, geography_villages.

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
    """Load districts from CSV."""
    csv_path = RAW_DIR / "up_districts.csv"
    if not csv_path.exists():
        print(f"  ERROR: {csv_path} not found. Run fetch_lgd_up.py first.")
        return {}

    district_map = {}
    created = 0
    skipped = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing = db.query(GeographyDistrict).filter_by(
                lgd_code=row["lgd_code"]
            ).first()
            if existing:
                district_map[row["lgd_code"]] = existing.id
                skipped += 1
                continue

            district = GeographyDistrict(
                id=uuid.uuid4(),
                lgd_code=row["lgd_code"],
                state_id=state_id,
                canonical_name=row["canonical_name"],
                census_name=row.get("census_name") or row["canonical_name"],
                aliases=[],
                created_at=now(),
                updated_at=now(),
            )
            db.add(district)
            db.flush()
            district_map[row["lgd_code"]] = district.id
            created += 1

    db.commit()
    print(f"  Districts: {created} created, {skipped} skipped")
    return district_map


def load_blocks(db: Session, district_map):
    """Load blocks from CSV."""
    csv_path = RAW_DIR / "up_blocks.csv"
    if not csv_path.exists():
        print(f"  ERROR: {csv_path} not found.")
        return {}

    block_map = {}
    created = 0
    skipped = 0
    warnings = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("lgd_code"):
                continue

            existing = db.query(GeographyBlock).filter_by(
                lgd_code=row["lgd_code"]
            ).first()
            if existing:
                block_map[row["lgd_code"]] = existing.id
                skipped += 1
                continue

            district_id = district_map.get(row["district_lgd_code"])
            if not district_id:
                district = db.query(GeographyDistrict).filter_by(
                    lgd_code=row["district_lgd_code"]
                ).first()
                if district:
                    district_id = district.id
                else:
                    warnings += 1
                    continue

            block = GeographyBlock(
                id=uuid.uuid4(),
                lgd_code=row["lgd_code"],
                district_id=district_id,
                canonical_name=row["canonical_name"],
                aliases=[],
                created_at=now(),
                updated_at=now(),
            )
            db.add(block)
            db.flush()
            block_map[row["lgd_code"]] = block.id
            created += 1

            # Batch commit every 100 records
            if created % 100 == 0:
                db.commit()

    db.commit()
    print(f"  Blocks: {created} created, {skipped} skipped, {warnings} warnings")
    return block_map


def load_villages(db: Session, block_map, district_map):
    """Load villages from CSV."""
    csv_path = RAW_DIR / "up_villages.csv"
    if not csv_path.exists():
        print(f"  ERROR: {csv_path} not found.")
        return

    created = 0
    skipped = 0
    warnings = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("lgd_code"):
                continue

            existing = db.query(GeographyVillage).filter_by(
                lgd_code=row["lgd_code"]
            ).first()
            if existing:
                skipped += 1
                continue

            block_id = block_map.get(row.get("block_lgd_code"))
            if not block_id:
                block = db.query(GeographyBlock).filter_by(
                    lgd_code=row.get("block_lgd_code", "")
                ).first()
                if block:
                    block_id = block.id
                else:
                    warnings += 1
                    continue

            district_id = district_map.get(row.get("district_lgd_code"))
            if not district_id:
                district = db.query(GeographyDistrict).filter_by(
                    lgd_code=row.get("district_lgd_code", "")
                ).first()
                if district:
                    district_id = district.id
                else:
                    warnings += 1
                    continue

            pin_codes = []
            if row.get("pin_codes"):
                pin_codes = [p.strip() for p in row["pin_codes"].split(",") if p.strip()]

            village = GeographyVillage(
                id=uuid.uuid4(),
                lgd_code=row["lgd_code"],
                block_id=block_id,
                district_id=district_id,
                canonical_name=row["canonical_name"],
                census_name=row.get("census_name"),
                census_village_code=row.get("census_village_code"),
                pin_codes=pin_codes if pin_codes else None,
                aliases=[],
                created_at=now(),
                updated_at=now(),
            )
            db.add(village)
            created += 1

            # Batch commit every 500 records for performance
            if created % 500 == 0:
                db.commit()
                if created % 5000 == 0:
                    print(f"    ... {created} villages loaded")

    db.commit()
    print(f"  Villages: {created} created, {skipped} skipped, {warnings} warnings")


if __name__ == "__main__":
    print("=" * 60)
    print("Loading UP Geography Data into Database")
    print("=" * 60)

    reset = "--reset" in sys.argv

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
