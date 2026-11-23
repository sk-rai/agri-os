#!/usr/bin/env python3
"""Focused behavioral regressions for lossless sync ingress.

This script is intentionally standalone and database-free. It is source for a
separately approved host run; adding it does not authorize executing it.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

assert "app.core.database" not in sys.modules
from app.modules.sync.ingress import (  # noqa: E402
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_JSON_NUMBER_CHARS,
    MAX_JSON_STRING_BYTES,
    MAX_SYNC_BODY_BYTES,
    preflight_sync_request,
)
from app.modules.sync.schemas import SyncEventPayload  # noqa: E402
assert "app.core.database" not in sys.modules


EVENT_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000101"))
ACTIVITY_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000102"))
FARMER_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000103"))
CYCLE_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000104"))


class FakeRequest:
    def __init__(
        self,
        chunks: list[bytes],
        content_length: int | None = None,
    ) -> None:
        headers: list[tuple[bytes, bytes]] = []
        if content_length is not None:
            headers.append((b"content-length", str(content_length).encode("ascii")))
        self.scope = {"headers": headers}
        self._chunks = chunks

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


def event_json(
    *,
    event_id: str = EVENT_ID,
    entity_type: str = "farmer",
    operation: str = "CREATE",
    version_token: str | None = "1",
    payload: str = "{}",
    entity_id: str | None = None,
    metadata: str = "{}",
) -> str:
    return (
        '{"event_id":' + json.dumps(event_id)
        + ',"entity_type":' + json.dumps(entity_type)
        + (',"entity_id":' + json.dumps(entity_id) if entity_id else "")
        + ',"operation":' + json.dumps(operation)
        + ',"payload":' + payload
        + (',"version":' + version_token if version_token is not None else "")
        + ',"metadata":' + metadata
        + "}"
    )


def activity_event_json(
    *,
    event_id: str = EVENT_ID,
    entity_type: str = "crop_activity",
    operation: str = "CREATE",
    version_token: str | None = "1",
    metadata: str = "{}",
    payload_overrides: dict[str, Any] | None = None,
) -> str:
    payload = {
        "activity_id": ACTIVITY_ID,
        "farmer_id": FARMER_ID,
        "crop_cycle_id": CYCLE_ID,
        "activity_type": "IRRIGATION",
        "activity_date": "2026-11-22",
        "quantity": "1.25",
        "cost_amount": "10.00",
    }
    payload.update(payload_overrides or {})
    return event_json(
        event_id=event_id,
        entity_type=entity_type,
        operation=operation,
        version_token=version_token,
        payload=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        entity_id=ACTIVITY_ID,
        metadata=metadata,
    )


async def accepted(raw: bytes) -> list[Any]:
    request = FakeRequest([raw[:7], raw[7:]], content_length=len(raw))
    return await preflight_sync_request(request, SyncEventPayload.model_validate)


async def rejected(
    raw: bytes,
    *,
    code: str,
    chunks: list[bytes] | None = None,
    content_length: int | None = None,
) -> None:
    request = FakeRequest(chunks or [raw], content_length=content_length)
    try:
        await preflight_sync_request(request, SyncEventPayload.model_validate)
    except HTTPException as exc:
        assert exc.detail["error"] == code, exc.detail
    else:
        raise AssertionError(f"expected rejection: {code}")


async def main() -> None:
    single = ("{\"events\":[" + event_json() + "]}").encode()
    assert len(await accepted(single)) == 1

    duplicate = ("{\"events\":[" + event_json() + "," + event_json() + "]}").encode()
    assert len(await accepted(duplicate)) == 1

    for payloads in (
        ('{\"measurement\":1.0}', '{\"measurement\":1.0000000000000001}'),
        ('{\"measurement\":1.0000000000000001}', '{\"measurement\":1.0}'),
        ('{\"measurement\":1}', '{\"measurement\":1e0}'),
        ('{\"measurement\":1e0}', '{\"measurement\":1}'),
    ):
        mixed = (
            "{\"events\":["
            + event_json(payload=payloads[0])
            + ","
            + event_json(payload=payloads[1])
            + "]}"
        ).encode()
        await rejected(mixed, code="DUPLICATE_EVENT_ID_CONFLICT")

    for version_token in ("1.0", "1e0"):
        invalid_version = (
            "{\"events\":[" + event_json(version_token=version_token) + "]}"
        ).encode()
        await rejected(invalid_version, code="SYNC_ENVELOPE_INVALID")

    for versions in (("1", "1.0"), ("1.0", "1")):
        mixed_validity = (
            "{\"events\":["
            + event_json(version_token=versions[0])
            + ","
            + event_json(version_token=versions[1])
            + "]}"
        ).encode()
        await rejected(mixed_validity, code="SYNC_ENVELOPE_INVALID")

    conflict = (
        "{\"events\":["
        + event_json(payload='{\"name\":\"one\"}')
        + ","
        + event_json(payload='{\"name\":\"two\"}')
        + "]}"
    ).encode()
    await rejected(conflict, code="DUPLICATE_EVENT_ID_CONFLICT")

    for alias in ("crop_activity", "cropactivity"):
        update = ("{\"events\":[" + activity_event_json(entity_type=alias, operation="UPDATE") + "]}").encode()
        await rejected(update, code="ACTIVITY_OPERATION_UNSUPPORTED")

        delete = ("{\"events\":[" + activity_event_json(entity_type=alias, operation="DELETE") + "]}").encode()
        await rejected(delete, code="ACTIVITY_OPERATION_UNSUPPORTED")

        create = ("{\"events\":[" + activity_event_json(entity_type=alias) + "]}").encode()
        assert len(await accepted(create)) == 1

    for spelling in (" crop_activity", "crop_activity ", "crop-activity", "crop activity"):
        value = ("{\"events\":[" + event_json(entity_type=spelling) + "]}").encode()
        await rejected(value, code="SYNC_ENVELOPE_INVALID")

    numeric_activity = (
        "{\"events\":["
        + activity_event_json(payload_overrides={"quantity": 1.0})
        + "]}"
    ).encode()
    await rejected(numeric_activity, code="ACTIVITY_PAYLOAD_INVALID")

    for operation in ("[]", "{}"):
        malformed_operation = (
            "{\"events\":["
            + activity_event_json(operation=operation)
            + "]}"
        ).encode()
        # event_json quotes strings, so substitute the raw malformed value.
        malformed_operation = malformed_operation.replace(
            json.dumps(operation).encode(), operation.encode(), 1
        )
        await rejected(malformed_operation, code="SYNC_ENVELOPE_INVALID")

    for invalid_version in ("0", "-1", "true", "false", '"1"', "1.0", "1e0"):
        invalid = (
            "{\"events\":["
            + activity_event_json(version_token=invalid_version)
            + "]}"
        ).encode()
        await rejected(invalid, code="SYNC_ENVELOPE_INVALID")

        ordinary = event_json(event_id=str(uuid.uuid4()))
        for ordered in (
            [activity_event_json(version_token=invalid_version), ordinary],
            [ordinary, activity_event_json(version_token=invalid_version)],
        ):
            mixed = ("{\"events\":[" + ",".join(ordered) + "]}").encode()
            await rejected(mixed, code="SYNC_ENVELOPE_INVALID")

        valid_duplicate = activity_event_json()
        invalid_duplicate = activity_event_json(version_token=invalid_version)
        for ordered in (
            [invalid_duplicate, valid_duplicate],
            [valid_duplicate, invalid_duplicate],
        ):
            duplicate_group = (
                "{\"events\":[" + ",".join(ordered) + "]}"
            ).encode()
            await rejected(duplicate_group, code="SYNC_ENVELOPE_INVALID")

    omitted_version = (
        "{\"events\":[" + activity_event_json(version_token=None) + "]}"
    ).encode()
    omitted = await accepted(omitted_version)
    assert omitted[0].validated.version == 1

    for value in ("01", "1e1", "+1", "-0", "-0.0", "-0.00", "1.", ".5"):
        noncanonical_decimal = (
            "{\"events\":["
            + activity_event_json(payload_overrides={"quantity": value})
            + "]}"
        ).encode()
        await rejected(noncanonical_decimal, code="ACTIVITY_PAYLOAD_INVALID")

    for overrides in (
        {"quantity": "0"},
        {"quantity": "0.0"},
        {"gps_lng": "-0.1"},
    ):
        accepted_decimal = (
            "{\"events\":["
            + activity_event_json(payload_overrides=overrides)
            + "]}"
        ).encode()
        assert len(await accepted(accepted_decimal)) == 1

    malformed_business = activity_event_json(
        payload_overrides={"activity_type": "NOT_REAL"}
    )
    valid_business = activity_event_json()
    for ordered in (
        [malformed_business, valid_business],
        [valid_business, malformed_business],
    ):
        invalid_occurrence = (
            "{\"events\":[" + ",".join(ordered) + "]}"
        ).encode()
        await rejected(invalid_occurrence, code="ACTIVITY_PAYLOAD_INVALID")

    composed = (
        "{\"events\":["
        + activity_event_json(metadata='{"label":"é"}')
        + "]}"
    ).encode("utf-8")
    decomposed = (
        "{\"events\":["
        + activity_event_json(metadata='{"label":"é"}')
        + "]}"
    ).encode("utf-8")
    composed_event = (await accepted(composed))[0]
    decomposed_event = (await accepted(decomposed))[0]
    assert composed_event.canonical_envelope != decomposed_event.canonical_envelope

    for writer_type in (
        "crop_cycle",
        "cropcycle",
        "crop_stage",
        "cropstage",
        "crop_stage_instance",
        "cropstageinstance",
    ):
        writer = event_json(
            event_id=str(uuid.uuid4()),
            entity_type=writer_type,
            payload=json.dumps({"crop_cycle_id": CYCLE_ID}),
        )
        for ordered in ([activity_event_json(), writer], [writer, activity_event_json()]):
            mixed_cycle_writer = (
                "{\"events\":[" + ",".join(ordered) + "]}"
            ).encode()
            await rejected(mixed_cycle_writer, code="CYCLE_LOCK_PLAN_INVALID")

    unknown_field = (
        "{\"events\":["
        + event_json()[:-1]
        + ',\"unexpected\":true}]}'
    ).encode()
    await rejected(unknown_field, code="SYNC_ENVELOPE_INVALID")

    for surrogate in (
        b'{"events":[{"\\uD800":1}]}',
        b'{"events":[{"event_id":"\\uD800"}]}',
    ):
        await rejected(surrogate, code="SYNC_JSON_INVALID")

    excessive_depth = ("[" * (MAX_JSON_DEPTH + 1) + "]" * (MAX_JSON_DEPTH + 1)).encode()
    await rejected(excessive_depth, code="SYNC_JSON_INVALID")
    excessive_nodes = ("[" + ",".join("null" for _ in range(MAX_JSON_NODES)) + "]").encode()
    await rejected(excessive_nodes, code="SYNC_JSON_INVALID")
    excessive_string = ('"' + ("a" * (MAX_JSON_STRING_BYTES + 1)) + '"').encode()
    await rejected(excessive_string, code="SYNC_JSON_INVALID")
    excessive_number = ("1" * (MAX_JSON_NUMBER_CHARS + 1)).encode()
    await rejected(excessive_number, code="SYNC_JSON_INVALID")

    exact_cap = single + (b" " * (MAX_SYNC_BODY_BYTES - len(single)))
    assert len(exact_cap) == MAX_SYNC_BODY_BYTES
    assert len(await accepted(exact_cap)) == 1

    oversized = b"{" + (b" " * MAX_SYNC_BODY_BYTES)
    await rejected(
        oversized,
        code="SYNC_BODY_TOO_LARGE",
        chunks=[oversized[:19], oversized[19:]],
    )
    await rejected(
        oversized,
        code="SYNC_BODY_TOO_LARGE",
        chunks=[oversized],
        content_length=1,
    )
    await rejected(
        b"{}",
        code="SYNC_BODY_TOO_LARGE",
        content_length=MAX_SYNC_BODY_BYTES + 1,
    )

    await rejected(b"\xef\xbb\xbf{}", code="SYNC_UTF8_INVALID")
    await rejected(b"\xff", code="SYNC_UTF8_INVALID")
    print("SYNC_LOSSLESS_INGRESS_OK")


if __name__ == "__main__":
    asyncio.run(main())
