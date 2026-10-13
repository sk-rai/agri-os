#!/usr/bin/env python3
"""Behavior regression for geography review authorization boundaries."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Project, Tenant
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


GLOBAL_ERROR = "GLOBAL_GEOGRAPHY_REVIEW_TENANT_REQUIRED"


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main() -> int:
    print("=" * 72)
    print("GEOGRAPHY REVIEW AUTHORIZATION REGRESSION")
    print("=" * 72)

    tenant_id = f"geography-review-auth-{uuid.uuid4().hex[:8]}"
    foreign_tenant_id = (
        f"geography-review-auth-foreign-{uuid.uuid4().hex[:8]}"
    )
    project_id = uuid.uuid4()
    foreign_project_id = uuid.uuid4()

    platform_admin_id = None
    tenant_admin_id = None

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        if not db.query(Tenant).filter(Tenant.id == "default").first():
            db.add(Tenant(
                id="default",
                name="Default",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ))

        db.add_all([
            Tenant(
                id=tenant_id,
                name="Geography Review Authorization Tenant",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ),
            Tenant(
                id=foreign_tenant_id,
                name="Foreign Geography Review Tenant",
                type="ENTERPRISE",
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=project_id,
                tenant_id=tenant_id,
                name="Geography Review Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="PLANNED",
                geography_scope={},
                crop_scope=[],
                config={},
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=foreign_project_id,
                tenant_id=foreign_tenant_id,
                name="Foreign Geography Review Project",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=180),
                status="PLANNED",
                geography_scope={},
                crop_scope=[],
                config={},
                created_at=now,
                updated_at=now,
            ),
        ])
        db.commit()

        platform_admin, platform_headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id="default",
        )
        tenant_admin, tenant_headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=tenant_id,
        )
        platform_admin_id = platform_admin.id
        tenant_admin_id = tenant_admin.id
    finally:
        db.close()

    client = TestClient(app)
    random_id = uuid.uuid4()

    global_cases = [
        (
            "NWDP boundary candidate review",
            (
                "/api/v1/master-data/geography/"
                f"nwdp-boundary-candidates/{random_id}/review"
            ),
            {
                "reviewer_decision": "KEEP_PENDING",
                "review_status": "MANUAL_REVIEW",
                "reviewer_notes": "",
                "evidence_summary": {},
            },
            404,
        ),
        (
            "NWDP demographic profile review",
            (
                "/api/v1/master-data/geography/"
                f"nwdp-demographic-profiles/{random_id}/review"
            ),
            {
                "review_status": "MANUAL_REVIEW",
                "reviewer_decision": "MARK_MANUAL_REVIEW",
                "reviewer_notes": "Authorization boundary regression",
                "evidence_summary": {},
            },
            404,
        ),
        (
            "CoRE LGD mapping review",
            (
                "/api/v1/master-data/geography/"
                f"core-lgd-mapping-review/{random_id}/review"
            ),
            {
                "review_status": "MANUAL_REVIEW",
                "review_notes": "Authorization boundary regression",
            },
            404,
        ),
        (
            "Village evidence primary review",
            (
                "/api/v1/master-data/geography/"
                "village-resolution/reviews"
            ),
            {
                "evidence_item_id": str(random_id),
                "decision": "HOLD",
                "notes": "Authorization boundary regression",
            },
            404,
        ),
        (
            "Village evidence second review",
            (
                "/api/v1/master-data/geography/"
                f"village-resolution/reviews/{random_id}/second-review"
            ),
            {
                "decision": "HOLD",
                "notes": "Authorization boundary regression",
                "confirmation_phrase":
                    "COMPLETE SECOND VILLAGE EVIDENCE REVIEW",
            },
            409,
        ),
    ]

    try:
        first_name, first_url, first_payload, _ = global_cases[0]

        missing = client.patch(first_url, json=first_payload)
        check(
            missing.status_code == 401,
            "Global geography review rejects missing bearer",
            missing.text,
        )

        impersonated_headers = {
            **platform_headers,
            "X-Actor-ID": str(uuid.uuid4()),
        }
        impersonated = client.patch(
            first_url,
            headers=impersonated_headers,
            json=first_payload,
        )
        check(
            impersonated.status_code == 403,
            "Global geography review rejects actor impersonation",
            impersonated.text,
        )
        check(
            impersonated.json()["detail"]["error"]
            == "ACTOR_ID_MISMATCH",
            "Actor impersonation has stable error code",
        )

        mismatched_headers = {
            **platform_headers,
            "X-Tenant-ID": tenant_id,
        }
        mismatched = client.patch(
            first_url,
            headers=mismatched_headers,
            json=first_payload,
        )
        check(
            mismatched.status_code == 403,
            "Global geography review rejects token/header mismatch",
            mismatched.text,
        )

        for name, url, payload, platform_status in global_cases:
            method = (
                client.post
                if "village-resolution/reviews" in url
                else client.patch
            )

            tenant_response = method(
                url,
                headers=tenant_headers,
                json=payload,
            )
            check(
                tenant_response.status_code == 403,
                f"{name} rejects ordinary tenant administrator",
                tenant_response.text,
            )
            check(
                tenant_response.json()["detail"]["error"]
                == GLOBAL_ERROR,
                f"{name} returns stable platform boundary error",
            )

            platform_response = method(
                url,
                headers=platform_headers,
                json=payload,
            )
            check(
                platform_response.status_code == platform_status,
                f"{name} permits platform administrator to reach resource validation",
                platform_response.text,
            )

        disabled_url = (
            "/api/v1/master-data/geography/"
            "nwdp-boundary-project-matching/apply"
        )

        missing_project = client.post(
            disabled_url,
            params={"project_id": str(project_id)},
        )
        check(
            missing_project.status_code == 401,
            "Disabled project matching apply rejects missing bearer",
            missing_project.text,
        )

        disabled_impersonated = client.post(
            disabled_url,
            params={"project_id": str(project_id)},
            headers={
                **tenant_headers,
                "X-Actor-ID": str(uuid.uuid4()),
            },
        )
        check(
            disabled_impersonated.status_code == 403,
            "Disabled project matching apply rejects actor impersonation",
            disabled_impersonated.text,
        )

        disabled = client.post(
            disabled_url,
            params={"project_id": str(project_id)},
            headers=tenant_headers,
        )
        check(
            disabled.status_code == 501,
            "Tenant project administrator reaches disabled contract",
            disabled.text[:1600],
        )
        detail = disabled.json()["detail"]
        check(
            detail["project"]["tenant_id"] == tenant_id,
            "Disabled contract reports verified project tenant",
        )
        check(
            detail["project"]["requested_by"]
            == str(tenant_admin_id),
            "Disabled contract reports verified administrator",
        )
        check(
            detail["guardrails"]["db_writes_attempted"] is False,
            "Disabled contract remains database write-free",
        )

        foreign = client.post(
            disabled_url,
            params={"project_id": str(foreign_project_id)},
            headers=tenant_headers,
        )
        check(
            foreign.status_code == 404,
            "Disabled project matching apply hides foreign project",
            foreign.text,
        )

    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(Project).filter(
                Project.id.in_([project_id, foreign_project_id])
            ).delete(synchronize_session=False)
            cleanup.commit()

            for user_id in (tenant_admin_id, platform_admin_id):
                if user_id:
                    delete_test_admin(cleanup, user_id)

            cleanup.query(Tenant).filter(
                Tenant.id.in_([tenant_id, foreign_tenant_id])
            ).delete(synchronize_session=False)
            cleanup.commit()
        finally:
            cleanup.close()

    print("=" * 72)
    print("Geography review authorization validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
