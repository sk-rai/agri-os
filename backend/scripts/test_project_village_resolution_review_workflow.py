#!/usr/bin/env python3
from pathlib import Path
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import text

from app.core.admin_auth import AdminPrincipal
from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.master_data.api.project_village_resolutions import (
    ProjectVillageResolutionDryRun,
    ProjectVillageResolutionReview,
    ProjectVillageResolutionRollback,
    activate_approved_resolution,
    approve_canonical_resolution,
    list_project_resolutions,
    nwdp_candidates,
    propose_canonical_resolution,
    rollback_canonical_resolution,
    worklist,
)
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

PROJECT = UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
TENANT = "android-dynamic-test"
ROLLBACK_TOKEN = "review-workflow-rollback-token"


def snapshot(db):
    return dict(
        db.execute(
            text(
                """
                select
                  (select count(*) from geography_villages) villages,
                  (select count(*) from geography_village_pin_links) pins,
                  (select count(*) from geography_boundary_crosswalk_candidates) candidates,
                  (select count(*) from geography_boundary_runtime_crosswalks) runtime,
                  (select count(*) from geography_boundary_project_matches) project_matches
                """
            )
        ).mappings().one()
    )


with SessionLocal() as db:
    proposer, _ = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT)
    approver, _ = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT)
    proposer_principal = AdminPrincipal(
        user_id=proposer.id, tenant_id=TENANT, role="ENTERPRISE_ADMIN", project_id=PROJECT
    )
    approver_principal = AdminPrincipal(
        user_id=approver.id, tenant_id=TENANT, role="ENTERPRISE_ADMIN", project_id=PROJECT
    )
    resolution_id = None
    original_gate = settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED
    try:
        before = snapshot(db)
        row = worklist(PROJECT, "FULLY_RESOLVED", 1, 0, db, TENANT, proposer_principal)["items"][0]
        search = nwdp_candidates(
            PROJECT,
            UUID(row["village_id"]),
            row["village_name"],
            20,
            db,
            TENANT,
            proposer_principal,
        )
        candidate = next(item for item in search["items"] if item["eligible_for_canonical_enrichment"])
        proposal_body = ProjectVillageResolutionDryRun(
            resolution_mode="CANONICAL_ENRICHMENT",
            canonical_village_id=UUID(row["village_id"]),
            nwdp_source_feature_id=UUID(candidate["source_feature_id"]),
            display_name=row["village_name"],
            pin_codes=list(row["pin_codes"]),
            hierarchy_labels={
                "state": row["state_name"],
                "district": row["district_name"],
                "block": row["block_name"],
            },
            evidence_basis="TWO_SESSION_ADMIN_REVIEW",
            review_notes="Proposal created for independent enterprise-admin review",
            rollback_token=ROLLBACK_TOKEN,
            dry_run=True,
            confirm_apply=False,
        )

        settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED = False
        proposed = propose_canonical_resolution(
            PROJECT, proposal_body, db, TENANT, proposer_principal
        )
        resolution_id = UUID(proposed["resolution_id"])
        assert proposed["status"] == "DRAFT"
        assert proposed["activation_enabled"] is False
        assert proposed["android_visible"] is False

        review = ProjectVillageResolutionReview(
            confirmation_phrase="APPROVE PROJECT CANONICAL ENRICHMENT",
            review_notes="Independent review confirms project-scoped evidence",
        )
        try:
            approve_canonical_resolution(
                PROJECT, resolution_id, review, db, TENANT, proposer_principal
            )
            raise AssertionError("Proposer unexpectedly approved own proposal")
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail == "SECOND_ADMIN_MUST_DIFFER_FROM_PROPOSER"

        approved = approve_canonical_resolution(
            PROJECT, resolution_id, review, db, TENANT, approver_principal
        )
        assert approved["status"] == "APPROVED"
        assert approved["activation_enabled"] is False

        queue = list_project_resolutions(
            PROJECT, None, 50, db, TENANT, approver_principal
        )
        queued = next(item for item in queue["items"] if item["resolution_id"] == str(resolution_id))
        assert queued["resolution_status"] == "APPROVED"
        assert [event["action"] for event in queued["events"]] == ["PROPOSED", "APPROVED"]
        assert queue["activation_enabled"] is False

        activation = ProjectVillageResolutionReview(
            confirmation_phrase="ACTIVATE APPROVED PROJECT CANONICAL ENRICHMENT",
            review_notes="Activation regression after independent approval",
        )
        try:
            activate_approved_resolution(
                PROJECT, resolution_id, activation, db, TENANT, approver_principal
            )
            raise AssertionError("Disabled activation unexpectedly succeeded")
        except HTTPException as exc:
            assert exc.status_code == 503
            assert exc.detail["code"] == "PROJECT_VILLAGE_RESOLUTION_APPLY_DISABLED"

        settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED = True
        active = activate_approved_resolution(
            PROJECT, resolution_id, activation, db, TENANT, approver_principal
        )
        assert active["status"] == "ACTIVE"
        assert active["android_visible"] is False
        assert active["global_geography_changed"] is False

        rolled = rollback_canonical_resolution(
            PROJECT,
            resolution_id,
            ProjectVillageResolutionRollback(
                rollback_token=ROLLBACK_TOKEN,
                reason="Regression confirms immediate project-only rollback",
            ),
            db,
            TENANT,
            approver_principal,
        )
        assert rolled["status"] == "RETIRED"
        actions = list(
            db.execute(
                text(
                    "select action from geography_project_village_resolution_events "
                    "where resolution_id=:id order by created_at"
                ),
                {"id": str(resolution_id)},
            ).scalars()
        )
        assert actions == ["PROPOSED", "APPROVED", "APPLIED", "ROLLED_BACK"]
        assert snapshot(db) == before
        print(
            {
                "schema_version": "project_village_resolution_review_workflow_test.v1",
                "proposal_status": "DRAFT",
                "approval_status": "APPROVED",
                "activation_status": "ACTIVE",
                "rollback_status": "RETIRED",
                "audit_actions": actions,
                "self_approval_rejected": True,
                "activation_default_closed": True,
                "global_geography_unchanged": True,
                "android_visible": False,
            }
        )
    finally:
        settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED = original_gate
        if resolution_id:
            db.execute(
                text("delete from geography_project_village_resolution_events where resolution_id=:id"),
                {"id": str(resolution_id)},
            )
            db.execute(
                text("delete from geography_project_village_resolutions where id=:id"),
                {"id": str(resolution_id)},
            )
            db.commit()
        delete_test_admin(db, proposer.id)
        delete_test_admin(db, approver.id)

print("PROJECT VILLAGE RESOLUTION REVIEW WORKFLOW PASSED")
