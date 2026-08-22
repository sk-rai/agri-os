#!/usr/bin/env python3
"""Regression for read-only NWDP boundary admin review endpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def check(condition: bool, label: str, detail=None):
    status = "PASS" if condition else "FAIL"
    print(f"{status} {label}")
    if detail is not None:
        print(f"      {detail if isinstance(detail, str) else json.dumps(detail, indent=2, default=str)[:1200]}")
    if not condition:
        raise AssertionError(label)


def staging_summary(db):
    return db.execute(text("""
        select
          count(*) as candidates,
          sum(case when is_active then 1 else 0 end) as active_candidates,
          sum(case when promotion_status <> 'NOT_PROMOTED' then 1 else 0 end) as promoted_candidates
        from geography_boundary_crosswalk_candidates
    """)).mappings().one()


def main() -> int:
    print("=" * 72)
    print("NWDP BOUNDARY ADMIN READ ENDPOINT REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None

    try:
        before = staging_summary(db)
        check(before["candidates"] >= 29789, "NWDP staged candidates exist", dict(before))
        check(before["active_candidates"] == 0, "Staged candidates start inactive", dict(before))
        check(before["promoted_candidates"] == 0, "Staged candidates start unpromoted", dict(before))

        denied = client.get(
            "/api/v1/master-data/geography/nwdp-boundary-batches",
            headers={"X-Tenant-ID": "default"},
        )
        check(denied.status_code in {401, 403}, "Unauthenticated read is denied", denied.text[:500])

        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="default")

        batches = client.get(
            "/api/v1/master-data/geography/nwdp-boundary-batches?state_or_ut=Karnataka&limit=5",
            headers=headers,
        )
        check(batches.status_code == 200, "Admin viewer can list batches", batches.text[:800])
        batch_data = batches.json()
        check(batch_data["schema_version"] == "nwdp_boundary_admin_batches.v1", "Batch schema version is stable", batch_data)
        check(batch_data["mode"] == "READ_ONLY_ADMIN_REVIEW", "Batch endpoint is read-only review mode", batch_data)
        check(batch_data["governance"]["read_only_runtime"] is True, "Batch governance is read-only runtime", batch_data["governance"])
        check(batch_data["governance"]["promotion_supported"] is False, "Batch governance disables promotion", batch_data["governance"])
        check(batch_data["summary"]["runtime_spatial_matching_changed"] is False, "Batch list has no runtime spatial impact", batch_data["summary"])
        check(len(batch_data["items"]) >= 1, "At least one NWDP batch returned", batch_data["items"])

        batch_id = batch_data["items"][0]["batch_id"]

        batch_detail = client.get(
            f"/api/v1/master-data/geography/nwdp-boundary-batches/{batch_id}",
            headers=headers,
        )
        check(batch_detail.status_code == 200, "Admin viewer can read batch detail", batch_detail.text[:800])
        detail_data = batch_detail.json()
        check(detail_data["schema_version"] == "nwdp_boundary_admin_batch_detail.v1", "Batch detail schema version is stable", detail_data)
        check(detail_data["candidate_summary"]["candidate_count"] == 29789, "Batch detail candidate count matches import", detail_data["candidate_summary"])
        check(detail_data["candidate_summary"]["active_candidate_count"] == 0, "Batch detail active candidates remain zero", detail_data["candidate_summary"])
        check(detail_data["candidate_summary"]["promoted_candidate_count"] == 0, "Batch detail promoted candidates remain zero", detail_data["candidate_summary"])

        candidates = client.get(
            f"/api/v1/master-data/geography/nwdp-boundary-batches/{batch_id}/candidates?review_status=MANUAL_REVIEW&limit=5",
            headers=headers,
        )
        check(candidates.status_code == 200, "Admin viewer can list candidates", candidates.text[:800])
        candidate_data = candidates.json()
        check(candidate_data["schema_version"] == "nwdp_boundary_admin_candidates.v1", "Candidate list schema version is stable", candidate_data)
        check(candidate_data["mode"] == "READ_ONLY_ADMIN_REVIEW", "Candidate list is read-only review mode", candidate_data)
        check(candidate_data["summary"]["runtime_spatial_matching_changed"] is False, "Candidate list has no runtime impact", candidate_data["summary"])
        check(len(candidate_data["items"]) >= 1, "Candidate list returns rows", candidate_data["items"])

        candidate_id = candidate_data["items"][0]["candidate_id"]

        candidate_detail = client.get(
            f"/api/v1/master-data/geography/nwdp-boundary-candidates/{candidate_id}",
            headers=headers,
        )
        check(candidate_detail.status_code == 200, "Admin viewer can read candidate detail", candidate_detail.text[:800])
        candidate_detail_data = candidate_detail.json()
        check(candidate_detail_data["schema_version"] == "nwdp_boundary_admin_candidate_detail.v1", "Candidate detail schema version is stable", candidate_detail_data)
        check(candidate_detail_data["governance"]["promotion_supported"] is False, "Candidate detail disables promotion", candidate_detail_data["governance"])
        check(candidate_detail_data["candidate"]["is_active"] is False, "Candidate detail row remains inactive", candidate_detail_data["candidate"])
        check(candidate_detail_data["candidate"]["promotion_status"] == "NOT_PROMOTED", "Candidate detail row remains unpromoted", candidate_detail_data["candidate"])

        after = staging_summary(db)
        check(after["candidates"] == before["candidates"], "Read endpoints did not create/delete candidates", dict(after))
        check(after["active_candidates"] == 0, "Read endpoints did not activate candidates", dict(after))
        check(after["promoted_candidates"] == 0, "Read endpoints did not promote candidates", dict(after))

        print("=" * 72)
        print("NWDP BOUNDARY ADMIN READ ENDPOINT REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
