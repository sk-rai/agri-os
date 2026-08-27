#!/usr/bin/env python3
"""Regression for disabled NWDP project matching apply endpoint contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


def check(condition: bool, label: str, detail=None):
    print(("PASS" if condition else "FAIL") + " " + label)
    if detail is not None:
        print("   ", json.dumps(detail, indent=2, default=str)[:1600])
    if not condition:
        raise AssertionError(label)


def get_project_id() -> str:
    with SessionLocal() as db:
        row = db.execute(
            text("""
                select id
                from projects
                where is_active = true
                order by created_at nulls last, id
                limit 1
            """)
        ).mappings().first()
    if not row:
        raise AssertionError("No active project fixture found")
    return str(row["id"])


def candidate_counts() -> dict:
    with SessionLocal() as db:
        return dict(db.execute(text("""
            select
              count(*) as candidates,
              count(*) filter (where is_active = true) as active_candidates,
              count(*) filter (where promotion_status <> 'NOT_PROMOTED') as promoted_candidates
            from geography_boundary_crosswalk_candidates
        """)).mappings().first())


def project_match_count() -> int:
    with SessionLocal() as db:
        return int(db.execute(text("select count(*) from geography_boundary_project_matches")).scalar_one())


def main() -> int:
    client = TestClient(app)
    project_id = get_project_id()
    before_candidates = candidate_counts()
    before_project_matches = project_match_count()
    admin = None

    unauth = client.post(
        "/api/v1/master-data/geography/nwdp-boundary-project-matching/apply",
        params={"project_id": project_id},
    )
    check(unauth.status_code in (401, 403), "Unauthenticated apply is denied", unauth.text)

    with SessionLocal() as db:
        admin, headers = create_test_admin(db, role="ADMIN_EDITOR", tenant_id="default")

    try:
        response = client.post(
            "/api/v1/master-data/geography/nwdp-boundary-project-matching/apply",
        params={
            "project_id": project_id,
            "feature_flag_enabled": "true",
            "dry_run_confirmed": "true",
            "admin_confirmation": "true",
            "rollback_token": "nwdp-boundary-apply-disabled-regression",
        },
            headers=headers,
        )
        check(response.status_code == 501, "Admin apply contract returns not implemented", response.text)

        detail = response.json()["detail"]
        check(detail["schema_version"] == "nwdp_boundary_project_matching_apply_disabled.v1", "Schema version is stable", detail)
        check(detail["mode"] == "PROJECT_MATCHING_APPLY_NOT_IMPLEMENTED", "Endpoint is disabled", detail)
        check(detail["required_gates"]["all_gates_present"] is True, "Endpoint reports all supplied gates", detail["required_gates"])
        check(detail["readiness"]["ready_for_apply_contract_review"] is True, "Endpoint is ready for contract review", detail["readiness"])
        check(detail["readiness"]["ready_for_project_matching_apply"] is False, "Endpoint is not ready for apply", detail["readiness"])

        policy = detail["candidate_selection_policy"]
        check(policy["candidate_bucket"] == "DIRECT_VLCODE_MATCH", "Policy selects direct vlcode only", policy)
        check(policy["review_status"] == "AUTO_CANDIDATE", "Policy selects auto candidates only", policy)
        check(policy["manual_review_candidates_excluded"] is True, "Policy excludes manual review", policy)
        check(policy["blocked_candidates_excluded"] is True, "Policy excludes blocked", policy)

        guardrails = detail["guardrails"]
        check(guardrails["db_writes_attempted"] is False, "Endpoint attempts no DB writes", guardrails)
        check(guardrails["project_matching_records_written"] is False, "Endpoint writes no project matching records", guardrails)
        check(guardrails["candidate_activation_changed"] is False, "Endpoint does not activate candidates", guardrails)
        check(guardrails["candidate_promotion_changed"] is False, "Endpoint does not promote candidates", guardrails)
        check(guardrails["runtime_tables_written"] is False, "Endpoint writes no runtime tables", guardrails)
        check(guardrails["lookup_api_enabled"] is False, "Endpoint keeps lookup disabled", guardrails)
        check(guardrails["android_behavior_changed"] is False, "Endpoint keeps Android unchanged", guardrails)

    finally:
        if admin is not None:
            with SessionLocal() as db:
                delete_test_admin(db, admin.id)

    after_candidates = candidate_counts()
    after_project_matches = project_match_count()

    check(after_project_matches == before_project_matches, "Endpoint did not create project match rows", {
        "before": before_project_matches,
        "after": after_project_matches,
    })
    check(after_candidates == before_candidates, "Endpoint did not mutate NWDP candidates", {
        "before": before_candidates,
        "after": after_candidates,
    })

    print("=" * 72)
    print("NWDP BOUNDARY PROJECT MATCHING APPLY DISABLED ENDPOINT REGRESSION PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
