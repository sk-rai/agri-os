#!/usr/bin/env python3
"""Audit language/localization readiness for Android/demo content.

Read-only. Reports where backend-driven labels/content exist and where broader
Hindi/local-language QA is still missing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text
from app.core.database import SessionLocal

TABLES = [
    "crops",
    "crop_lifecycle_templates",
    "crop_taxonomy_nodes",
    "agricultural_inputs",
    "agricultural_products",
    "input_categories",
    "broadcast_campaigns",
    "broadcast_contents",
    "broadcast_deliveries",
    "profile_option_sets",
    "profile_form_configs",
]


def table_exists(db, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def columns_for(db, table_name: str) -> list[str]:
    rows = db.execute(
        text("""
            select column_name
            from information_schema.columns
            where table_name = :table_name
            order by ordinal_position
        """),
        {"table_name": table_name},
    ).all()
    return [row[0] for row in rows]


def count(db, table_name: str) -> int:
    return int(db.execute(text(f"select count(*) from {table_name}")).scalar() or 0)


def non_empty_json_count(db, table_name: str, column: str) -> int:
    return int(
        db.execute(
            text(
                f"""
                select count(*)
                from {table_name}
                where {column} is not null
                  and cast({column} as text) not in ('[]', '{{}}', 'null', '')
                """
            )
        ).scalar()
        or 0
    )


def text_like_hindi_count(db, table_name: str, column: str) -> int:
    return int(
        db.execute(
            text(
                f"""
                select count(*)
                from {table_name}
                where {column} is not null
                  and cast({column} as text) ~ '[\\u0900-\\u097F]'
                """
            )
        ).scalar()
        or 0
    )


def grouped_counts(db, table_name: str, column: str) -> dict:
    rows = db.execute(
        text(
            f"""
            select cast({column} as text) as value, count(*) as count
            from {table_name}
            group by cast({column} as text)
            order by cast({column} as text)
            """
        )
    ).mappings().all()
    return {str(row["value"]): int(row["count"]) for row in rows}


def table_summary(db, table_name: str) -> dict:
    exists = table_exists(db, table_name)
    summary = {
        "table": table_name,
        "exists": exists,
        "row_count": 0,
        "columns": [],
        "localization_columns_present": [],
        "localized_json_non_empty_counts": {},
        "hindi_script_counts": {},
        "status_counts": {},
    }

    if not exists:
        return summary

    columns = columns_for(db, table_name)
    summary["columns"] = columns
    summary["row_count"] = count(db, table_name)

    localization_candidates = [
        "title",
        "description",
        "canonical_name",
        "display_name",
        "brand_name",
        "aliases",
        "metadata",
        "content",
        "localized_content",
        "translations",
        "language_code",
        "locale",
        "review_status",
        "translation_status",
    ]

    present = [col for col in localization_candidates if col in columns]
    summary["localization_columns_present"] = present

    for col in present:
        if col in {"aliases", "metadata", "content", "localized_content", "translations", "title", "description"}:
            summary["localized_json_non_empty_counts"][col] = non_empty_json_count(db, table_name, col)
            summary["hindi_script_counts"][col] = text_like_hindi_count(db, table_name, col)

    for col in ["language_code", "locale", "review_status", "translation_status", "status"]:
        if col in columns:
            summary["status_counts"][col] = grouped_counts(db, table_name, col)

    return summary


def main() -> int:
    db = SessionLocal()
    try:
        summaries = [table_summary(db, table) for table in TABLES]
        by_table = {item["table"]: item for item in summaries}

        crop_rows = by_table.get("crops", {}).get("row_count", 0)
        crop_alias_hindi = by_table.get("crops", {}).get("hindi_script_counts", {}).get("aliases", 0)
        lifecycle_rows = by_table.get("crop_lifecycle_templates", {}).get("row_count", 0)
        lifecycle_hindi = by_table.get("crop_lifecycle_templates", {}).get("hindi_script_counts", {}).get("aliases", 0)

        broadcast_tables_ready = any(
            item["exists"] and item["row_count"] > 0
            for item in summaries
            if item["table"] in {"broadcast_campaigns", "broadcast_contents"}
        )

        result = {
            "schema_version": "language_localization_readiness_audit.v1",
            "external_translation_calls_made": False,
            "tables": summaries,
            "readiness": {
                "backend_driven_labels_supported": True,
                "broadcast_content_tables_present": broadcast_tables_ready,
                "crop_rows_present": crop_rows > 0,
                "crop_hindi_alias_coverage_count": crop_alias_hindi,
                "crop_hindi_alias_coverage_percent": round((crop_alias_hindi / crop_rows) * 100, 2) if crop_rows else 0,
                "workflow_stage_rows_present": lifecycle_rows > 0,
                "workflow_stage_hindi_alias_coverage_count": lifecycle_hindi,
                "ready_for_english_first_android_qa": True,
                "ready_for_broad_hindi_language_qa": crop_alias_hindi >= crop_rows and lifecycle_hindi >= lifecycle_rows,
                "safe_for_unreviewed_dynamic_advisory_translation": False,
            },
            "translation_policy": {
                "production_publish_rule": "Publish only client/agronomist-reviewed language variants.",
                "machine_translation_role": "Draft assistance only unless explicitly marked demo/unverified.",
                "missing_translation_fallback": "Fallback to source language or suppress localized variant with warning.",
                "android_rule": "Android renders backend-selected approved content variant; Android does not translate advisories locally.",
            },
            "next_actions": [
                "Add reviewed Hindi/local-language seed samples for crops and workflow stages.",
                "Add advisory content variant statuses such as SOURCE, MACHINE_TRANSLATED_DRAFT, REVIEWED_APPROVED.",
                "Require reviewer approval before localized advisory broadcast in production.",
                "Keep Android fallback behavior backend-driven.",
            ],
        }
    finally:
        db.close()

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
