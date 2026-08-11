#!/usr/bin/env python3
"""Verify admin localization tables and seeded platform content keys."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal


REQUIRED_TABLES = [
    "localized_content_keys",
    "localized_content_overrides",
    "land_intelligence_summary_overrides",
]


def main() -> int:
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        missing_tables = [table for table in REQUIRED_TABLES if not inspector.has_table(table)]

        result = {
            "schema_version": "admin_localization_tables_verification.v1",
            "mode": "READ_ONLY_VERIFY",
            "db_writes_made": False,
            "external_calls_made": False,
            "required_tables": REQUIRED_TABLES,
            "missing_tables": missing_tables,
            "counts": {},
            "readiness": {},
            "samples": {},
        }

        if missing_tables:
            result["readiness"] = {
                "migration_applied": False,
                "seeded_content_keys": False,
                "ready_for_admin_api_contract": False,
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            return 1

        content_key_count = int(db.execute(text("select count(*) from localized_content_keys where is_active = true")).scalar() or 0)
        missing_en_count = int(db.execute(text("""
            select count(*)
            from localized_content_keys
            where is_active = true
              and not (default_labels ? 'en')
        """)).scalar() or 0)
        override_count = int(db.execute(text("select count(*) from localized_content_overrides where is_active = true")).scalar() or 0)
        summary_override_count = int(db.execute(text("select count(*) from land_intelligence_summary_overrides where is_active = true")).scalar() or 0)

        by_source = db.execute(text("""
            select source, count(*) as count
            from localized_content_keys
            where is_active = true
            group by source
            order by source
        """)).mappings().all()

        samples = db.execute(text("""
            select content_key, source, content_kind, default_labels
            from localized_content_keys
            where is_active = true
            order by content_key
            limit 20
        """)).mappings().all()

        result["counts"] = {
            "localized_content_keys": content_key_count,
            "localized_content_overrides": override_count,
            "land_intelligence_summary_overrides": summary_override_count,
            "localized_content_keys_missing_english": missing_en_count,
            "content_keys_by_source": {row["source"]: row["count"] for row in by_source},
        }
        result["samples"] = {
            "first_20_content_keys": [dict(row) for row in samples],
        }
        result["readiness"] = {
            "migration_applied": True,
            "seeded_content_keys": content_key_count > 0,
            "english_fallback_complete": missing_en_count == 0,
            "ready_for_admin_api_contract": content_key_count > 0 and missing_en_count == 0,
            "safe_read_only": True,
        }

        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result["readiness"]["ready_for_admin_api_contract"] else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
