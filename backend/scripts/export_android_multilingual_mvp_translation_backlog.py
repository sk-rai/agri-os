#!/usr/bin/env python3
"""Export MVP Android multilingual translation backlog.

Read-only. Produces CSV/JSON artifacts for human/native-speaker review.
It does not write to DB and does not modify backend form registries.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from audit_android_multilingual_form_labels import (  # noqa: E402
    MVP_CORE_FIELD_IDS,
    MVP_NATIVE_LABEL_FORMS,
    MVP_NATIVE_OPTION_SETS,
    REGIONAL_FALLBACK_LANGUAGES,
    TARGET_LANGUAGES,
    _collect_label_maps_from_form,
    _collect_label_maps_from_option_set,
    _is_mvp_native_label_path,
    _parse_label_path,
)
from app.modules.workflow.forms import FORM_REGISTRY, PROFILE_OPTION_REGISTRY  # noqa: E402


OUTPUT_DIR = BACKEND_DIR.parent / "data" / "staged" / "android_multilingual"
CSV_PATH = OUTPUT_DIR / "android_mvp_native_translation_backlog.csv"
JSON_PATH = OUTPUT_DIR / "android_mvp_native_translation_backlog.json"


def collect_label_maps() -> list[tuple[str, dict[str, str]]]:
    label_maps: list[tuple[str, dict[str, str]]] = []

    for form_id, form in sorted(FORM_REGISTRY.items()):
        label_maps.extend(_collect_label_maps_from_form(form_id, form))

    for option_set, payload in sorted(PROFILE_OPTION_REGISTRY.items()):
        label_maps.extend(_collect_label_maps_from_option_set(option_set, payload))

    return label_maps


def build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for path, labels in collect_label_maps():
        if not _is_mvp_native_label_path(path):
            continue

        missing_languages = [
            lang for lang in REGIONAL_FALLBACK_LANGUAGES
            if not labels.get(lang)
        ]
        if not missing_languages:
            continue

        parsed = _parse_label_path(path)
        rows.append({
            "label_path": path,
            "source": parsed.get("source"),
            "form_id": parsed.get("form_id") or "",
            "option_set": parsed.get("option_set") or "",
            "field_id": parsed.get("field_id") or "",
            "label_kind": parsed.get("label_kind") or "",
            "en": labels.get("en", ""),
            "hi": labels.get("hi", ""),
            "kn": labels.get("kn", ""),
            "mr": labels.get("mr", ""),
            "pa": labels.get("pa", ""),
            "missing_languages": ",".join(missing_languages),
            "review_status": "NEEDS_NATIVE_REVIEW",
            "notes": "",
        })

    return rows


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = build_rows()
    fieldnames = [
        "label_path",
        "source",
        "form_id",
        "option_set",
        "field_id",
        "label_kind",
        "en",
        "hi",
        "kn",
        "mr",
        "pa",
        "missing_languages",
        "review_status",
        "notes",
    ]

    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "schema_version": "android_mvp_native_translation_backlog.v1",
        "mode": "READ_ONLY_EXPORT",
        "db_writes_made": False,
        "external_calls_made": False,
        "target_languages": TARGET_LANGUAGES,
        "native_review_languages": REGIONAL_FALLBACK_LANGUAGES,
        "scope": {
            "forms": MVP_NATIVE_LABEL_FORMS,
            "option_sets": MVP_NATIVE_OPTION_SETS,
            "core_field_ids": {key: sorted(value) for key, value in sorted(MVP_CORE_FIELD_IDS.items())},
        },
        "counts": {
            "rows": len(rows),
            "missing_native_labels_by_language": {
                lang: sum(1 for row in rows if lang in row["missing_languages"].split(","))
                for lang in REGIONAL_FALLBACK_LANGUAGES
            },
        },
        "output_files": {
            "csv": str(CSV_PATH),
            "json": str(JSON_PATH),
        },
        "readiness": {
            "safe_read_only": True,
            "ready_for_human_translation_review": bool(rows),
            "english_source_available": all(row["en"] for row in rows),
            "hindi_reference_available": all(row["hi"] for row in rows),
        },
        "samples": rows[:20],
    }

    JSON_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
