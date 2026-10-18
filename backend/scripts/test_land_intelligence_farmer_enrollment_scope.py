#!/usr/bin/env python3
"""Read-only behavior contract for project-scoped farmer land intelligence."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.core.database import SessionLocal
from app.core.human_auth import AuthenticatedPrincipal
from app.modules.auth.models import User
from app.modules.farmer.api import _require_land_intelligence_project_read_scope
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
    ProjectRole,
)
from app.modules.master_data.api.land_intelligence_summary import (
    _require_land_summary_project_read_scope,
)


TENANT_ID = "android-dynamic-test"
PROJECT_ID = uuid.UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
MOBILE = "+919900000002"


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def expect_scope_denied(call, label: str) -> None:
    try:
        call()
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        check(exc.status_code == 403, f"{label} returns 403")
        check(
            detail.get("error") == "LAND_INTELLIGENCE_SCOPE_DENIED",
            f"{label} uses stable scope denial",
        )
        return
    raise AssertionError(f"{label} unexpectedly permitted")


def main() -> int:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.mobile_number == MOBILE).one()
        farmer = db.query(Farmer).filter(
            Farmer.tenant_id == TENANT_ID,
            Farmer.user_id == user.id,
            Farmer.status != "ARCHIVED",
            Farmer.is_active == True,
        ).one()
        enrollment = db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id == TENANT_ID,
            FarmerProjectEnrollment.project_id == PROJECT_ID,
            FarmerProjectEnrollment.farmer_id == farmer.id,
            FarmerProjectEnrollment.status == "ACTIVE",
            FarmerProjectEnrollment.is_active == True,
        ).one()
        project_role_count = db.query(ProjectRole).filter(
            ProjectRole.project_id == PROJECT_ID,
            ProjectRole.user_id == user.id,
            ProjectRole.is_active == True,
        ).count()

        check(enrollment is not None, "fixture farmer has active project enrollment")
        check(project_role_count == 0, "fixture farmer has no project role")

        principal = AuthenticatedPrincipal(
            user_id=user.id,
            tenant_id=TENANT_ID,
            role="FARMER",
            device_id="read-only-enrollment-scope-regression",
        )
        _require_land_intelligence_project_read_scope(
            db,
            principal=principal,
            actor_id=user.id,
            project_id=PROJECT_ID,
        )
        check(True, "active enrolled farmer reads project land context")
        _require_land_summary_project_read_scope(
            db,
            principal=principal,
            actor_id=user.id,
            project_id=PROJECT_ID,
        )
        check(True, "active enrolled farmer reads project land summary")

        unrelated_id = uuid.UUID("a6921b17-88d0-486a-b7f5-26d9d375bdef")
        unrelated = AuthenticatedPrincipal(
            user_id=unrelated_id,
            tenant_id=TENANT_ID,
            role="FARMER",
            device_id="read-only-unrelated-scope-regression",
        )
        expect_scope_denied(
            lambda: _require_land_intelligence_project_read_scope(
                db,
                principal=unrelated,
                actor_id=unrelated_id,
                project_id=PROJECT_ID,
            ),
            "unrelated farmer land context",
        )
        expect_scope_denied(
            lambda: _require_land_summary_project_read_scope(
                db,
                principal=unrelated,
                actor_id=unrelated_id,
                project_id=PROJECT_ID,
            ),
            "unrelated farmer land summary",
        )
    finally:
        db.close()

    print("LAND INTELLIGENCE FARMER ENROLLMENT SCOPE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
