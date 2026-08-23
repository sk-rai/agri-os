#!/usr/bin/env python3
"""Regression for NWDP boundary runtime promotion dry-run.

The endpoint must stay read-only: it can calculate promotion eligibility, but it
must not create runtime rows, activate candidates, promote candidates, or change
Android/runtime behavior.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


TOKEN = os.environ.get("WEB_SWEEP_TOKEN")
TENANT_ID = os.environ.get("WEB_SWEEP_TENANT_ID", "default")
ACTOR_ID = os.environ.get("WEB_SWEEP_ACTOR_ID")

if not TOKEN or not ACTOR_ID:
    raise SystemExit("Missing WEB_SWEEP_TOKEN / WEB_SWEEP_ACTOR_ID. Generate them with create_web_ui_smoke_session.py.")

client = TestClient(app)
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "X-Tenant-ID": TENANT_ID,
    "X-Actor-ID": ACTOR_ID,
}


def assert_pass(name: str, condition: bool, payload=None) -> None:
    if not condition:
        print(f"FAIL {name}")
        if payload is not None:
            print(json.dumps(payload, indent=2, default=str))
        raise SystemExit(1)
    print(f"PASS {name}")
    if payload is not None:
        print("    ", json.dumps(payload, indent=2, default=str)[:1200])


def main() -> None:
    before = client.get(
        "/api/v1/master-data/geography/nwdp-boundary-batches/38c31776-9683-5b36-bb79-0438864b9f3f/candidates",
        headers=headers,
        params={"limit": 1},
    )
    assert_pass("Candidate list before dry-run is readable", before.status_code == 200, before.text)
    before_data = before.json()
    before_summary = before_data["summary"]

    response = client.get(
        "/api/v1/master-data/geography/boundary-runtime-promotion/dry-run",
        headers=headers,
        params={
            "state_or_ut": "Karnataka",
            "source_system": "NWDP_GSI_VILLAGE_BOUNDARY",
            "limit": 5,
        },
    )
    assert_pass("Dry-run endpoint returns 200", response.status_code == 200, response.text)
    data = response.json()

    assert_pass("Dry-run schema version is stable", data.get("schema_version") == "nwdp_boundary_runtime_promotion_dry_run.v1", data)
    assert_pass("Dry-run mode is read-only", data.get("mode") == "DRY_RUN_READ_ONLY", data)

    summary = data.get("summary") or {}
    readiness = data.get("readiness") or {}

    assert_pass("Dry-run reports no DB writes", summary.get("db_writes_attempted") is False, summary)
    assert_pass("Dry-run writes no runtime tables", summary.get("runtime_tables_written") is False, summary)
    assert_pass("Dry-run does not enable runtime matching", summary.get("runtime_spatial_matching_changed") is False, summary)
    assert_pass("Dry-run does not change Android behavior", summary.get("android_behavior_changed") is False, summary)
    assert_pass("Dry-run keeps runtime matching not ready", readiness.get("ready_for_runtime_spatial_matching") is False, readiness)
    assert_pass("Dry-run marks runtime tables required", readiness.get("runtime_tables_required") is True, readiness)
    assert_pass("Dry-run does not support promotion", readiness.get("promotion_supported_by_this_endpoint") is False, readiness)

    assert_pass("Dry-run sees staged candidates", summary.get("candidate_count") == 29789, summary)
    assert_pass("No current candidate is promotable before approval", summary.get("promotable_candidate_count") == 0, summary)
    assert_pass("All current candidates are excluded before approval", summary.get("excluded_candidate_count") == 29789, summary)

    eligibility = data.get("eligibility_counts") or []
    assert_pass(
        "All current candidates are blocked by review approval",
        eligibility == [{"eligibility": "NOT_REVIEW_APPROVED", "count": 29789}],
        eligibility,
    )
    assert_pass("Excluded samples are returned", len(data.get("excluded_samples") or []) > 0, data.get("excluded_samples"))

    after = client.get(
        "/api/v1/master-data/geography/nwdp-boundary-batches/38c31776-9683-5b36-bb79-0438864b9f3f/candidates",
        headers=headers,
        params={"limit": 1},
    )
    assert_pass("Candidate list after dry-run is readable", after.status_code == 200, after.text)
    after_summary = after.json()["summary"]

    assert_pass("Dry-run did not create/delete candidates", after_summary["total"] == before_summary["total"], after_summary)
    assert_pass("Dry-run did not activate candidates", after_summary["active_candidate_count"] == before_summary["active_candidate_count"] == 0, after_summary)
    assert_pass("Dry-run did not promote candidates", after_summary["promoted_candidate_count"] == before_summary["promoted_candidate_count"] == 0, after_summary)

    print("=" * 72)
    print("NWDP BOUNDARY RUNTIME PROMOTION DRY-RUN REGRESSION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
