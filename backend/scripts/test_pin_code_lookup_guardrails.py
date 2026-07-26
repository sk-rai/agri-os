#!/usr/bin/env python3
"""Regression checks for Android PIN-code lookup guardrails."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def check(condition, label, detail=None):
    if condition:
        print(f"  PASS {label}")
        if detail is not None:
            print(f"       {detail}")
        return
    print(f"  FAIL {label}")
    if detail is not None:
        print(f"       {detail}")
    raise AssertionError(label)


def get(pin: str):
    response = client.get(f"/api/v1/master-data/geography/villages/by-pin-code?pin_code={pin}&limit=10&postal_limit=10")
    check(response.status_code == 200, f"{pin} lookup returns 200", response.text[:500])
    return response.json()


def main() -> int:
    print("=" * 72)
    print("PIN CODE LOOKUP GUARDRAIL REGRESSION")
    print("=" * 72)

    bihar = get("847409")
    check(bihar["schema_version"] == "pin_code_lookup.v1", "Response schema version present")
    check(bihar["is_valid_postal_pin"] is True, "847409 is valid postal PIN", bihar)
    check(bihar["has_lgd_village_candidates"] is True, "847409 has LGD village candidates", bihar["village_candidate_count"])
    check(bihar["status_reason"] == "LGD_VILLAGE_CANDIDATES_FOUND", "847409 status reason is candidate-found")
    check(len(bihar["village_candidates"]) > 0, "847409 returns village candidates")
    check(len(bihar["postal_references"]) > 0, "847409 returns postal references")

    telangana = get("504273")
    check(telangana["is_valid_postal_pin"] is True, "504273 is valid postal PIN")
    check(telangana["has_lgd_village_candidates"] is True, "504273 has LGD village candidates", telangana["village_candidate_count"])

    urban = get("560001")
    check(urban["is_valid_postal_pin"] is True, "560001 is valid postal PIN")
    check(urban["has_lgd_village_candidates"] is False, "560001 has no rural LGD village candidates", urban)
    check(urban["status_reason"] == "VALID_POSTAL_PIN_NO_LGD_VILLAGES", "560001 status reason distinguishes valid postal/no LGD villages")
    check(len(urban["postal_references"]) > 0, "560001 still returns postal references")

    unknown = get("999999")
    check(unknown["is_valid_postal_pin"] is False, "999999 is unknown in active postal data", unknown)
    check(unknown["has_lgd_village_candidates"] is False, "999999 has no village candidates")
    check(unknown["status_reason"] == "PIN_NOT_FOUND", "999999 status reason is PIN_NOT_FOUND")

    malformed = client.get("/api/v1/master-data/geography/villages/by-pin-code?pin_code=56001")
    check(malformed.status_code == 422, "Malformed PIN is rejected by request validation", malformed.text[:300])

    print("=" * 72)
    print("PIN code lookup guardrails validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())