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
    approve_canonical_resolution,
    cancel_project_resolution,
    nwdp_candidates,
    propose_canonical_resolution,
    reject_project_resolution,
    worklist,
)
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

PROJECT = UUID("0f7e0a6b-8472-5d6d-8a14-a9d000000001")
TENANT = "android-dynamic-test"


def protected_snapshot(db):
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


def actions(db, resolution_id):
    return list(
        db.execute(
            text(
                """
                select action
                from geography_project_village_resolution_events
                where resolution_id = :id
                order by created_at, id
                """
            ),
            {"id": str(resolution_id)},
        ).scalars()
    )


with SessionLocal() as db:
    proposer, _ = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT)
    reviewer, _ = create_test_admin(db, role="ENTERPRISE_ADMIN", tenant_id=TENANT)
    proposer_principal = AdminPrincipal(
        user_id=proposer.id, tenant_id=TENANT, role="ENTERPRISE_ADMIN", project_id=PROJECT
    )
    reviewer_principal = AdminPrincipal(
        user_id=reviewer.id, tenant_id=TENANT, role="ENTERPRISE_ADMIN", project_id=PROJECT
    )
    created_ids = []
    original_gate = settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED

    try:
        settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED = False
        before = protected_snapshot(db)
        village = worklist(
            PROJECT, "FULLY_RESOLVED", 1, 0, db, TENANT, proposer_principal
        )["items"][0]
        search = nwdp_candidates(
            PROJECT,
            UUID(village["village_id"]),
            village["village_name"],
            20,
            db,
            TENANT,
            proposer_principal,
        )
        candidate = next(
            item for item in search["items"] if item["eligible_for_canonical_enrichment"]
        )

        def create_proposal(label):
            body = ProjectVillageResolutionDryRun(
                resolution_mode="CANONICAL_ENRICHMENT",
                canonical_village_id=UUID(village["village_id"]),
                nwdp_source_feature_id=UUID(candidate["source_feature_id"]),
                display_name=village["village_name"],
                pin_codes=list(village["pin_codes"]),
                hierarchy_labels={
                    "state": village["state_name"],
                    "district": village["district_name"],
                    "block": village["block_name"],
                },
                evidence_basis="TERMINAL_REVIEW_REGRESSION",
                review_notes=f"{label} proposal requires terminal review",
                rollback_token=f"terminal-review-{label.lower().replace(' ', '-')}",
                dry_run=True,
                confirm_apply=False,
            )
            result = propose_canonical_resolution(
                PROJECT, body, db, TENANT, proposer_principal
            )
            resolution_id = UUID(result["resolution_id"])
            created_ids.append(resolution_id)
            assert result["status"] == "DRAFT"
            assert result["activation_enabled"] is False
            return resolution_id

        cancellation_id = create_proposal("Cancellation")
        cancel_body = ProjectVillageResolutionReview(
            confirmation_phrase="CANCEL PROJECT CANONICAL ENRICHMENT",
            review_notes="Proposer withdraws obsolete evidence before review",
        )
        try:
            cancel_project_resolution(
                PROJECT,
                cancellation_id,
                cancel_body,
                db,
                TENANT,
                reviewer_principal,
            )
            raise AssertionError("Non-proposer unexpectedly cancelled draft")
        except HTTPException as exc:
            assert exc.status_code == 403
            assert exc.detail == "ONLY_PROPOSER_CAN_CANCEL_DRAFT"

        cancelled = cancel_project_resolution(
            PROJECT,
            cancellation_id,
            cancel_body,
            db,
            TENANT,
            proposer_principal,
        )
        assert cancelled["status"] == "REJECTED"
        assert cancelled["terminal_action"] == "CANCELLED"
        assert actions(db, cancellation_id) == ["PROPOSED", "CANCELLED"]

        draft_rejection_id = create_proposal("Draft rejection")
        reject_body = ProjectVillageResolutionReview(
            confirmation_phrase="REJECT PROJECT CANONICAL ENRICHMENT",
            review_notes="Independent reviewer rejects insufficient project evidence",
        )
        try:
            reject_project_resolution(
                PROJECT,
                draft_rejection_id,
                reject_body,
                db,
                TENANT,
                proposer_principal,
            )
            raise AssertionError("Proposer unexpectedly rejected own draft")
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail == "SECOND_ADMIN_MUST_DIFFER_FROM_PROPOSER"

        rejected_draft = reject_project_resolution(
            PROJECT,
            draft_rejection_id,
            reject_body,
            db,
            TENANT,
            reviewer_principal,
        )
        assert rejected_draft["status"] == "REJECTED"
        assert rejected_draft["previous_status"] == "DRAFT"
        assert actions(db, draft_rejection_id) == ["PROPOSED", "REJECTED"]

        approved_rejection_id = create_proposal("Approved rejection")
        approval = approve_canonical_resolution(
            PROJECT,
            approved_rejection_id,
            ProjectVillageResolutionReview(
                confirmation_phrase="APPROVE PROJECT CANONICAL ENRICHMENT",
                review_notes="Independent reviewer initially approves the evidence",
            ),
            db,
            TENANT,
            reviewer_principal,
        )
        assert approval["status"] == "APPROVED"

        rejected_approved = reject_project_resolution(
            PROJECT,
            approved_rejection_id,
            ProjectVillageResolutionReview(
                confirmation_phrase="REJECT PROJECT CANONICAL ENRICHMENT",
                review_notes="Independent reviewer closes approval after evidence withdrawal",
            ),
            db,
            TENANT,
            reviewer_principal,
        )
        assert rejected_approved["status"] == "REJECTED"
        assert rejected_approved["previous_status"] == "APPROVED"
        assert actions(db, approved_rejection_id) == [
            "PROPOSED",
            "APPROVED",
            "REJECTED",
        ]

        terminal_rows = list(
            db.execute(
                text(
                    """
                    select resolution_status, is_active
                    from geography_project_village_resolutions
                    where id = any(cast(:ids as uuid[]))
                    order by created_at
                    """
                ),
                {"ids": [str(value) for value in created_ids]},
            ).mappings()
        )
        assert len(terminal_rows) == 3
        assert all(
            row["resolution_status"] == "REJECTED" and row["is_active"] is False
            for row in terminal_rows
        )
        assert protected_snapshot(db) == before

        print(
            {
                "schema_version": "project_village_resolution_terminal_review_test.v1",
                "cancellation_actions": actions(db, cancellation_id),
                "draft_rejection_actions": actions(db, draft_rejection_id),
                "approved_rejection_actions": actions(db, approved_rejection_id),
                "non_proposer_cancellation_rejected": True,
                "self_rejection_rejected": True,
                "activation_gate": False,
                "all_terminal_rows_inactive": True,
                "global_geography_unchanged": True,
                "android_visible": False,
            }
        )
    finally:
        settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED = original_gate
        if created_ids:
            db.execute(
                text(
                    "delete from geography_project_village_resolution_events "
                    "where resolution_id = any(cast(:ids as uuid[]))"
                ),
                {"ids": [str(value) for value in created_ids]},
            )
            db.execute(
                text(
                    "delete from geography_project_village_resolutions "
                    "where id = any(cast(:ids as uuid[]))"
                ),
                {"ids": [str(value) for value in created_ids]},
            )
            db.commit()
        delete_test_admin(db, proposer.id)
        delete_test_admin(db, reviewer.id)

print("PROJECT VILLAGE RESOLUTION TERMINAL REVIEW WORKFLOW PASSED")
