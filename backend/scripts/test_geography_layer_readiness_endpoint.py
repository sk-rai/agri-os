#!/usr/bin/env python3
"""Regression for read-only geography layer readiness endpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin  # noqa: E402


ENDPOINT = "/api/v1/master-data/geography/layer-readiness"


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str)[:2400])
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("GEOGRAPHY LAYER READINESS ENDPOINT REGRESSION")
    print("=" * 72)

    client = TestClient(app)
    db = SessionLocal()
    admin = None

    try:
        unauth = client.get(ENDPOINT)
        check(unauth.status_code in (401, 403), "Unauthenticated readiness endpoint is denied", unauth.text)

        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="default")

        response = client.get(ENDPOINT, headers=headers)
        check(response.status_code == 200, "Admin can read readiness endpoint", response.text)

        data = response.json()
        summary = data["summary"]
        gap = data["gap_accounting"]

        check(data["schema_version"] == "geography_layer_readiness_matrix.v1", "Schema version is stable", data)
        check(data["mode"] == "READ_ONLY_STATE_DISTRICT_GEOGRAPHY_LAYER_READINESS_MATRIX", "Endpoint is read-only matrix", data)
        check(data["healthy"] is True, "Endpoint is healthy", data)
        check(len(data["rows"]) > 0, "Endpoint returns rows", data["rows"][:2])

        check(summary["state_district_row_count"] > 0, "State/district row count is visible", summary)
        check(summary["lgd_village_count"] >= 500000, "LGD village coverage is visible", summary)
        check(summary["pin_linked_village_count"] >= 500000, "PIN-code coverage is visible", summary)
        check(summary["demographic_active_promoted_count"] >= 450000, "NWDP demographic admin layer is visible", summary)
        check(summary["demographic_remaining_eligible_count"] == 0, "No demographic rows remain promotion-eligible", summary)
        check(summary["boundary_candidate_count"] >= 550000, "District-placeable boundary candidates are visible", summary)

        check(gap["boundary_candidate_raw_count"] >= summary["boundary_candidate_count"], "Boundary raw count covers matrix count", gap)
        check(gap["boundary_candidate_outside_state_district_matrix_count"] > 0, "Boundary outside-matrix gap is exposed", gap)
        check(gap["demographic_profile_outside_state_district_matrix_count"] == 0, "Demographic profiles are fully placeable", gap)
        check(gap["pin_link_outside_state_district_matrix_count"] == 0, "PIN links are fully placeable", gap)

        posture = data["source_posture"]
        check(posture["lgd_is_canonical_runtime_identity"] is True, "LGD remains canonical runtime identity", posture)
        check(posture["village_pin_codes_android_ready"] is True, "PIN-code layer remains Android-ready", posture)
        check(posture["nwdp_demographic_android_enabled"] is False, "NWDP demographic remains Android-disabled", posture)
        check(posture["nwdp_boundary_runtime_lookup_enabled"] is False, "NWDP boundary runtime lookup remains disabled", posture)
        check(posture["soi_direct_lgd_join_safe"] is False, "SOI direct LGD join remains unsafe", posture)

        guardrails = data["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Endpoint attempts no DB writes", guardrails)
        check(guardrails["runtime_lookup_enabled"] is False, "Endpoint does not enable runtime lookup", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Endpoint does not change Android behavior", guardrails)

        scoped = client.get(
        ENDPOINT + "?state_or_ut=Andaman%20And%20Nicobar%20Islands&district=Nicobars&limit=5",
        headers=headers,
        )
        check(scoped.status_code == 200, "Scoped readiness endpoint returns 200", scoped.text)
        scoped_data = scoped.json()
        check(scoped_data["filters"]["district"] == "Nicobars", "Scoped endpoint records district filter", scoped_data["filters"])
        check(len(scoped_data["rows"]) <= 5, "Scoped endpoint honors limit", scoped_data["rows"])

        print("=" * 72)
        print("GEOGRAPHY LAYER READINESS ENDPOINT REGRESSION PASSED")
        print("=" * 72)
        return 0
    finally:
        if admin is not None:
            delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
