#!/usr/bin/env python3
"""Audit Android multilingual profile-form label readiness.

Read-only. This does not call external services and does not modify the DB.

The Android rendering contract for backend-driven form labels is:

    label[currentLanguageCode] ?: label["en"]

This audit intentionally separates two concerns:

1. English fallback completeness, which must be green for all Android forms.
2. Native regional label coverage, which is currently incomplete for kn/mr/pa and
   should therefore be tested as explicit fallback behavior in Maestro.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.modules.workflow.forms import FORM_REGISTRY, PROFILE_OPTION_REGISTRY  # noqa: E402

TARGET_LANGUAGES = ["en", "hi", "kn", "mr", "pa"]
REGIONAL_FALLBACK_LANGUAGES = ["kn", "mr", "pa"]

MVP_NATIVE_LABEL_FORMS = [
    "farmer_registration",
    "parcel_registration",
    "crop_cycle_create",
    "activity_log",
]

MVP_NATIVE_OPTION_SETS = [
    "irrigation_sources",
    "land_units",
    "languages",
    "ownership_types",
    "seasons",
]

MVP_CORE_FIELD_IDS = {
    "farmer_registration": {
        "display_name",
        "mobile_number",
        "village_name_manual",
        "pin_code",
        "primary_crop_code",
        "language_preference",
    },
    "parcel_registration": {
        "local_name",
        "village_name_manual",
        "pin_code",
        "reported_area",
        "reported_area_unit",
        "ownership_type",
        "irrigation_source",
        "current_crop_code",
    },
    "crop_cycle_create": {
        "crop_code",
        "season_code",
        "parcel_id",
        "planned_sowing_date",
        "actual_sowing_date",
    },
    "activity_log": {
        "activity_type",
        "activity_date",
        "input_name",
        "quantity",
        "quantity_unit",
        "cost_amount",
    },
}

STATE_LANGUAGE_SCENARIOS = [
    {
        "state_lgd_code": "9",
        "state_name": "UTTAR PRADESH",
        "language_code": "hi",
        "language_name": "Hindi",
        "expected_behavior": "PREFERRED_OR_EN_FALLBACK",
        "district_examples": ["Agra", "Aligarh"],
    },
    {
        "state_lgd_code": "29",
        "state_name": "KARNATAKA",
        "language_code": "kn",
        "language_name": "Kannada",
        "expected_behavior": "EN_FALLBACK_UNTIL_NATIVE_LABELS_ADDED",
        "district_examples": ["Bagalkote", "Bengaluru Urban", "Dakshina Kannada"],
    },
    {
        "state_lgd_code": "27",
        "state_name": "MAHARASHTRA",
        "language_code": "mr",
        "language_name": "Marathi",
        "expected_behavior": "EN_FALLBACK_UNTIL_NATIVE_LABELS_ADDED",
        "district_examples": ["Ahmednagar", "Akola", "Bhandara"],
    },
    {
        "state_lgd_code": "3",
        "state_name": "PUNJAB",
        "language_code": "pa",
        "language_name": "Punjabi",
        "expected_behavior": "EN_FALLBACK_UNTIL_NATIVE_LABELS_ADDED",
        "district_examples": ["Amritsar", "Bathinda", "Faridkot"],
    },
]


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


def _collect_label_maps_from_form(form_id: str, form: Any) -> list[tuple[str, dict[str, str]]]:
    payload = _model_dump(form)
    maps: list[tuple[str, dict[str, str]]] = []

    def add(path: str, value: Any) -> None:
        if isinstance(value, dict):
            maps.append((path, value))

    add(f"form.{form_id}.title", payload.get("title"))
    add(f"form.{form_id}.description", payload.get("description"))
    add(f"form.{form_id}.submit_label", payload.get("submit_label"))

    for field in payload.get("fields") or []:
        field_id = field.get("id", "<unknown>")
        add(f"form.{form_id}.field.{field_id}.label", field.get("label"))
        add(f"form.{form_id}.field.{field_id}.placeholder", field.get("placeholder"))
        add(f"form.{form_id}.field.{field_id}.hint", field.get("hint"))
        for option in field.get("options") or []:
            add(f"form.{form_id}.field.{field_id}.option.{option.get('value', '<unknown>')}.label", option.get("label"))
    return maps


def _parse_label_path(path: str) -> dict[str, str | None]:
    parts = path.split(".")
    parsed: dict[str, str | None] = {
        "source": parts[0] if parts else None,
        "form_id": None,
        "option_set": None,
        "field_id": None,
        "label_kind": parts[-1] if parts else None,
    }

    if len(parts) >= 3 and parts[0] == "form":
        parsed["form_id"] = parts[1]
        if "field" in parts:
            idx = parts.index("field")
            if len(parts) > idx + 1:
                parsed["field_id"] = parts[idx + 1]

    if len(parts) >= 3 and parts[0] == "option_set":
        parsed["option_set"] = parts[1]

    return parsed


def _is_mvp_native_label_path(path: str) -> bool:
    parsed = _parse_label_path(path)

    form_id = parsed["form_id"]
    if form_id in MVP_NATIVE_LABEL_FORMS:
        field_id = parsed["field_id"]
        if field_id is None:
            return True
        return field_id in MVP_CORE_FIELD_IDS.get(form_id, set())

    option_set = parsed["option_set"]
    if option_set in MVP_NATIVE_OPTION_SETS:
        return True

    return False


def _count_missing_by_form(paths: list[str]) -> dict[str, int]:
    counts = Counter()
    for path in paths:
        parsed = _parse_label_path(path)
        form_id = parsed["form_id"]
        option_set = parsed["option_set"]
        if form_id:
            counts[f"form.{form_id}"] += 1
        elif option_set:
            counts[f"option_set.{option_set}"] += 1
        else:
            counts["other"] += 1
    return dict(sorted(counts.items()))


def _build_translation_backlog(missing_by_language: dict[str, list[str]]) -> dict[str, Any]:
    backlog_by_language = {}
    for lang in REGIONAL_FALLBACK_LANGUAGES:
        missing_paths = missing_by_language[lang]
        mvp_paths = [path for path in missing_paths if _is_mvp_native_label_path(path)]
        backlog_by_language[lang] = {
            "missing_native_labels": len(missing_paths),
            "mvp_native_labels_missing": len(mvp_paths),
            "mvp_missing_by_form_or_option_set": _count_missing_by_form(mvp_paths),
            "mvp_samples": mvp_paths[:40],
        }

    return {
        "scope": {
            "forms": MVP_NATIVE_LABEL_FORMS,
            "option_sets": MVP_NATIVE_OPTION_SETS,
            "core_field_ids": {key: sorted(value) for key, value in sorted(MVP_CORE_FIELD_IDS.items())},
        },
        "by_language": backlog_by_language,
        "recommendation": (
            "Translate MVP native label backlog first; keep English fallback mandatory for all labels."
        ),
    }


def _collect_label_maps_from_option_set(option_set: str, payload: Any) -> list[tuple[str, dict[str, str]]]:
    value = _model_dump(payload)
    maps: list[tuple[str, dict[str, str]]] = []
    title = value.get("title")
    if isinstance(title, dict):
        maps.append((f"option_set.{option_set}.title", title))
    for option in value.get("options") or []:
        label = option.get("label")
        if isinstance(label, dict):
            maps.append((f"option_set.{option_set}.option.{option.get('value', '<unknown>')}.label", label))
    return maps


def main() -> int:
    label_maps: list[tuple[str, dict[str, str]]] = []
    form_label_counts: dict[str, int] = {}
    option_label_counts: dict[str, int] = {}

    for form_id, form in sorted(FORM_REGISTRY.items()):
        maps = _collect_label_maps_from_form(form_id, form)
        form_label_counts[form_id] = len(maps)
        label_maps.extend(maps)

    for option_set, payload in sorted(PROFILE_OPTION_REGISTRY.items()):
        maps = _collect_label_maps_from_option_set(option_set, payload)
        option_label_counts[option_set] = len(maps)
        label_maps.extend(maps)

    missing_by_language: dict[str, list[str]] = defaultdict(list)
    present_counts = Counter()
    fallback_counts = Counter()

    for path, labels in label_maps:
        for lang in TARGET_LANGUAGES:
            if labels.get(lang):
                present_counts[lang] += 1
            else:
                missing_by_language[lang].append(path)
                if lang != "en" and labels.get("en"):
                    fallback_counts[lang] += 1

    regional_native_complete = all(not missing_by_language[lang] for lang in REGIONAL_FALLBACK_LANGUAGES)
    english_complete = not missing_by_language["en"]
    hindi_key_present = present_counts["hi"] > 0
    translation_backlog = _build_translation_backlog(missing_by_language)

    payload = {
        "schema_version": "android_multilingual_form_label_audit.v1",
        "mode": "READ_ONLY_AUDIT",
        "db_writes_made": False,
        "external_calls_made": False,
        "target_languages": TARGET_LANGUAGES,
        "counts": {
            "forms": len(FORM_REGISTRY),
            "option_sets": len(PROFILE_OPTION_REGISTRY),
            "label_maps_audited": len(label_maps),
            "present_by_language": dict(present_counts),
            "missing_by_language": {lang: len(paths) for lang, paths in sorted(missing_by_language.items())},
            "fallback_to_en_available_by_language": dict(fallback_counts),
        },
        "form_label_counts": form_label_counts,
        "option_label_counts": option_label_counts,
        "state_language_scenarios": STATE_LANGUAGE_SCENARIOS,
        "mvp_native_translation_backlog": translation_backlog,
        "readiness": {
            "english_fallback_complete": english_complete,
            "hindi_label_keys_present": hindi_key_present,
            "regional_native_labels_complete": regional_native_complete,
            "android_must_use_en_fallback_for_kn_mr_pa": not regional_native_complete,
            "ready_for_multilingual_fallback_maestro": english_complete and not regional_native_complete,
            "ready_for_mvp_native_translation_planning": english_complete and hindi_key_present,
            "safe_read_only": True,
        },
        "samples": {
            "missing_native_label_paths": {
                lang: missing_by_language[lang][:20]
                for lang in REGIONAL_FALLBACK_LANGUAGES
            },
            "missing_english_label_paths": missing_by_language["en"][:20],
        },
        "android_contract": {
            "label_resolution": "labels[currentLanguageCode] ?: labels['en']",
            "do_not_hardcode_translations": True,
            "do_not_translate_advisories_on_device": True,
            "regional_languages_to_exercise_next": ["kn", "mr", "pa"],
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if english_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())