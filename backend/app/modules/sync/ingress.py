"""Bounded, lossless sync-request ingress and batch preflight.

This module performs no authorization or database work. It preserves JSON
presence and numeric tokens until every occurrence has been validated and the
batch has been checked for duplicate event identities.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Generic, TypeVar

from fastapi import HTTPException, Request
from pydantic import ValidationError


MAX_SYNC_BODY_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 100_000
MAX_JSON_STRING_BYTES = 262_144
MAX_JSON_NUMBER_CHARS = 1_024
MAX_SYNC_EVENTS = 100

_ACTIVITY_TYPES = frozenset({"crop_activity", "cropactivity"})
_REJECTED_ACTIVITY_ALIASES = frozenset({"crop-activity", "crop activity"})
_ACTIVITY_DECIMAL_FIELDS = frozenset(
    {
        "quantity",
        "area_applied",
        "areaApplied",
        "recommended_quantity",
        "recommendedQuantity",
        "actual_quantity",
        "actualQuantity",
        "cost_amount",
        "costAmount",
        "gps_lat",
        "gpsLat",
        "gps_lng",
        "gpsLng",
        "latitude",
        "longitude",
        "duration_hours",
        "durationHours",
    }
)


class _IngressError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.public_message = message


@dataclass(frozen=True)
class LosslessNumber:
    token: str
    value: Decimal


T = TypeVar("T")


@dataclass(frozen=True)
class PreflightEvent(Generic[T]):
    validated: T
    lossless_envelope: dict[str, Any]


def _public_error(error: _IngressError) -> HTTPException:
    return HTTPException(
        status_code=error.status,
        detail={"error": error.code, "message": error.public_message},
    )


def _content_length(request: Request) -> int | None:
    values = [
        value
        for name, value in request.scope.get("headers", [])
        if name.lower() == b"content-length"
    ]
    if not values:
        return None
    if len(values) != 1:
        raise _IngressError(400, "SYNC_BODY_INVALID", "Conflicting Content-Length headers.")
    try:
        text = values[0].decode("ascii")
        if not text or not text.isdigit():
            raise ValueError
        length = int(text)
    except (UnicodeDecodeError, ValueError):
        raise _IngressError(400, "SYNC_BODY_INVALID", "Invalid Content-Length header.")
    if length > MAX_SYNC_BODY_BYTES:
        raise _IngressError(413, "SYNC_BODY_TOO_LARGE", "Sync request body exceeds the limit.")
    return length


async def _read_bounded_body(request: Request) -> bytes:
    _content_length(request)
    total = 0
    retained = bytearray()
    async for chunk in request.stream():
        size = len(chunk)
        total += size
        remaining = MAX_SYNC_BODY_BYTES + 1 - len(retained)
        if remaining > 0:
            retained.extend(chunk[:remaining])
        if total > MAX_SYNC_BODY_BYTES:
            raise _IngressError(413, "SYNC_BODY_TOO_LARGE", "Sync request body exceeds the limit.")
    return bytes(retained)


def _number(token: str) -> LosslessNumber:
    try:
        value = Decimal(token)
    except InvalidOperation:
        raise _IngressError(400, "SYNC_JSON_INVALID", "Invalid JSON number.")
    if not value.is_finite():
        raise _IngressError(400, "SYNC_JSON_INVALID", "Invalid JSON number.")
    return LosslessNumber(token=token, value=value)


def _constant(_token: str) -> Any:
    raise _IngressError(400, "SYNC_JSON_INVALID", "Invalid JSON number.")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _IngressError(400, "SYNC_JSON_INVALID", "Duplicate JSON object member.")
        result[key] = value
    return result


def _scan_string(text: str, start: int) -> int:
    """Scan one JSON string without constructing its decoded value."""

    index = start + 1
    decoded_bytes = 0
    while index < len(text):
        character = text[index]
        if character == '"':
            return index + 1
        if ord(character) < 0x20:
            raise _IngressError(400, "SYNC_JSON_INVALID", "Malformed sync JSON.")
        if character != "\\":
            decoded_bytes += len(character.encode("utf-8"))
            index += 1
        else:
            index += 1
            if index >= len(text) or text[index] not in '"\\/bfnrtu':
                raise _IngressError(400, "SYNC_JSON_INVALID", "Malformed sync JSON.")
            escape = text[index]
            if escape != "u":
                decoded_bytes += 1
                index += 1
            else:
                digits = text[index + 1:index + 5]
                if len(digits) != 4:
                    raise _IngressError(400, "SYNC_JSON_INVALID", "Malformed sync JSON.")
                try:
                    codepoint = int(digits, 16)
                except ValueError:
                    raise _IngressError(400, "SYNC_JSON_INVALID", "Malformed sync JSON.")
                index += 5
                if 0xD800 <= codepoint <= 0xDBFF:
                    if text[index:index + 2] != "\\u":
                        raise _IngressError(400, "SYNC_JSON_INVALID", "Invalid Unicode surrogate.")
                    low_digits = text[index + 2:index + 6]
                    try:
                        low = int(low_digits, 16)
                    except (TypeError, ValueError):
                        raise _IngressError(400, "SYNC_JSON_INVALID", "Invalid Unicode surrogate.")
                    if len(low_digits) != 4 or not 0xDC00 <= low <= 0xDFFF:
                        raise _IngressError(400, "SYNC_JSON_INVALID", "Invalid Unicode surrogate.")
                    codepoint = 0x10000 + ((codepoint - 0xD800) << 10) + (low - 0xDC00)
                    index += 6
                elif 0xDC00 <= codepoint <= 0xDFFF:
                    raise _IngressError(400, "SYNC_JSON_INVALID", "Invalid Unicode surrogate.")
                decoded_bytes += len(chr(codepoint).encode("utf-8"))
        if decoded_bytes > MAX_JSON_STRING_BYTES:
            raise _IngressError(400, "SYNC_JSON_INVALID", "JSON string exceeds the limit.")
    raise _IngressError(400, "SYNC_JSON_INVALID", "Malformed sync JSON.")


def _scan_json_limits(text: str) -> None:
    """Enforce allocation limits before ``json.loads`` builds the tree."""

    index = 0
    depth = 0
    nodes = 0
    length = len(text)

    def add_node() -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise _IngressError(400, "SYNC_JSON_INVALID", "JSON value count exceeds the limit.")

    while index < length:
        character = text[index]
        if character in " \t\r\n,:":
            index += 1
        elif character == '"':
            add_node()  # Includes member names, making the bound conservative.
            index = _scan_string(text, index)
        elif character in "[{":
            add_node()
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise _IngressError(400, "SYNC_JSON_INVALID", "JSON nesting exceeds the limit.")
            index += 1
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise _IngressError(400, "SYNC_JSON_INVALID", "Malformed sync JSON.")
            index += 1
        elif character == "-" or character.isdigit():
            add_node()
            end = index + 1
            while end < length and text[end] in "0123456789+-.eE":
                end += 1
            if end - index > MAX_JSON_NUMBER_CHARS:
                raise _IngressError(400, "SYNC_JSON_INVALID", "JSON number exceeds the limit.")
            index = end
        elif character in "tfn":
            add_node()
            end = index + 1
            while end < length and text[end].isalpha():
                end += 1
            index = end
        else:
            index += 1  # ``json.loads`` supplies the fixed syntax rejection.


def _parse_lossless(body: bytes) -> dict[str, Any]:
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise _IngressError(400, "SYNC_UTF8_INVALID", "Sync request must be strict UTF-8.")
    if text.startswith("\ufeff"):
        raise _IngressError(400, "SYNC_UTF8_INVALID", "UTF-8 BOM is not accepted.")
    _scan_json_limits(text)
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_object,
            parse_int=_number,
            parse_float=_number,
            parse_constant=_constant,
        )
    except _IngressError:
        raise
    except (json.JSONDecodeError, RecursionError):
        raise _IngressError(400, "SYNC_JSON_INVALID", "Malformed sync JSON.")
    if not isinstance(parsed, dict) or set(parsed) != {"events"}:
        raise _IngressError(422, "SYNC_ENVELOPE_INVALID", "Expected only an events array.")
    events = parsed.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_SYNC_EVENTS:
        raise _IngressError(422, "SYNC_ENVELOPE_INVALID", "Events must contain 1 to 100 entries.")
    if any(not isinstance(event, dict) for event in events):
        raise _IngressError(422, "SYNC_ENVELOPE_INVALID", "Each event must be an object.")
    return parsed


def _runtime_value(value: Any) -> Any:
    if isinstance(value, LosslessNumber):
        token = value.token.lower()
        if "." not in token and "e" not in token:
            return int(value.value)
        converted = float(value.value)
        if not math.isfinite(converted):
            raise _IngressError(422, "SYNC_ENVELOPE_INVALID", "Numeric value is outside the supported range.")
        return converted
    if isinstance(value, dict):
        return {key: _runtime_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_runtime_value(child) for child in value]
    return value


def _event_id(event: dict[str, Any]) -> uuid.UUID:
    raw = event.get("event_id")
    if not isinstance(raw, str):
        raise _IngressError(422, "SYNC_ENVELOPE_INVALID", "event_id must be a UUID string.")
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise _IngressError(422, "SYNC_ENVELOPE_INVALID", "event_id must be a UUID string.")


def _activity_preflight(event: dict[str, Any]) -> None:
    entity_type = event.get("entity_type")
    if not isinstance(entity_type, str):
        return
    classified = entity_type.lower()
    if classified.strip() in _ACTIVITY_TYPES or classified in _REJECTED_ACTIVITY_ALIASES:
        if classified not in _ACTIVITY_TYPES:
            raise _IngressError(
                422,
                "SYNC_ENVELOPE_INVALID",
                "Unsupported activity entity type spelling.",
            )
    if classified not in _ACTIVITY_TYPES:
        return
    payload = event.get("payload")
    if isinstance(payload, dict):
        for name in _ACTIVITY_DECIMAL_FIELDS:
            value = payload.get(name)
            if value is not None and not isinstance(value, str):
                raise _IngressError(
                    422,
                    "ACTIVITY_PAYLOAD_INVALID",
                    "Queued activity decimals must use canonical strings.",
                )
    operation = event.get("operation")
    if not isinstance(operation, str):
        return  # Ordinary validation returns the fixed envelope error.
    if operation in {"UPDATE", "DELETE"}:
        raise _IngressError(
            422,
            "ACTIVITY_OPERATION_UNSUPPORTED",
            "Queued activity update and delete are not supported.",
        )
    if operation == "CREATE":
        raise _IngressError(
            422,
            "ACTIVITY_CREATE_NOT_READY",
            "Queued activity creation is not enabled.",
        )


def _token_sensitive_preflight(event: dict[str, Any]) -> None:
    """Validate token distinctions that ordinary Pydantic parsing may erase."""

    version = event.get("version")
    if isinstance(version, LosslessNumber):
        token = version.token.lower()
        if "." in token or "e" in token:
            raise _IngressError(
                422,
                "SYNC_ENVELOPE_INVALID",
                "version must use an integer JSON token.",
            )


async def preflight_sync_request(
    request: Request,
    validate_event: Callable[[dict[str, Any]], T],
) -> list[PreflightEvent[T]]:
    """Return validated logical events or raise a fixed public HTTP error."""

    try:
        parsed = _parse_lossless(await _read_bounded_body(request))
        occurrences: list[tuple[uuid.UUID, dict[str, Any], T]] = []
        for event in parsed["events"]:
            event_uuid = _event_id(event)
            _token_sensitive_preflight(event)
            _activity_preflight(event)
            try:
                validated = validate_event(_runtime_value(event))
            except ValidationError:
                raise _IngressError(
                    422,
                    "SYNC_ENVELOPE_INVALID",
                    "Sync event validation failed.",
                )
            occurrences.append((event_uuid, event, validated))

        grouped: dict[uuid.UUID, list[tuple[dict[str, Any], T]]] = {}
        for event_uuid, event, validated in occurrences:
            grouped.setdefault(event_uuid, []).append((event, validated))

        logical: list[PreflightEvent[T]] = []
        for event_uuid in dict.fromkeys(event_uuid for event_uuid, _, _ in occurrences):
            group = grouped[event_uuid]
            first_envelope, first_validated = group[0]
            if any(envelope != first_envelope for envelope, _ in group[1:]):
                raise _IngressError(
                    422,
                    "DUPLICATE_EVENT_ID_CONFLICT",
                    "Conflicting occurrences share one event identity.",
                )
            logical.append(PreflightEvent(first_validated, first_envelope))
        return logical
    except _IngressError as error:
        raise _public_error(error)
