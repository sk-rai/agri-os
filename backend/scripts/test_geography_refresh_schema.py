#!/usr/bin/env python3
"""Regression checks for modular geography refresh schema."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.modules.master_data.models import (
    GeographyBlock,
    GeographyDistrict,
    GeographyImportBatch,
    GeographyPostalReference,
    GeographyState,
    GeographyVillage,
    GeographyVillagePinLink,
)


def check(condition, label, detail=None):
    if condition:
        print(f"  PASS {label}")
        if detail is not None:
            print(f"       {detail}")
        return
    print(f"  FAIL {label}")
    if detail is not None:
        print(f"       {detail}")
    raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("GEOGRAPHY REFRESH SCHEMA REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)

    try:
        state = GeographyState(lgd_code=f"T{suffix}", canonical_name="Schema Test State", aliases=[])
        db.add(state)
        db.commit()
        db.refresh(state)

        d1 = GeographyDistrict(lgd_code=f"D{suffix}1", state_id=state.id, canonical_name="District One", aliases=[])
        d2 = GeographyDistrict(lgd_code=f"D{suffix}2", state_id=state.id, canonical_name="District Two", aliases=[])
        db.add_all([d1, d2])
        db.commit()
        db.refresh(d1)
        db.refresh(d2)

        shared_block_code = f"B{suffix}"
        b1 = GeographyBlock(lgd_code=shared_block_code, district_id=d1.id, canonical_name="Shared Block Code One", aliases=[])
        b2 = GeographyBlock(lgd_code=shared_block_code, district_id=d2.id, canonical_name="Shared Block Code Two", aliases=[])
        db.add_all([b1, b2])
        db.commit()
        check(True, "Same block LGD code allowed under different districts")
        db.refresh(b1)
        db.refresh(b2)

        duplicate_block = GeographyBlock(lgd_code=shared_block_code, district_id=d1.id, canonical_name="Duplicate Same District", aliases=[])
        db.add(duplicate_block)
        try:
            db.commit()
            check(False, "Duplicate block LGD code blocked within same district")
        except IntegrityError:
            db.rollback()
            check(True, "Duplicate block LGD code blocked within same district")

        shared_village_code = f"V{suffix}"
        v1 = GeographyVillage(lgd_code=shared_village_code, block_id=b1.id, district_id=d1.id, canonical_name="Shared Village One", pin_codes=[], aliases=[])
        v2 = GeographyVillage(lgd_code=shared_village_code, block_id=b2.id, district_id=d2.id, canonical_name="Shared Village Two", pin_codes=[], aliases=[])
        db.add_all([v1, v2])
        db.commit()
        check(True, "Same village LGD code allowed under different blocks")
        db.refresh(v1)

        batch = GeographyImportBatch(
            source_system="OGD",
            source_resource_id="regression",
            source_label="Regression source",
            raw_manifest_path="data/raw/example/manifest.json",
            validation_report_path="data/staged/example/validation_report.json",
            refresh_mode="INCREMENTAL_REFRESH",
            status="APPLIED",
            retrieved_at=now,
            validated_at=now,
            applied_at=now,
            row_counts={"example": 1},
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)
        check(bool(batch.id), "Import batch persists provenance")

        postal = GeographyPostalReference(
            import_batch_id=batch.id,
            pin_code="560001",
            office_name="Schema Test B.O",
            office_type="BO",
            delivery_status="Delivery",
            postal_district_name="Bengaluru",
            postal_state_name="KARNATAKA",
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(postal)
        db.commit()
        check(True, "Postal reference persists")

        link = GeographyVillagePinLink(
            import_batch_id=batch.id,
            geography_village_id=v1.id,
            pin_code="560001",
            state_lgd_code=state.lgd_code,
            state_name=state.canonical_name,
            district_lgd_code=d1.lgd_code,
            district_name=d1.canonical_name,
            subdistrict_lgd_code=b1.lgd_code,
            subdistrict_name=b1.canonical_name,
            village_lgd_code=v1.lgd_code,
            village_name=v1.canonical_name,
            match_status="MATCHED",
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(link)
        db.commit()
        check(True, "Village PIN link persists with full LGD context")

        print("=" * 72)
        print("Geography refresh schema validated")
        print("=" * 72)
        return 0

    finally:
        db.query(GeographyVillagePinLink).filter(GeographyVillagePinLink.state_lgd_code == f"T{suffix}").delete(synchronize_session=False)
        db.query(GeographyPostalReference).filter(GeographyPostalReference.office_name == "Schema Test B.O").delete(synchronize_session=False)
        db.query(GeographyImportBatch).filter(GeographyImportBatch.source_resource_id == "regression").delete(synchronize_session=False)
        db.query(GeographyVillage).filter(GeographyVillage.district_id.in_([d1.id, d2.id]) if "d1" in locals() and "d2" in locals() else False).delete(synchronize_session=False)
        db.query(GeographyBlock).filter(GeographyBlock.district_id.in_([d1.id, d2.id]) if "d1" in locals() and "d2" in locals() else False).delete(synchronize_session=False)
        db.query(GeographyDistrict).filter(GeographyDistrict.state_id == state.id if "state" in locals() else False).delete(synchronize_session=False)
        db.query(GeographyState).filter(GeographyState.lgd_code == f"T{suffix}").delete(synchronize_session=False)
        db.commit()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
