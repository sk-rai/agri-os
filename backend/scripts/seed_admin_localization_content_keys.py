#!/usr/bin/env python3
"""Seed platform-owned localized content keys from audited backend sources."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal
from scripts.audit_admin_localization_content_sources import collect_db_rows, collect_form_rows, collect_option_rows


REQUIRED_TABLE = "localized_content_keys"


def table_exists(db, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def audited_rows(db) -> list[dict]:
    rows = []
    rows.extend(collect_form_rows())
    rows.extend(collect_option_rows())
    db_rows, _skipped = collect_db_rows(db)
    rows.extend(db_rows)

    unique = {}
    for row in rows:
        unique[row["content_key"]] = row
    return [unique[key] for key in sorted(unique)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    db = SessionLocal()
    result = {
        "schema_version": "admin_localization_content_keys_seed.v1",
        "mode": "DRY_RUN" if dry_run else "APPLY",
        "db_writes_made": bool(args.apply),
        "external_calls_made": False,
        "table": REQUIRED_TABLE,
        "counts": {
            "audited_content_keys": 0,
            "existing": 0,
            "created": 0,
            "updated": 0,
            "would_create": 0,
            "would_update": 0,
        },
        "samples": {
            "created_or_would_create": [],
            "updated_or_would_update": [],
        },
        "readiness": {},
    }

    try:
        if not table_exists(db, REQUIRED_TABLE):
            result["readiness"] = {
                "migration_applied": False,
                "ready": False,
                "reason": "Run alembic upgrade head so localized_content_keys exists.",
            }
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            return 1

        now = datetime.now(timezone.utc)
        rows = audited_rows(db)
        result["counts"]["audited_content_keys"] = len(rows)

        for item in rows:
            existing = db.execute(
                text("""
                    select id, default_labels, source, content_kind, metadata
                    from localized_content_keys
                    where content_key = :content_key
                    limit 1
                """),
                {"content_key": item["content_key"]},
            ).mappings().first()

            payload = {
                "id": str(uuid.uuid4()),
                "content_key": item["content_key"],
                "source": item["source"],
                "content_kind": item["content_kind"],
                "default_labels": json.dumps(item["default_labels"]),
                "metadata": json.dumps(item["metadata"]),
                "updated_at": now,
            }

            if existing:
                result["counts"]["existing"] += 1
                changed = (
                    existing["default_labels"] != item["default_labels"]
                    or existing["source"] != item["source"]
                    or existing["content_kind"] != item["content_kind"]
                    or (existing["metadata"] or {}) != item["metadata"]
                )
                if changed:
                    if dry_run:
                        result["counts"]["would_update"] += 1
                    else:
                        db.execute(
                            text("""
                                update localized_content_keys
                                set source = :source,
                                    content_kind = :content_kind,
                                    default_labels = cast(:default_labels as jsonb),
                                    metadata = cast(:metadata as jsonb),
                                    updated_at = :updated_at
                                where content_key = :content_key
                            """),
                            payload,
                        )
                        result["counts"]["updated"] += 1
                    if len(result["samples"]["updated_or_would_update"]) < 20:
                        result["samples"]["updated_or_would_update"].append(item["content_key"])
            else:
                if dry_run:
                    result["counts"]["would_create"] += 1
                else:
                    db.execute(
                        text("""
                            insert into localized_content_keys (
                                id,
                                content_key,
                                source,
                                content_kind,
                                default_labels,
                                metadata,
                                review_status,
                                created_at,
                                updated_at,
                                version,
                                is_active
                            ) values (
                                cast(:id as uuid),
                                :content_key,
                                :source,
                                :content_kind,
                                cast(:default_labels as jsonb),
                                cast(:metadata as jsonb),
                                'PLATFORM_DEFAULT',
                                :updated_at,
                                :updated_at,
                                'v1.0',
                                true
                            )
                        """),
                        payload,
                    )
                    result["counts"]["created"] += 1
                if len(result["samples"]["created_or_would_create"]) < 20:
                    result["samples"]["created_or_would_create"].append(item["content_key"])

        if dry_run:
            db.rollback()
        else:
            db.commit()

        result["readiness"] = {
            "migration_applied": True,
            "ready": True,
            "safe_to_rerun": True,
        }
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
