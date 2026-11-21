"""Canonical crop-activity CREATE command structures.

This module is dependency-free and is not wired to either HTTP or sync
materialization. It defines the immutable v1 request intent used by both future
entry points.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


ACTIVITY_INTENT_VERSION = "crop_activity_intent.v1"
ACTIVITY_RESULT_VERSION = "crop_activity_result.v1"
ACTIVITY_TYPES = frozenset(
    {"FERTILIZER", "PESTICIDE", "IRRIGATION", "LABOR", "MACHINERY", "HARVEST", "SEED", "OTHER"}
)


@dataclass(frozen=True)
class QueuedActivityOrigin:
    event_id: UUID
    entity_type: str
    operation: str
    client_version: int
    dependency_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class CropActivityCreateCommand:
    tenant_id: str
    actor_id: UUID
    farmer_id: UUID
    crop_cycle_id: UUID
    activity_id: UUID
    requested_stage_id: UUID | None
    requested_stage_code: str | None
    activity_type: str
    activity_date: date
    input_code: str | None = None
    input_name: str | None = None
    input_rule_id: UUID | None = None
    product_id: UUID | None = None
    product_code: str | None = None
    package_id: UUID | None = None
    package_sku: str | None = None
    quantity: Decimal | None = None
    quantity_unit: str | None = None
    area_applied: Decimal | None = None
    area_unit: str | None = None
    recommended_quantity: Decimal | None = None
    recommended_quantity_unit: str | None = None
    actual_quantity: Decimal | None = None
    actual_quantity_unit: str | None = None
    dosage_variance_reason: str | None = None
    cost_amount: Decimal | None = None
    cost_currency: str | None = None
    gps_lat: Decimal | None = None
    gps_lng: Decimal | None = None
    irrigation_source: str | None = None
    duration_hours: Decimal | None = None
    notes: str | None = None
    queued_origin: QueuedActivityOrigin | None = None


@dataclass(frozen=True)
class CanonicalActivityIntent:
    version: str
    canonical_text: str
    sha256: str


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("ACTIVITY_INTENT_TEXT_INVALID")
    normalized = unicodedata.normalize("NFC", value)
    if "\x00" in normalized:
        raise ValueError("ACTIVITY_INTENT_TEXT_INVALID")
    return normalized


def _code(value: str | None) -> str | None:
    normalized = _text(value)
    if normalized is None:
        return None
    if not normalized or normalized != normalized.upper():
        raise ValueError("ACTIVITY_INTENT_CODE_INVALID")
    return normalized


def _normalize_code_input(value: str | None) -> str | None:
    normalized = _text(value)
    if normalized is None:
        return None
    normalized = unicodedata.normalize(
        "NFC",
        normalized.strip().upper().replace(" ", "_"),
    )
    return normalized or None


def _bounded(value: str | None, maximum: int, code: str) -> str | None:
    if value is not None and len(value) > maximum:
        raise ValueError(code)
    return value


def normalize_activity_command(
    command: CropActivityCreateCommand,
) -> CropActivityCreateCommand:
    """Return the single normalized command used for hash and persistence."""

    if not isinstance(command, CropActivityCreateCommand):
        raise ValueError("ACTIVITY_INTENT_COMMAND_INVALID")
    queued_origin = command.queued_origin
    if queued_origin is not None:
        queued_origin = replace(
            queued_origin,
            entity_type=_text(queued_origin.entity_type),
            operation=_normalize_code_input(queued_origin.operation),
        )
    normalized = replace(
        command,
        tenant_id=_bounded(_text(command.tenant_id), 50, "ACTIVITY_TENANT_LENGTH"),
        requested_stage_code=_bounded(
            _normalize_code_input(command.requested_stage_code),
            50,
            "ACTIVITY_STAGE_CODE_LENGTH",
        ),
        activity_type=_bounded(
            _normalize_code_input(command.activity_type),
            30,
            "ACTIVITY_TYPE_LENGTH",
        ),
        input_code=_bounded(
            _normalize_code_input(command.input_code),
            50,
            "ACTIVITY_INPUT_CODE_LENGTH",
        ),
        input_name=_bounded(_text(command.input_name), 200, "ACTIVITY_INPUT_NAME_LENGTH"),
        product_code=_bounded(
            _normalize_code_input(command.product_code),
            80,
            "ACTIVITY_PRODUCT_CODE_LENGTH",
        ),
        package_sku=_bounded(
            _normalize_code_input(command.package_sku),
            100,
            "ACTIVITY_PACKAGE_SKU_LENGTH",
        ),
        quantity_unit=_bounded(
            _normalize_code_input(command.quantity_unit),
            20,
            "ACTIVITY_QUANTITY_UNIT_LENGTH",
        ),
        area_unit=_bounded(
            _normalize_code_input(command.area_unit),
            20,
            "ACTIVITY_AREA_UNIT_LENGTH",
        ),
        recommended_quantity_unit=_bounded(
            _normalize_code_input(command.recommended_quantity_unit),
            20,
            "ACTIVITY_RECOMMENDED_UNIT_LENGTH",
        ),
        actual_quantity_unit=_bounded(
            _normalize_code_input(command.actual_quantity_unit),
            20,
            "ACTIVITY_ACTUAL_UNIT_LENGTH",
        ),
        dosage_variance_reason=_text(command.dosage_variance_reason),
        cost_currency=_bounded(
            _normalize_code_input(command.cost_currency),
            5,
            "ACTIVITY_CURRENCY_LENGTH",
        ),
        irrigation_source=_bounded(
            _normalize_code_input(command.irrigation_source),
            100,
            "ACTIVITY_IRRIGATION_SOURCE_LENGTH",
        ),
        notes=_text(command.notes),
        queued_origin=queued_origin,
    )
    if normalized.activity_type not in ACTIVITY_TYPES:
        raise ValueError("ACTIVITY_INTENT_TYPE_INVALID")
    return normalized


def _uuid(value: UUID | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, UUID):
        raise ValueError("ACTIVITY_INTENT_UUID_INVALID")
    return str(value)


def _decimal(value: Decimal | None, precision: int, scale: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or isinstance(value, bool) or not value.is_finite():
        raise ValueError("ACTIVITY_INTENT_DECIMAL_INVALID")

    parts = value.as_tuple()
    digits = list(parts.digits)
    exponent = parts.exponent
    if not isinstance(exponent, int):
        raise ValueError("ACTIVITY_INTENT_DECIMAL_INVALID")
    if not digits or all(digit == 0 for digit in digits):
        return "0"

    while digits[-1] == 0:
        digits.pop()
        exponent += 1

    fractional_digits = max(-exponent, 0)
    integer_digits = max(len(digits) + exponent, 0)
    if fractional_digits > scale:
        raise ValueError("ACTIVITY_INTENT_DECIMAL_SCALE")
    if integer_digits > precision - scale:
        raise ValueError("ACTIVITY_INTENT_DECIMAL_PRECISION")

    coefficient = "".join(str(digit) for digit in digits)
    point = len(coefficient) + exponent
    if point <= 0:
        rendered = "0." + ("0" * -point) + coefficient
    elif point >= len(coefficient):
        rendered = coefficient + ("0" * (point - len(coefficient)))
    else:
        rendered = coefficient[:point] + "." + coefficient[point:]
    return ("-" if parts.sign else "") + rendered


def _date(value: date) -> str:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError("ACTIVITY_INTENT_DATE_INVALID")
    return value.isoformat()


def _queued(origin: QueuedActivityOrigin | None) -> dict[str, Any]:
    if origin is None:
        return {
            "origin_kind": "DIRECT",
            "event_id": None,
            "entity_type": None,
            "operation": None,
            "client_version": None,
            "dependency_ids": None,
        }
    entity_type = _text(origin.entity_type)
    if entity_type is None or entity_type.lower() not in {
        "crop_activity",
        "cropactivity",
    }:
        raise ValueError("ACTIVITY_INTENT_ENTITY_TYPE_INVALID")
    if origin.operation != "CREATE":
        raise ValueError("ACTIVITY_INTENT_OPERATION_INVALID")
    if (
        not isinstance(origin.client_version, int)
        or isinstance(origin.client_version, bool)
        or origin.client_version < 1
    ):
        raise ValueError("ACTIVITY_INTENT_CLIENT_VERSION_INVALID")
    return {
        "origin_kind": "SYNC",
        "event_id": _uuid(origin.event_id),
        "entity_type": entity_type,
        "operation": origin.operation,
        "client_version": origin.client_version,
        "dependency_ids": [_uuid(value) for value in origin.dependency_ids],
    }


def canonicalize_activity_intent(
    command: CropActivityCreateCommand,
) -> CanonicalActivityIntent:
    command = normalize_activity_command(command)

    payload: dict[str, Any] = {
        "intent_version": ACTIVITY_INTENT_VERSION,
        "tenant_id": _text(command.tenant_id),
        "actor_id": _uuid(command.actor_id),
        "farmer_id": _uuid(command.farmer_id),
        "crop_cycle_id": _uuid(command.crop_cycle_id),
        "activity_id": _uuid(command.activity_id),
        "requested_stage_id": _uuid(command.requested_stage_id),
        "requested_stage_code": _code(command.requested_stage_code),
        "activity_type": _code(command.activity_type),
        "activity_date": _date(command.activity_date),
        "input_code": _code(command.input_code),
        "input_name": _text(command.input_name),
        "input_rule_id": _uuid(command.input_rule_id),
        "product_id": _uuid(command.product_id),
        "product_code": _code(command.product_code),
        "package_id": _uuid(command.package_id),
        "package_sku": _code(command.package_sku),
        "quantity": _decimal(command.quantity, 10, 2),
        "quantity_unit": _code(command.quantity_unit),
        "area_applied": _decimal(command.area_applied, 10, 2),
        "area_unit": _code(command.area_unit),
        "recommended_quantity": _decimal(command.recommended_quantity, 12, 3),
        "recommended_quantity_unit": _code(command.recommended_quantity_unit),
        "actual_quantity": _decimal(command.actual_quantity, 12, 3),
        "actual_quantity_unit": _code(command.actual_quantity_unit),
        "dosage_variance_reason": _text(command.dosage_variance_reason),
        "cost_amount": _decimal(command.cost_amount, 12, 2),
        "cost_currency": _code(command.cost_currency),
        "gps_lat": _decimal(command.gps_lat, 10, 8),
        "gps_lng": _decimal(command.gps_lng, 11, 8),
        "irrigation_source": _code(command.irrigation_source),
        "duration_hours": _decimal(command.duration_hours, 10, 2),
        "notes": _text(command.notes),
    }
    payload.update(_queued(command.queued_origin))
    canonical_text = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    return CanonicalActivityIntent(
        version=ACTIVITY_INTENT_VERSION,
        canonical_text=canonical_text,
        sha256=digest,
    )
