#!/usr/bin/env python3
"""Audit product catalog source-verification readiness.

Read-only. This does not scrape websites. It reports whether local product rows
have enough source/review metadata to move from demo/reference into reviewed or
verified catalog status.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text
from app.core.database import SessionLocal

TABLE_CANDIDATES = [
    "agricultural_products",
    "agricultural_inputs",
    "input_categories",
    "manufacturers",
    "company_discovery_candidates",
    "company_profiles",
]

SOURCE_COLUMNS = [
    "source_url",
    "source_notes",
    "source_text",
    "source_references",
    "evidence_references",
    "registration_number",
    "label_url",
    "catalog_url",
    "review_status",
    "verification_status",
    "trust_status",
    "organic_natural_classification",
    "input_origin_type",
    "metadata",
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


def count_non_empty(db, table_name: str, column: str) -> int:
    return int(
        db.execute(
            text(
                f"""
                select count(*)
                from {table_name}
                where {column} is not null
                  and trim(cast({column} as text)) not in ('', '[]', '{{}}', 'null')
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


def safe_sample_products(db, table_name: str, columns: list[str]) -> list[dict]:
    printable = [
        col for col in [
            "id",
            "code",
            "product_code",
            "name",
            "canonical_name",
            "manufacturer_id",
            "input_id",
            "review_status",
            "verification_status",
            "trust_status",
            "source_url",
            "label_url",
            "registration_number",
        ]
        if col in columns
    ]

    if not printable:
        return []

    rows = db.execute(
        text(f"select {', '.join(printable)} from {table_name} order by 1 limit 15")
    ).mappings().all()
    return [dict(row) for row in rows]


def table_summary(db, table_name: str) -> dict:
    exists = table_exists(db, table_name)
    summary = {
        "table": table_name,
        "exists": exists,
        "row_count": 0,
        "columns": [],
        "source_columns_present": [],
        "source_column_non_empty_counts": {},
        "status_counts": {},
        "safe_samples": [],
    }

    if not exists:
        return summary

    columns = columns_for(db, table_name)
    summary["columns"] = columns
    summary["row_count"] = count(db, table_name)
    summary["source_columns_present"] = [col for col in SOURCE_COLUMNS if col in columns]

    for col in summary["source_columns_present"]:
        summary["source_column_non_empty_counts"][col] = count_non_empty(db, table_name, col)

    for col in ["review_status", "verification_status", "trust_status", "input_origin_type", "organic_natural_classification"]:
        if col in columns:
            summary["status_counts"][col] = grouped_counts(db, table_name, col)

    if table_name == "agricultural_products":
        summary["safe_samples"] = safe_sample_products(db, table_name, columns)

    return summary


def readiness_from(summary_by_table: dict) -> dict:
    products = summary_by_table.get("agricultural_products", {})
    product_count = products.get("row_count", 0)
    source_counts = products.get("source_column_non_empty_counts", {})

    has_source_fields = bool(products.get("source_columns_present"))
    products_with_source_url = source_counts.get("source_url", 0)
    products_with_source_text = source_counts.get("source_text", 0)
    products_with_label_url = source_counts.get("label_url", 0)
    products_with_registration = source_counts.get("registration_number", 0)
    products_with_review_status = source_counts.get("review_status", 0) or source_counts.get("verification_status", 0)

    return {
        "product_rows_present": product_count > 0,
        "product_count": product_count,
        "source_fields_present": has_source_fields,
        "products_with_source_url": products_with_source_url,
        "products_with_source_text": products_with_source_text,
        "products_with_label_url": products_with_label_url,
        "products_with_registration_number": products_with_registration,
        "products_with_review_or_verification_status": products_with_review_status,
        "ready_for_demo_reference_catalog": product_count > 0,
        "ready_for_manufacturer_verified_catalog": (
            product_count > 0
            and products_with_source_url == product_count
            and products_with_review_status == product_count
        ),
        "ready_for_dosage_claims": products_with_label_url > 0 or products_with_registration > 0,
        "ready_for_organic_natural_claims": False,
        "reason_organic_natural_not_ready": (
            "Organic/natural classification needs explicit evidence. NATURAL means natural-farming/on-farm or low-external-input practice; ORGANIC means externally supplied organic-compatible product with certification/evidence review."
        ),
    }


def main() -> int:
    db = SessionLocal()
    try:
        summaries = [table_summary(db, table) for table in TABLE_CANDIDATES]
        summary_by_table = {item["table"]: item for item in summaries}
        readiness = readiness_from(summary_by_table)

        result = {
            "schema_version": "product_source_verification_readiness_audit.v1",
            "external_calls_made": False,
            "tables": summaries,
            "readiness": readiness,
            "next_actions": [
                "Keep demo/reference rows clearly labeled until source review is complete.",
                "Use Screener/TNAU only for company discovery, not product truth.",
                "Prefer regulator registration and product label evidence for dosage and legal claims.",
                "Use manufacturer pages/catalogs for product discovery and descriptive source text.",
                "Keep ORGANIC and NATURAL as separate classifications with evidence notes.",
                "Do not scrape products aggressively; use company-by-company reviewed passes.",
            ],
        }
    finally:
        db.close()

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["readiness"]["product_rows_present"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
