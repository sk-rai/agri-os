#!/usr/bin/env python3
"""Database-free checks for crop activity intent canonicalization v1."""

from __future__ import annotations

import json
import sys
import unicodedata
from dataclasses import replace
from datetime import date
from decimal import Decimal, Inexact, Rounded, localcontext
from pathlib import Path
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

assert "app.core.database" not in sys.modules
from app.modules.workflow.activity_command import (  # noqa: E402
    ACTIVITY_INTENT_VERSION,
    CropActivityCreateCommand,
    QueuedActivityOrigin,
    canonicalize_activity_intent,
    normalize_activity_command,
)
assert "app.core.database" not in sys.modules


ACTOR_ID = UUID("00000000-0000-0000-0000-000000000011")
FARMER_ID = UUID("00000000-0000-0000-0000-000000000012")
CYCLE_ID = UUID("00000000-0000-0000-0000-000000000013")
ACTIVITY_ID = UUID("00000000-0000-0000-0000-000000000014")
EVENT_ID = UUID("00000000-0000-0000-0000-000000000015")
DEPENDENCY_A = UUID("00000000-0000-0000-0000-000000000016")
DEPENDENCY_B = UUID("00000000-0000-0000-0000-000000000017")

EXPECTED_DIRECT_CANONICAL = (
    '{"activity_date":"2026-11-17","activity_id":"00000000-0000-0000-0000-000000000014",'
    '"activity_type":"IRRIGATION","actor_id":"00000000-0000-0000-0000-000000000011",'
    '"actual_quantity":null,"actual_quantity_unit":null,"area_applied":null,'
    '"area_unit":null,"client_version":null,"cost_amount":"0","cost_currency":"INR",'
    '"crop_cycle_id":"00000000-0000-0000-0000-000000000013","dependency_ids":null,'
    '"dosage_variance_reason":null,"duration_hours":"0","entity_type":null,'
    '"event_id":null,"farmer_id":"00000000-0000-0000-0000-000000000012",'
    '"gps_lat":"26.8","gps_lng":"82.46","input_code":null,"input_name":"Café",'
    '"input_rule_id":null,"intent_version":"crop_activity_intent.v1",'
    '"irrigation_source":"CANAL","notes":"field note","operation":null,'
    '"origin_kind":"DIRECT","package_id":null,"package_sku":null,"product_code":null,'
    '"product_id":null,"quantity":"1","quantity_unit":"LITRE",'
    '"recommended_quantity":null,"recommended_quantity_unit":null,'
    '"requested_stage_code":"NURSERY","requested_stage_id":null,"tenant_id":"tenant-one"}'
)
EXPECTED_DIRECT_SHA256 = "b8a5a2c78b936bbdb8d1cb189918edc5b2df6f4aedf090df9325c41f10031b03"

EXPECTED_QUEUED_CANONICAL = (
    '{"activity_date":"2026-11-17","activity_id":"00000000-0000-0000-0000-000000000014",'
    '"activity_type":"IRRIGATION","actor_id":"00000000-0000-0000-0000-000000000011",'
    '"actual_quantity":null,"actual_quantity_unit":null,"area_applied":null,'
    '"area_unit":null,"client_version":1,"cost_amount":"0","cost_currency":"INR",'
    '"crop_cycle_id":"00000000-0000-0000-0000-000000000013",'
    '"dependency_ids":["00000000-0000-0000-0000-000000000016",'
    '"00000000-0000-0000-0000-000000000016","00000000-0000-0000-0000-000000000017"],'
    '"dosage_variance_reason":null,"duration_hours":"0","entity_type":"crop_activity",'
    '"event_id":"00000000-0000-0000-0000-000000000015",'
    '"farmer_id":"00000000-0000-0000-0000-000000000012","gps_lat":"26.8",'
    '"gps_lng":"82.46","input_code":null,"input_name":"Café","input_rule_id":null,'
    '"intent_version":"crop_activity_intent.v1","irrigation_source":"CANAL",'
    '"notes":"field note","operation":"CREATE","origin_kind":"SYNC","package_id":null,'
    '"package_sku":null,"product_code":null,"product_id":null,"quantity":"1",'
    '"quantity_unit":"LITRE","recommended_quantity":null,'
    '"recommended_quantity_unit":null,"requested_stage_code":"NURSERY",'
    '"requested_stage_id":null,"tenant_id":"tenant-one"}'
)
EXPECTED_QUEUED_SHA256 = "8416007b83a81a69b99df6bc95ed09ee7140da9f80901c3855f59d76b70e8fb4"


def command() -> CropActivityCreateCommand:
    return CropActivityCreateCommand(
        tenant_id="tenant-one",
        actor_id=ACTOR_ID,
        farmer_id=FARMER_ID,
        crop_cycle_id=CYCLE_ID,
        activity_id=ACTIVITY_ID,
        requested_stage_id=None,
        requested_stage_code="NURSERY",
        activity_type="IRRIGATION",
        activity_date=date(2026, 11, 17),
        input_name="Cafe\u0301",
        quantity=Decimal("1.00"),
        quantity_unit="LITRE",
        cost_amount=Decimal("0.00"),
        cost_currency="INR",
        gps_lat=Decimal("26.80000000"),
        gps_lng=Decimal("82.46000000"),
        irrigation_source="CANAL",
        duration_hours=Decimal("-0.00"),
        notes="field note",
    )


def expect_error(value: CropActivityCreateCommand, code: str) -> None:
    try:
        canonicalize_activity_intent(value)
    except ValueError as exc:
        assert str(exc) == code, exc
    else:
        raise AssertionError(f"expected {code}")


def main() -> None:
    direct = canonicalize_activity_intent(command())
    repeated = canonicalize_activity_intent(command())
    assert direct == repeated
    assert direct.version == ACTIVITY_INTENT_VERSION
    assert direct.canonical_text == EXPECTED_DIRECT_CANONICAL
    assert direct.sha256 == EXPECTED_DIRECT_SHA256
    assert direct.canonical_text.encode("utf-8").decode("utf-8") == direct.canonical_text

    parsed = json.loads(direct.canonical_text)
    assert parsed["origin_kind"] == "DIRECT"
    assert parsed["event_id"] is None
    assert parsed["dependency_ids"] is None
    assert parsed["quantity"] == "1"
    assert parsed["cost_amount"] == "0"
    assert parsed["duration_hours"] == "0"
    assert parsed["gps_lat"] == "26.8"
    assert parsed["input_name"] == unicodedata.normalize("NFC", "Cafe\u0301")
    assert '": "' not in direct.canonical_text
    assert '", "' not in direct.canonical_text
    assert "\\u00e9" not in direct.canonical_text

    queued_origin = QueuedActivityOrigin(
        event_id=EVENT_ID,
        entity_type="crop_activity",
        operation="CREATE",
        client_version=1,
        dependency_ids=(DEPENDENCY_A, DEPENDENCY_A, DEPENDENCY_B),
    )
    queued = canonicalize_activity_intent(
        replace(command(), queued_origin=queued_origin)
    )
    queued_payload = json.loads(queued.canonical_text)
    assert queued_payload["origin_kind"] == "SYNC"
    assert queued_payload["event_id"] == str(EVENT_ID)
    assert queued_payload["dependency_ids"] == [
        str(DEPENDENCY_A),
        str(DEPENDENCY_A),
        str(DEPENDENCY_B),
    ]
    assert queued.canonical_text == EXPECTED_QUEUED_CANONICAL
    assert queued.sha256 == EXPECTED_QUEUED_SHA256
    assert queued.sha256 != direct.sha256

    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        constrained = canonicalize_activity_intent(
            replace(command(), quantity=Decimal("1.2300"))
        )
    ordinary = canonicalize_activity_intent(
        replace(command(), quantity=Decimal("1.2300"))
    )
    assert constrained == ordinary
    assert json.loads(constrained.canonical_text)["quantity"] == "1.23"

    case_variants = []
    for spelling in ("CROP_ACTIVITY", "CrOpAcTiViTy", "cropactivity"):
        variant = canonicalize_activity_intent(
            replace(
                command(),
                queued_origin=replace(queued_origin, entity_type=spelling),
            )
        )
        assert json.loads(variant.canonical_text)["entity_type"] == spelling
        case_variants.append(variant)
    assert len({value.canonical_text for value in case_variants}) == 3
    assert len({value.sha256 for value in case_variants}) == 3
    assert all(value.sha256 != queued.sha256 for value in case_variants)

    reordered = canonicalize_activity_intent(
        replace(
            command(),
            queued_origin=replace(
                queued_origin,
                dependency_ids=(DEPENDENCY_B, DEPENDENCY_A, DEPENDENCY_A),
            ),
        )
    )
    deduplicated = canonicalize_activity_intent(
        replace(
            command(),
            queued_origin=replace(
                queued_origin,
                dependency_ids=(DEPENDENCY_A, DEPENDENCY_B),
            ),
        )
    )
    assert reordered.sha256 != queued.sha256
    assert deduplicated.sha256 != queued.sha256

    expect_error(replace(command(), quantity=1.0), "ACTIVITY_INTENT_DECIMAL_INVALID")
    expect_error(
        replace(command(), quantity=Decimal("1.001")),
        "ACTIVITY_INTENT_DECIMAL_SCALE",
    )
    lowercase_type = canonicalize_activity_intent(
        replace(command(), activity_type="irrigation")
    )
    assert json.loads(lowercase_type.canonical_text)["activity_type"] == "IRRIGATION"
    expect_error(
        replace(command(), activity_type="NOT_A_REAL_ACTIVITY"),
        "ACTIVITY_INTENT_TYPE_INVALID",
    )
    combining_source = "\u0390"
    normalized_once = normalize_activity_command(
        replace(command(), input_code=combining_source)
    )
    normalized_twice = normalize_activity_command(normalized_once)
    expected_code = unicodedata.normalize("NFC", combining_source.upper())
    assert normalized_once.input_code == expected_code
    assert normalized_twice == normalized_once
    assert json.loads(
        canonicalize_activity_intent(normalized_once).canonical_text
    )["input_code"] == expected_code
    expect_error(
        replace(command(), activity_date="2026-11-17"),
        "ACTIVITY_INTENT_DATE_INVALID",
    )
    expect_error(
        replace(
            command(),
            queued_origin=replace(queued_origin, operation="UPDATE"),
        ),
        "ACTIVITY_INTENT_OPERATION_INVALID",
    )
    print("CROP_ACTIVITY_INTENT_CANONICALIZATION_OK")


if __name__ == "__main__":
    main()
