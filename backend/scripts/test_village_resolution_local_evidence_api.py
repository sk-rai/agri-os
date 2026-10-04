#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def main() -> int:
    db = SessionLocal()
    user = None
    try:
        active = db.execute(text("""
          select s.id::text snapshot_id, s.item_count
          from geography_village_resolution_evidence_snapshots s
          where s.is_active
        """)).mappings().first()
        assert active and int(active["item_count"]) == 7493

        state = db.execute(text("""
          select distinct state.id::text state_id
          from geography_village_resolution_evidence_items item
          join geography_village_resolution_evidence_snapshots snapshot
            on snapshot.id=item.snapshot_id and snapshot.is_active
          join geography_villages village on village.id=item.village_id
          join geography_districts district on district.id=village.district_id
          join geography_states state on state.id=district.state_id
          where state.canonical_name='Rajasthan'
        """)).mappings().one()
        before = dict(db.execute(text("""
          select
            (select count(*) from geography_village_resolution_evidence_snapshots) snapshots,
            (select count(*) from geography_village_resolution_evidence_items) items,
            (select count(*) from geography_villages where is_active) villages,
            (select count(*) from geography_village_pin_links where is_active) pin_links,
            (select count(*) from geography_boundary_runtime_crosswalks where is_active) runtime_crosswalks
        """)).mappings().one())

        user, headers = create_test_admin(db)
        client = TestClient(app)
        base = "/api/v1/master-data/geography/village-resolution"
        common = {"state_id": state["state_id"], "resolution_status": "UNRESOLVED", "limit": 200}

        default_response = client.get(base, params=common, headers=headers)
        assert default_response.status_code == 200, default_response.text
        default_payload = default_response.json()
        assert default_payload["schema_version"] == "lgd_pin_nwdp_village_resolution.v1"
        assert default_payload["read_only"] is True
        assert "local_evidence_status" in default_payload["items"][0]

        eligible_response = client.get(
            base,
            params={**common, "review_eligibility": "TWO_SESSION_REVIEW_ELIGIBLE"},
            headers=headers,
        )
        assert eligible_response.status_code == 200, eligible_response.text
        eligible = eligible_response.json()
        assert eligible["pagination"]["filtered_total"] == 98
        assert all(row["review_eligibility"] == "TWO_SESSION_REVIEW_ELIGIBLE" for row in eligible["items"])

        collision_response = client.get(
            base,
            params={**common, "source_collision": "true"},
            headers=headers,
        )
        assert collision_response.status_code == 200, collision_response.text
        collisions = collision_response.json()
        assert collisions["pagination"]["filtered_total"] == 15
        assert all(row["source_collision"] is True for row in collisions["items"])
        assert all(row["review_eligibility"] == "CONFLICT_REVIEW_REQUIRED" for row in collisions["items"])

        invalid = client.get(
            base,
            params={**common, "local_evidence_status": "AUTO_APPROVE"},
            headers=headers,
        )
        assert invalid.status_code == 400

        after = dict(db.execute(text("""
          select
            (select count(*) from geography_village_resolution_evidence_snapshots) snapshots,
            (select count(*) from geography_village_resolution_evidence_items) items,
            (select count(*) from geography_villages where is_active) villages,
            (select count(*) from geography_village_pin_links where is_active) pin_links,
            (select count(*) from geography_boundary_runtime_crosswalks where is_active) runtime_crosswalks
        """)).mappings().one())
        assert before == after
        print({
            "schema_version": "village_resolution_local_evidence_api_test.v1",
            "active_snapshot_id": active["snapshot_id"],
            "rajasthan_two_session_eligible": eligible["pagination"]["filtered_total"],
            "rajasthan_collision_rows": collisions["pagination"]["filtered_total"],
            "database_unchanged": True,
            "cohort_specific_endpoint_added": False,
            "android_changed": False,
        })
        print("VILLAGE RESOLUTION LOCAL EVIDENCE API PASSED")
        return 0
    finally:
        if user is not None:
            delete_test_admin(db, user.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
