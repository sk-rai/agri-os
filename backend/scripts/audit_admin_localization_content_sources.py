#!/usr/bin/env python3
"""Audit backend-owned translatable/admin-localizable content sources.

Read-only. No DB writes and no external calls.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal
from app.modules.workflow.forms import FORM_REGISTRY, PROFILE_OPTION_REGISTRY


TARGET_LANGUAGES = ["en", "hi", "kn", "mr", "pa"]
REGIONAL_LANGUAGES = ["kn", "mr", "pa"]


def model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


def label_status(labels: dict[str, str] | None) -> dict[str, Any]:
    labels = labels or {}
    present = sorted([lang for lang in TARGET_LANGUAGES if labels.get(lang)])
    missing = sorted([lang for lang in TARGET_LANGUAGES if not labels.get(lang)])
    return {
        "present_languages": present,
        "missing_languages": missing,
        "english_fallback_available": bool(labels.get("en")),
        "hindi_available": bool(labels.get("hi")),
        "regional_native_complete": all(bool(labels.get(lang)) for lang in REGIONAL_LANGUAGES),
    }


def content_row(
    source: str,
    key: str,
    kind: str,
    labels: dict[str, str] | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = label_status(labels)
    return {
        "source": source,
        "content_key": key,
        "content_kind": kind,
        "default_labels": labels or {},
        "metadata": metadata or {},
        **status,
    }


def collect_form_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for form_id, form in sorted(FORM_REGISTRY.items()):
        payload = model_dump(form)

        for kind in ["title", "description", "submit_label"]:
            labels = payload.get(kind)
            if isinstance(labels, dict):
                rows.append(content_row(
                    "profile_form",
                    f"profile_form.{form_id}.{kind}",
                    kind,
                    labels,
                    {"form_id": form_id},
                ))

        for field in payload.get("fields") or []:
            field_id = field.get("id", "<unknown>")

            for kind in ["label", "placeholder", "hint"]:
                labels = field.get(kind)
                if isinstance(labels, dict):
                    rows.append(content_row(
                        "profile_form_field",
                        f"profile_form.{form_id}.field.{field_id}.{kind}",
                        kind,
                        labels,
                        {"form_id": form_id, "field_id": field_id},
                    ))

            for option in field.get("options") or []:
                option_value = option.get("value", "<unknown>")
                labels = option.get("label")
                if isinstance(labels, dict):
                    rows.append(content_row(
                        "profile_form_field_option",
                        f"profile_form.{form_id}.field.{field_id}.option.{option_value}.label",
                        "label",
                        labels,
                        {
                            "form_id": form_id,
                            "field_id": field_id,
                            "option_value": option_value,
                        },
                    ))

    return rows


def collect_option_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for option_set, payload in sorted(PROFILE_OPTION_REGISTRY.items()):
        value = model_dump(payload)

        title = value.get("title")
        if isinstance(title, dict):
            rows.append(content_row(
                "profile_option_set",
                f"profile_option_set.{option_set}.title",
                "title",
                title,
                {"option_set": option_set},
            ))

        for option in value.get("options") or []:
            option_value = option.get("value", "<unknown>")
            labels = option.get("label")
            if isinstance(labels, dict):
                rows.append(content_row(
                    "profile_option_set_option",
                    f"profile_option_set.{option_set}.option.{option_value}.label",
                    "label",
                    labels,
                    {"option_set": option_set, "option_value": option_value},
                ))

    return rows


def table_exists(db, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def columns_for(db, table_name: str) -> set[str]:
    if not table_exists(db, table_name):
        return set()
    return {column["name"] for column in inspect(db.bind).get_columns(table_name)}


def collect_db_rows(db) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    skipped: list[str] = []

    if table_exists(db, "workflow_template_stages"):
        cols = columns_for(db, "workflow_template_stages")
        stage_name_col = "stage_name" if "stage_name" in cols else None
        description_col = "description" if "description" in cols else None

        select_parts = [
            "stage_code",
            f"{stage_name_col} as stage_name" if stage_name_col else "null as stage_name",
            f"{description_col} as description" if description_col else "null as description",
        ]

        stage_rows = db.execute(text(f"""
            select {", ".join(select_parts)}
            from workflow_template_stages
            where coalesce(is_active, true) = true
            limit 10000
        """)).mappings().all()

        for item in stage_rows:
            stage_code = item["stage_code"]
            name = item.get("stage_name")
            desc = item.get("description")

            labels = name if isinstance(name, dict) else {"en": str(name or stage_code).replace("_", " ").title()}
            rows.append(content_row(
                "workflow_stage",
                f"workflow_stage.{stage_code}.name",
                "name",
                labels,
                dict(item),
            ))

            if isinstance(desc, dict):
                rows.append(content_row(
                    "workflow_stage",
                    f"workflow_stage.{stage_code}.description",
                    "description",
                    desc,
                    dict(item),
                ))
            elif desc:
                rows.append(content_row(
                    "workflow_stage",
                    f"workflow_stage.{stage_code}.description",
                    "description",
                    {"en": str(desc)},
                    dict(item),
                ))
    else:
        skipped.append("workflow_template_stages")

    if table_exists(db, "input_categories"):
        cols = columns_for(db, "input_categories")
        code_col = "code" if "code" in cols else None
        name_col = "name" if "name" in cols else None
        desc_col = "description" if "description" in cols else None

        if code_col and name_col:
            cat_rows = db.execute(text(f"""
                select code, name, {"description" if desc_col else "null as description"}
                from input_categories
                where coalesce(is_active, true) = true
                limit 10000
            """)).mappings().all()

            for item in cat_rows:
                rows.append(content_row(
                    "input_category",
                    f"input_category.{item['code']}.name",
                    "name",
                    {"en": str(item["name"])},
                    dict(item),
                ))
                if item.get("description"):
                    rows.append(content_row(
                        "input_category",
                        f"input_category.{item['code']}.description",
                        "description",
                        {"en": str(item["description"])},
                        dict(item),
                    ))
        else:
            skipped.append("input_categories.columns")
    else:
        skipped.append("input_categories")

    if table_exists(db, "agricultural_inputs"):
        cols = columns_for(db, "agricultural_inputs")
        code_col = "code" if "code" in cols else None
        name_col = "name" if "name" in cols else None
        desc_col = "description" if "description" in cols else None

        if code_col and name_col:
            input_rows = db.execute(text(f"""
                select code, name, {"description" if desc_col else "null as description"}
                from agricultural_inputs
                where coalesce(is_active, true) = true
                limit 10000
            """)).mappings().all()

            for item in input_rows:
                rows.append(content_row(
                    "agricultural_input",
                    f"agricultural_input.{item['code']}.name",
                    "name",
                    {"en": str(item["name"])},
                    dict(item),
                ))
                if item.get("description"):
                    rows.append(content_row(
                        "agricultural_input",
                        f"agricultural_input.{item['code']}.description",
                        "description",
                        {"en": str(item["description"])},
                        dict(item),
                    ))
        else:
            skipped.append("agricultural_inputs.columns")
    else:
        skipped.append("agricultural_inputs")

    if table_exists(db, "crop_stage_input_rules"):
        cols = columns_for(db, "crop_stage_input_rules")
        required = {"crop_code", "stage_code", "activity_type", "input_code"}
        if required.issubset(cols):
            optional_cols = [col for col in ["season_code", "timing_note", "safety_note", "application_method"] if col in cols]
            select_cols = ["crop_code", "stage_code", "activity_type", "input_code"] + optional_cols
            rule_rows = db.execute(text(f"""
                select {", ".join(select_cols)}
                from crop_stage_input_rules
                where coalesce(is_active, true) = true
                limit 10000
            """)).mappings().all()

            for item in rule_rows:
                season = item.get("season_code") or "ANY"
                base = f"crop_stage_input_rule.{item['crop_code']}.{season}.{item['stage_code']}.{item['activity_type']}.{item['input_code']}"
                for field in ["timing_note", "safety_note", "application_method"]:
                    if item.get(field):
                        rows.append(content_row(
                            "crop_stage_input_rule",
                            base + f".{field}",
                            field,
                            {"en": str(item[field])},
                            dict(item),
                        ))
        else:
            skipped.append("crop_stage_input_rules.columns")
    else:
        skipped.append("crop_stage_input_rules")

    if table_exists(db, "agricultural_products"):
        cols = columns_for(db, "agricultural_products")
        code_col = "product_code" if "product_code" in cols else None
        brand_col = "brand_name" if "brand_name" in cols else None

        if code_col and brand_col:
            product_rows = db.execute(text("""
                select product_code, brand_name
                from agricultural_products
                where coalesce(is_active, true) = true
                limit 10000
            """)).mappings().all()

            for item in product_rows:
                rows.append(content_row(
                    "agricultural_product",
                    f"agricultural_product.{item['product_code']}.brand_name",
                    "brand_name",
                    {"en": str(item["brand_name"])},
                    dict(item),
                ))
        else:
            skipped.append("agricultural_products.columns")
    else:
        skipped.append("agricultural_products")

    if table_exists(db, "agricultural_product_packages") and table_exists(db, "agricultural_products"):
        package_cols = columns_for(db, "agricultural_product_packages")
        product_cols = columns_for(db, "agricultural_products")

        if {"id", "product_id", "pack_label"}.issubset(package_cols) and {"id", "product_code"}.issubset(product_cols):
            package_rows = db.execute(text("""
                select p.product_code, pkg.id::text as package_id, pkg.pack_label
                from agricultural_product_packages pkg
                join agricultural_products p on p.id = pkg.product_id
                where coalesce(pkg.is_active, true) = true
                limit 10000
            """)).mappings().all()

            for item in package_rows:
                rows.append(content_row(
                    "agricultural_product_package",
                    f"agricultural_product.{item['product_code']}.package.{item['package_id']}.pack_label",
                    "pack_label",
                    {"en": str(item["pack_label"])},
                    dict(item),
                ))
        else:
            skipped.append("agricultural_product_packages.columns")
    else:
        skipped.append("agricultural_product_packages")

    return rows, skipped


def summarize(rows: list[dict[str, Any]], skipped: list[str]) -> dict[str, Any]:
    by_source = Counter(row["source"] for row in rows)
    by_kind = Counter(row["content_kind"] for row in rows)
    missing = {lang: 0 for lang in TARGET_LANGUAGES}
    present = {lang: 0 for lang in TARGET_LANGUAGES}

    english_missing_samples: list[str] = []
    regional_missing_samples: dict[str, list[str]] = defaultdict(list)

    for item in rows:
        labels = item["default_labels"]
        for lang in TARGET_LANGUAGES:
            if labels.get(lang):
                present[lang] += 1
            else:
                missing[lang] += 1
                if lang == "en" and len(english_missing_samples) < 20:
                    english_missing_samples.append(item["content_key"])
                if lang in REGIONAL_LANGUAGES and len(regional_missing_samples[lang]) < 20:
                    regional_missing_samples[lang].append(item["content_key"])

    proposed_tables = [
        {
            "table": "localized_content_keys",
            "purpose": "Stable platform-owned key registry for labels/copy that admin may override.",
            "core_columns": [
                "id",
                "content_key",
                "source",
                "content_kind",
                "default_labels",
                "metadata",
                "is_active",
                "created_at",
                "updated_at",
            ],
        },
        {
            "table": "localized_content_overrides",
            "purpose": "Tenant/project/language scoped reviewed override text, without changing workflow/input semantics.",
            "core_columns": [
                "id",
                "tenant_id",
                "project_id",
                "content_key_id",
                "language_code",
                "override_text",
                "review_status",
                "is_active",
                "created_by",
                "updated_by",
                "created_at",
                "updated_at",
            ],
        },
        {
            "table": "land_intelligence_summary_overrides",
            "purpose": "Project/company editable Android-ready summary cards for region/season/soil/water/crops.",
            "core_columns": [
                "id",
                "tenant_id",
                "project_id",
                "scope_type",
                "scope_code",
                "language_code",
                "summary_payload",
                "review_status",
                "is_active",
                "created_at",
                "updated_at",
            ],
        },
    ]

    return {
        "schema_version": "admin_localization_content_source_audit.v1",
        "mode": "READ_ONLY_AUDIT",
        "db_writes_made": False,
        "external_calls_made": False,
        "target_languages": TARGET_LANGUAGES,
        "counts": {
            "content_keys": len(rows),
            "by_source": dict(sorted(by_source.items())),
            "by_kind": dict(sorted(by_kind.items())),
            "present_by_language": present,
            "missing_by_language": missing,
            "skipped_missing_tables": skipped,
        },
        "readiness": {
            "safe_read_only": True,
            "english_fallback_complete": missing["en"] == 0,
            "hindi_coverage_present": present["hi"] > 0,
            "regional_native_labels_complete": all(missing[lang] == 0 for lang in REGIONAL_LANGUAGES),
            "ready_to_design_override_tables": len(rows) > 0 and missing["en"] == 0,
            "android_must_keep_english_fallback": True,
        },
        "samples": {
            "first_30_content_keys": rows[:30],
            "missing_english_label_paths": english_missing_samples,
            "missing_regional_label_paths": dict(regional_missing_samples),
        },
        "proposed_content_key_contract": {
            "profile_form": "profile_form.{form_id}.{title|description|submit_label}",
            "profile_form_field": "profile_form.{form_id}.field.{field_id}.{label|placeholder|hint}",
            "profile_option": "profile_option_set.{option_set}.option.{value}.label",
            "workflow_stage": "workflow_stage.{stage_code}.{name|description}",
            "input": "agricultural_input.{input_code}.{name|description}",
            "input_rule": "crop_stage_input_rule.{crop}.{season}.{stage}.{activity}.{input}.{timing_note|safety_note|application_method}",
            "product": "agricultural_product.{product_code}.{brand_name|package.*.pack_label}",
        },
        "proposed_tables": proposed_tables,
        "next_step_recommendation": "Create Alembic table design for localized_content_keys and localized_content_overrides first; keep land-intelligence summary override payload Android-ready and read-only initially.",
    }


def main() -> int:
    rows: list[dict[str, Any]] = []
    rows.extend(collect_form_rows())
    rows.extend(collect_option_rows())

    db = SessionLocal()
    try:
        db_rows, skipped = collect_db_rows(db)
        rows.extend(db_rows)
    finally:
        db.close()

    payload = summarize(rows, skipped)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if payload["readiness"]["ready_to_design_override_tables"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
