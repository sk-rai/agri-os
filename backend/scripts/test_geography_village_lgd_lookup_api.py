#!/usr/bin/env python3
"""Regression coverage for canonical village LGD bulk lookup."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal
from app.main import app

ENDPOINT = "/api/v1/master-data/geography/villages/by-lgd-codes"


def check(condition: bool, label: str, detail=None) -> None:
    print(("PASS" if condition else "FAIL") + " " + label)
    if not condition:
        if detail is not None:
            print(detail)
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("GEOGRAPHY VILLAGE LGD LOOKUP API REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT
                v.lgd_code,
                v.canonical_name,
                b.canonical_name AS block_name,
                d.canonical_name AS district_name,
                s.canonical_name AS state_name
            FROM geography_villages v
            JOIN geography_blocks b ON b.id = v.block_id
            JOIN geography_districts d ON d.id = v.district_id
            JOIN geography_states s ON s.id = d.state_id
            WHERE v.is_active IS TRUE
              AND b.is_active IS TRUE
              AND d.is_active IS TRUE
              AND s.is_active IS TRUE
              AND v.lgd_code IS NOT NULL
            ORDER BY v.lgd_code
            LIMIT 2
        """)).mappings().all()
    finally:
        db.close()

    check(len(rows) == 2, "Two active canonical villages are available")

    client = TestClient(app)
    codes = [row["lgd_code"] for row in rows]

    response = client.get(
        ENDPOINT,
        params={"lgd_codes": ",".join([codes[1], codes[0], codes[1]])},
    )
    payload = response.json()

    check(response.status_code == 200, "Bulk lookup succeeds", payload)
    check(len(payload) == 2, "Duplicate LGD codes are deduplicated", payload)
    check(
        [row["lgd_code"] for row in payload] == [codes[1], codes[0]],
        "Requested LGD order is preserved",
        payload,
    )
    check(
        all(
            row.get("canonical_name")
            and row.get("block_name")
            and row.get("district_name")
            and row.get("state_name")
            for row in payload
        ),
        "Canonical hierarchy labels are returned",
        payload,
    )

    missing = client.get(
        ENDPOINT,
        params={"lgd_codes": f"{codes[0]},999999999"},
    )
    missing_payload = missing.json()
    check(missing.status_code == 200, "Unknown LGD code is tolerated")
    check(
        [row["lgd_code"] for row in missing_payload] == [codes[0]],
        "Unknown LGD code is omitted",
        missing_payload,
    )

    invalid = client.get(
        ENDPOINT,
        params={"lgd_codes": "not-a-code"},
    )
    check(invalid.status_code == 400, "Non-numeric LGD code is rejected")

    print("=" * 72)
    print("GEOGRAPHY VILLAGE LGD LOOKUP API REGRESSION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
