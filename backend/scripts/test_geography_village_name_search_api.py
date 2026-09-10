#!/usr/bin/env python3
"""Regression for global and district-scoped canonical village-name search."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal
from app.main import app

ENDPOINT = "/api/v1/master-data/geography/villages/search"


def check(condition, label, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if not condition:
        if detail is not None:
            print(detail)
        raise AssertionError(label)


def main():
    print("=" * 72)
    print("GEOGRAPHY VILLAGE NAME SEARCH API REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    try:
        fixture = db.execute(text("""
            select
              v.lgd_code,
              v.canonical_name,
              v.district_id::text as district_id,
              d.canonical_name as district_name,
              s.canonical_name as state_name
            from geography_villages v
            join geography_districts d on d.id = v.district_id
            join geography_states s on s.id = d.state_id
            where v.lgd_code = '645063'
              and v.is_active = true
              and d.is_active = true
              and s.is_active = true
        """)).mappings().one()
    finally:
        db.close()

    client = TestClient(app)
    query = fixture["canonical_name"].replace("*", "")

    global_response = client.get(
        ENDPOINT,
        params={"q": query, "limit": 30},
    )
    global_payload = global_response.json()

    check(
        global_response.status_code == 200,
        "Global village-name search succeeds",
        global_payload,
    )

    global_match = next(
        (
            row for row in global_payload
            if row["lgd_code"] == fixture["lgd_code"]
        ),
        None,
    )
    check(global_match is not None, "Global search finds fixture village")
    check(
        global_match["state_name"] == fixture["state_name"],
        "Global result includes canonical state",
        global_match,
    )
    check(
        global_match["district_name"] == fixture["district_name"],
        "Global result includes canonical district",
        global_match,
    )
    check(
        bool(
            global_match["state_id"]
            and global_match["district_id"]
            and global_match["block_id"]
        ),
        "Global result includes hierarchy identifiers",
        global_match,
    )

    scoped_response = client.get(
        ENDPOINT,
        params={
            "q": query,
            "district_id": fixture["district_id"],
            "limit": 30,
        },
    )
    scoped_payload = scoped_response.json()

    check(
        scoped_response.status_code == 200,
        "District-scoped village-name search succeeds",
        scoped_payload,
    )
    check(
        any(
            row["lgd_code"] == fixture["lgd_code"]
            for row in scoped_payload
        ),
        "District-scoped search retains fixture village",
        scoped_payload,
    )
    check(
        all(
            row["district_id"] == fixture["district_id"]
            for row in scoped_payload
        ),
        "District scope excludes other districts",
        scoped_payload,
    )

    lgd_response = client.get(
        ENDPOINT,
        params={"q": fixture["lgd_code"], "limit": 10},
    )
    lgd_payload = lgd_response.json()

    check(
        lgd_response.status_code == 200,
        "Direct LGD-code search succeeds",
        lgd_payload,
    )
    check(
        lgd_payload[0]["lgd_code"] == fixture["lgd_code"],
        "Exact LGD result ranks first",
        lgd_payload,
    )
    check(
        lgd_payload[0]["match_type"] == "EXACT_LGD",
        "Exact LGD match type is reported",
        lgd_payload[0],
    )
    check(
        global_match["match_type"] in {
            "EXACT_NAME",
            "PREFIX_NAME",
            "SUBSTRING_NAME",
            "FUZZY_NAME",
        },
        "Name match type is reported",
        global_match,
    )

    short_query = client.get(ENDPOINT, params={"q": "H"})
    check(short_query.status_code == 422, "One-character query is rejected")

    print("=" * 72)
    print("GEOGRAPHY VILLAGE NAME SEARCH API REGRESSION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
