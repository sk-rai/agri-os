"""Runtime localization helpers for Android/web-facing backend-driven payloads."""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable, Optional
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.master_data.models import LocalizedContentKey, LocalizedContentOverride


PUBLISHED_STATUSES = {"PUBLISHED", "APPROVED", "ACTIVE"}


def _normalize_language(value: str) -> str:
    return str(value or "").strip().lower()


def _published_override_map(
    db: Session,
    *,
    tenant_id: str,
    project_id: Optional[uuid.UUID],
    content_keys: Iterable[str],
) -> dict[str, dict[str, str]]:
    keys = sorted({str(key) for key in content_keys if key})
    if not keys:
        return {}

    query = (
        db.query(
            LocalizedContentKey.content_key,
            LocalizedContentOverride.language_code,
            LocalizedContentOverride.override_text,
            LocalizedContentOverride.project_id,
        )
        .join(LocalizedContentOverride, LocalizedContentOverride.content_key_id == LocalizedContentKey.id)
        .filter(
            LocalizedContentKey.content_key.in_(keys),
            LocalizedContentKey.is_active.is_(True),
            LocalizedContentOverride.tenant_id == tenant_id,
            LocalizedContentOverride.is_active.is_(True),
            LocalizedContentOverride.review_status.in_(sorted(PUBLISHED_STATUSES)),
        )
    )
    if project_id:
        query = query.filter(or_(LocalizedContentOverride.project_id == project_id, LocalizedContentOverride.project_id.is_(None)))
    else:
        query = query.filter(LocalizedContentOverride.project_id.is_(None))

    rows = query.order_by(
        LocalizedContentKey.content_key,
        LocalizedContentOverride.language_code,
        LocalizedContentOverride.project_id.is_(None),
        LocalizedContentOverride.updated_at.desc(),
    ).all()

    resolved: dict[str, dict[str, str]] = {}
    seen: set[tuple[str, str]] = set()
    for content_key, language_code, override_text, _project_id in rows:
        lang = _normalize_language(language_code)
        pair = (content_key, lang)
        if pair in seen:
            continue
        if not lang or not str(override_text or "").strip():
            continue
        resolved.setdefault(content_key, {})[lang] = override_text
        seen.add(pair)
    return resolved


def _overlay_label_map(payload: dict, field_name: str, content_key: str, overrides: dict[str, dict[str, str]], applied: set[str]) -> None:
    labels = payload.get(field_name)
    additions = overrides.get(content_key) or {}
    if not isinstance(labels, dict) or not additions:
        return
    for language_code, text in additions.items():
        labels[language_code] = text
        applied.add(content_key)


def localize_form_payload(
    db: Session,
    form_payload: dict,
    *,
    tenant_id: str,
    project_id: Optional[uuid.UUID] = None,
) -> dict:
    payload = deepcopy(form_payload)
    form_id = payload.get("form_id")
    if not form_id:
        return payload

    content_keys: list[str] = []
    for kind in ("title", "description", "submit_label"):
        if isinstance(payload.get(kind), dict):
            content_keys.append(f"profile_form.{form_id}.{kind}")

    for field in payload.get("fields") or []:
        if not isinstance(field, dict) or not field.get("id"):
            continue
        field_id = field["id"]
        for kind in ("label", "placeholder", "hint"):
            if isinstance(field.get(kind), dict):
                content_keys.append(f"profile_form.{form_id}.field.{field_id}.{kind}")
        for option in field.get("options") or []:
            if isinstance(option, dict) and option.get("value") and isinstance(option.get("label"), dict):
                content_keys.append(f"profile_form.{form_id}.field.{field_id}.option.{option['value']}.label")

    overrides = _published_override_map(db, tenant_id=tenant_id, project_id=project_id, content_keys=content_keys)
    applied: set[str] = set()

    for kind in ("title", "description", "submit_label"):
        _overlay_label_map(payload, kind, f"profile_form.{form_id}.{kind}", overrides, applied)

    for field in payload.get("fields") or []:
        if not isinstance(field, dict) or not field.get("id"):
            continue
        field_id = field["id"]
        for kind in ("label", "placeholder", "hint"):
            _overlay_label_map(field, kind, f"profile_form.{form_id}.field.{field_id}.{kind}", overrides, applied)
        for option in field.get("options") or []:
            if isinstance(option, dict) and option.get("value"):
                _overlay_label_map(option, "label", f"profile_form.{form_id}.field.{field_id}.option.{option['value']}.label", overrides, applied)

    payload.setdefault("metadata", {})
    if isinstance(payload["metadata"], dict):
        payload["metadata"]["localization_overrides_applied"] = len(applied)
    return payload


def localize_option_set_payload(
    db: Session,
    option_payload: dict,
    *,
    tenant_id: str,
    project_id: Optional[uuid.UUID] = None,
) -> dict:
    payload = deepcopy(option_payload)
    option_set = payload.get("option_set")
    if not option_set:
        return payload

    content_keys: list[str] = []
    if isinstance(payload.get("title"), dict):
        content_keys.append(f"profile_option_set.{option_set}.title")
    for option in payload.get("options") or []:
        if isinstance(option, dict) and option.get("value") and isinstance(option.get("label"), dict):
            content_keys.append(f"profile_option_set.{option_set}.option.{option['value']}.label")

    overrides = _published_override_map(db, tenant_id=tenant_id, project_id=project_id, content_keys=content_keys)
    applied: set[str] = set()

    _overlay_label_map(payload, "title", f"profile_option_set.{option_set}.title", overrides, applied)
    for option in payload.get("options") or []:
        if isinstance(option, dict) and option.get("value"):
            _overlay_label_map(option, "label", f"profile_option_set.{option_set}.option.{option['value']}.label", overrides, applied)

    metadata = payload.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["localization_overrides_applied"] = len(applied)
    return payload
