"""Regression for cloning published workflow versions into draft versions."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.modules.workflow.models import (
    WorkflowTemplate,
    WorkflowTemplateAuditEvent,
    WorkflowTemplateRecommendation,
    WorkflowTemplateStage,
    WorkflowTemplateVersion,
)

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
TENANT_ID = "default"


def check(condition, label, detail=None):
    icon = f"{GREEN}?{RESET}" if condition else f"{RED}?{RESET}"
    print(f"  {icon} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def cleanup_draft(db, draft_version_id):
    if not draft_version_id:
        return
    db.query(WorkflowTemplateAuditEvent).filter(
        WorkflowTemplateAuditEvent.template_version_id == draft_version_id
    ).delete(synchronize_session=False)
    stage_ids = [
        row.id
        for row in db.query(WorkflowTemplateStage.id)
        .filter(WorkflowTemplateStage.template_version_id == draft_version_id)
        .all()
    ]
    if stage_ids:
        db.query(WorkflowTemplateRecommendation).filter(
            WorkflowTemplateRecommendation.template_stage_id.in_(stage_ids)
        ).delete(synchronize_session=False)
        db.query(WorkflowTemplateStage).filter(
            WorkflowTemplateStage.id.in_(stage_ids)
        ).delete(synchronize_session=False)
    db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == draft_version_id).delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("WORKFLOW DRAFT CLONE REGRESSION")
    print("=" * 72)

    db = SessionLocal()
    draft_version_id = None
    restored_draft_id = None
    source_version_id = None
    source_effective_to = None
    try:
        rice = db.query(WorkflowTemplate).filter(WorkflowTemplate.code == "WF_RICE_KHARIF_DEFAULT").first()
        check(rice is not None, "Rice workflow template exists")
        source_version = db.query(WorkflowTemplateVersion).filter(
            WorkflowTemplateVersion.template_id == rice.id,
            WorkflowTemplateVersion.status == "PUBLISHED",
            WorkflowTemplateVersion.is_active == True,
        ).first()
        check(source_version is not None, "Published source version exists")
        source_version_id = source_version.id
        source_effective_to = source_version.effective_to

        source_stages = db.query(WorkflowTemplateStage).filter(
            WorkflowTemplateStage.template_version_id == source_version.id,
            WorkflowTemplateStage.is_active == True,
        ).all()
        source_stage_ids = [stage.id for stage in source_stages]
        source_recommendation_count = db.query(WorkflowTemplateRecommendation).filter(
            WorkflowTemplateRecommendation.template_stage_id.in_(source_stage_ids),
            WorkflowTemplateRecommendation.is_active == True,
        ).count()

        client = TestClient(app)
        headers = {"X-Tenant-ID": TENANT_ID}
        catalog_before = client.get("/api/v1/workflow-catalog/enabled-crop-workflows", headers=headers)
        check(catalog_before.status_code == 200, "Published catalog before clone returns 200", f"Status: {catalog_before.status_code}")
        ids_before = {item["workflow_template_version_id"] for item in catalog_before.json()["workflows"]}

        clone = client.post(
            f"/api/v1/workflow-catalog/templates/{rice.id}/versions/{source_version.id}/clone-draft",
            headers=headers,
            json={"version_number": f"{source_version.version_number}-codex-draft-test"},
        )
        check(clone.status_code == 200, "Clone draft endpoint returns 200", f"Status: {clone.status_code}")
        payload = clone.json()
        draft_version_id = payload["draft_version_id"]
        check(payload["source_version_id"] == str(source_version.id), "Response references source version")
        check(payload["workflow_template_id"] == str(rice.id), "Response references template")
        check(payload["status"] == "DRAFT", "Draft status returned")
        check(payload["stage_count"] == len(source_stages), "Stage count copied")
        check(payload["recommendation_count"] == source_recommendation_count, "Recommendation count copied")

        draft = db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == draft_version_id).first()
        check(draft is not None, "Draft version exists in database")
        check(draft.status == "DRAFT", "Database draft status is DRAFT")
        check(draft.published_at is None, "Draft is not published")
        check(draft.metadata_["source_version_id"] == str(source_version.id), "Draft metadata stores source version")

        draft_stages = db.query(WorkflowTemplateStage).filter(WorkflowTemplateStage.template_version_id == draft.id).all()
        check(len(draft_stages) == len(source_stages), "Draft stages copied to new version")
        check(all(stage.template_version_id == draft.id for stage in draft_stages), "Draft stages point at draft version")
        draft_stage_ids = [stage.id for stage in draft_stages]
        draft_rec_count = db.query(WorkflowTemplateRecommendation).filter(
            WorkflowTemplateRecommendation.template_stage_id.in_(draft_stage_ids)
        ).count()
        check(draft_rec_count == source_recommendation_count, "Draft recommendations copied to draft stages")

        catalog_after = client.get("/api/v1/workflow-catalog/enabled-crop-workflows", headers=headers)
        check(catalog_after.status_code == 200, "Published catalog after clone returns 200", f"Status: {catalog_after.status_code}")
        ids_after = {item["workflow_template_version_id"] for item in catalog_after.json()["workflows"]}
        check(draft_version_id not in ids_after, "Draft is excluded from Android-facing enabled catalog")
        check(ids_before == ids_after, "Published catalog version set is unchanged by draft clone")

        draft_preview = client.get(f"/api/v1/workflow-catalog/workflow-preview/{draft_version_id}", headers=headers)
        check(draft_preview.status_code == 404, "Published preview endpoint does not serve draft versions", f"Status: {draft_preview.status_code}")

        admin_draft_preview = client.get(f"/api/v1/workflow-catalog/draft-preview/{draft_version_id}", headers=headers)
        check(admin_draft_preview.status_code == 200, "Admin draft preview endpoint returns 200", f"Status: {admin_draft_preview.status_code}")
        draft_preview_payload = admin_draft_preview.json()
        check(draft_preview_payload["status"] == "DRAFT", "Admin draft preview reports DRAFT status")
        check(draft_preview_payload["preview_source"] == "workflow_template_draft", "Admin draft preview source is explicit")
        check(draft_preview_payload["enablement_source"] == "draft_admin_preview", "Admin draft preview is not Android enablement sourced")
        check(len(draft_preview_payload["android_preview"]["stages"]) == len(source_stages), "Admin draft preview renders copied stages")
        draft_preview_rec_count = sum(
            len(stage.get("recommended_activities", []))
            for stage in draft_preview_payload["android_preview"]["stages"]
        )
        check(draft_preview_rec_count == source_recommendation_count, "Admin draft preview renders copied recommendations")

        patch_stage = client.patch(
            f"/api/v1/workflow-catalog/drafts/{draft_version_id}/stages/NURSERY",
            headers=headers,
            json={
                "stage_name": {"en": "Custom Nursery Draft", "hi": "Custom Nursery Draft"},
                "duration_days": 19,
                "description": {"en": "Draft-stage edited nursery description"},
                "farmer_actions": ["BED_PREPARATION", "SEED_TREATMENT"],
                "key_observations": ["GERMINATION_RATE"],
            },
        )
        check(patch_stage.status_code == 200, "Draft stage patch returns 200", f"Status: {patch_stage.status_code}")
        patched_payload = patch_stage.json()
        patched_nursery = next(stage for stage in patched_payload["android_preview"]["stages"] if stage["code"] == "NURSERY")
        check(patched_nursery["name"]["en"] == "Custom Nursery Draft", "Draft stage name is updated")
        check(patched_nursery["duration_days"] == 19, "Draft stage duration is updated")
        check(patched_nursery["description"]["en"] == "Draft-stage edited nursery description", "Draft stage description is updated")
        check(patched_nursery["farmer_actions"] == ["BED_PREPARATION", "SEED_TREATMENT"], "Draft stage farmer actions are updated")
        check(patched_payload["status"] == "DRAFT", "Patch response remains draft preview")

        db.expire_all()
        draft_after_patch = db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == draft_version_id).first()
        check(draft_after_patch.total_duration_days == patched_payload["total_duration_days"], "Draft total duration is recalculated")

        patch_published = client.patch(
            f"/api/v1/workflow-catalog/drafts/{source_version.id}/stages/NURSERY",
            headers=headers,
            json={"duration_days": 99},
        )
        check(patch_published.status_code == 404, "Published version cannot be edited through draft stage API", f"Status: {patch_published.status_code}")

        patch_negative = client.patch(
            f"/api/v1/workflow-catalog/drafts/{draft_version_id}/stages/NURSERY",
            headers=headers,
            json={"duration_days": -1},
        )
        check(patch_negative.status_code == 400, "Draft stage rejects negative duration", f"Status: {patch_negative.status_code}")

        nursery_recs = patched_nursery.get("recommended_activities", [])
        check(len(nursery_recs) > 0, "Draft nursery has recommendations to edit")
        editable_rec = nursery_recs[0]
        editable_rec_id = editable_rec["metadata"]["recommendation_id"]

        patch_rec = client.patch(
            f"/api/v1/workflow-catalog/drafts/{draft_version_id}/recommendations/{editable_rec_id}",
            headers=headers,
            json={
                "input_name": "Edited FYM/Compost Draft",
                "day_offset": 3,
                "typical_quantity": "4 quintal/acre",
                "typical_cost_per_acre": 750,
                "is_critical": False,
                "description": {"en": "Edited draft recommendation description"},
            },
        )
        check(patch_rec.status_code == 200, "Draft recommendation patch returns 200", f"Status: {patch_rec.status_code}")
        patched_rec_payload = patch_rec.json()
        patched_rec_nursery = next(stage for stage in patched_rec_payload["android_preview"]["stages"] if stage["code"] == "NURSERY")
        edited_rec = next(rec for rec in patched_rec_nursery["recommended_activities"] if rec["metadata"]["recommendation_id"] == editable_rec_id)
        check(edited_rec["input_name"] == "Edited FYM/Compost Draft", "Draft recommendation name is updated")
        check(edited_rec["day_offset"] == 3, "Draft recommendation offset is updated")
        check(edited_rec["typical_quantity"] == "4 quintal/acre", "Draft recommendation quantity is updated")
        check(edited_rec["typical_cost_per_acre"] == 750, "Draft recommendation cost is updated")
        check(edited_rec["description"]["en"] == "Edited draft recommendation description", "Draft recommendation description is updated")

        patch_rec_published = client.patch(
            f"/api/v1/workflow-catalog/drafts/{source_version.id}/recommendations/{editable_rec_id}",
            headers=headers,
            json={"input_name": "Should not update"},
        )
        check(patch_rec_published.status_code == 404, "Published version cannot be edited through draft recommendation API", f"Status: {patch_rec_published.status_code}")

        patch_rec_empty_name = client.patch(
            f"/api/v1/workflow-catalog/drafts/{draft_version_id}/recommendations/{editable_rec_id}",
            headers=headers,
            json={"input_name": ""},
        )
        check(patch_rec_empty_name.status_code == 400, "Draft recommendation rejects empty input name", f"Status: {patch_rec_empty_name.status_code}")

        add_rec = client.post(
            f"/api/v1/workflow-catalog/drafts/{draft_version_id}/stages/NURSERY/recommendations",
            headers=headers,
            json={
                "day_offset": 5,
                "activity_type": "LABOR",
                "input_code": "LABOR_GENERAL",
                "input_name": "Draft custom labour",
                "typical_quantity": "1 labour-day/acre",
                "is_critical": False,
                "description": {"en": "Draft-only labour recommendation"},
            },
        )
        check(add_rec.status_code == 200, "Draft recommendation create returns 200", f"Status: {add_rec.status_code}")
        add_rec_payload = add_rec.json()
        add_rec_nursery = next(stage for stage in add_rec_payload["android_preview"]["stages"] if stage["code"] == "NURSERY")
        added_rec = next(rec for rec in add_rec_nursery["recommended_activities"] if rec["input_name"] == "Draft custom labour")
        added_rec_id = added_rec["metadata"]["recommendation_id"]
        check(added_rec["input_code"] == "LABOR_GENERAL", "Created draft recommendation keeps input code")
        check(added_rec["day_offset"] == 5, "Created draft recommendation keeps day offset")

        delete_rec = client.delete(
            f"/api/v1/workflow-catalog/drafts/{draft_version_id}/recommendations/{added_rec_id}",
            headers=headers,
        )
        check(delete_rec.status_code == 200, "Draft recommendation delete returns 200", f"Status: {delete_rec.status_code}")
        delete_rec_payload = delete_rec.json()
        delete_rec_nursery = next(stage for stage in delete_rec_payload["android_preview"]["stages"] if stage["code"] == "NURSERY")
        check(
            all(rec["metadata"]["recommendation_id"] != added_rec_id for rec in delete_rec_nursery["recommended_activities"]),
            "Deleted draft recommendation is removed from preview",
        )

        validation = client.get(f"/api/v1/workflow-catalog/drafts/{draft_version_id}/validation", headers=headers)
        check(validation.status_code == 200, "Draft validation report returns 200", f"Status: {validation.status_code}")
        validation_payload = validation.json()
        check(validation_payload["workflow_template_version_id"] == draft_version_id, "Validation report references draft version")
        check(validation_payload["can_publish"] is True, "Validation report allows publishable draft")
        check("ERROR" in validation_payload["issues_by_level"], "Validation report groups errors")
        check(validation_payload["counts"]["stages"] == len(delete_rec_payload["android_preview"]["stages"]), "Validation report includes stage count")

        publish = client.post(
            f"/api/v1/workflow-catalog/drafts/{draft_version_id}/publish",
            headers=headers,
            json={"archive_previous": True},
        )
        check(publish.status_code == 200, "Draft publish returns 200", f"Status: {publish.status_code}")
        publish_payload = publish.json()
        check(publish_payload["status"] == "PUBLISHED", "Publish response marks version as PUBLISHED")
        check(publish_payload["workflow_template_version_id"] == draft_version_id, "Publish response references draft version")
        check(publish_payload["preview_source"] == "workflow_template_published", "Publish response is published preview")

        db.expire_all()
        published_draft = db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == draft_version_id).first()
        archived_source = db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == source_version.id).first()
        check(published_draft.status == "PUBLISHED", "Draft row becomes PUBLISHED in database")
        check(published_draft.published_at is not None, "Published draft stores published_at")
        check(archived_source.status == "ARCHIVED", "Previous published version is archived")

        catalog_after_publish = client.get("/api/v1/workflow-catalog/enabled-crop-workflows", headers=headers)
        check(catalog_after_publish.status_code == 200, "Published catalog after publish returns 200", f"Status: {catalog_after_publish.status_code}")
        rice_versions_after_publish = [
            item["workflow_template_version_id"]
            for item in catalog_after_publish.json()["workflows"]
            if item["workflow_template_id"] == str(rice.id)
        ]
        check(rice_versions_after_publish == [draft_version_id], "Android catalog serves the newly published version once")

        old_preview = client.get(f"/api/v1/workflow-catalog/workflow-preview/{source_version.id}", headers=headers)
        check(old_preview.status_code == 404, "Archived source version is no longer Android-preview visible", f"Status: {old_preview.status_code}")
        new_preview = client.get(f"/api/v1/workflow-catalog/workflow-preview/{draft_version_id}", headers=headers)
        check(new_preview.status_code == 200, "Newly published draft is Android-preview visible", f"Status: {new_preview.status_code}")

        draft_edit_after_publish = client.patch(
            f"/api/v1/workflow-catalog/drafts/{draft_version_id}/stages/NURSERY",
            headers=headers,
            json={"duration_days": 20},
        )
        check(draft_edit_after_publish.status_code == 404, "Published draft cannot be edited through draft APIs", f"Status: {draft_edit_after_publish.status_code}")

        versions = client.get(f"/api/v1/workflow-catalog/templates/{rice.id}/versions", headers=headers)
        check(versions.status_code == 200, "Workflow version history returns 200", f"Status: {versions.status_code}")
        versions_payload = versions.json()
        check(versions_payload["current_published_version_id"] == draft_version_id, "Version history marks newly published version active")
        statuses_by_id = {item["workflow_template_version_id"]: item["status"] for item in versions_payload["versions"]}
        check(statuses_by_id[draft_version_id] == "PUBLISHED", "Version history includes published draft")
        check(statuses_by_id[str(source_version.id)] == "ARCHIVED", "Version history includes archived source")
        active_rows = [item for item in versions_payload["versions"] if item["is_current_published"]]
        check(len(active_rows) == 1 and active_rows[0]["workflow_template_version_id"] == draft_version_id, "Exactly one version is Android active")

        restore = client.post(
            f"/api/v1/workflow-catalog/templates/{rice.id}/versions/{source_version.id}/restore-draft",
            headers=headers,
            json={"version_number": f"{source_version.version_number}-codex-restore-test"},
        )
        check(restore.status_code == 200, "Restore archived version to draft returns 200", f"Status: {restore.status_code}")
        restore_payload = restore.json()
        restored_draft_id = restore_payload["draft_version_id"]
        check(restore_payload["source_version_id"] == str(source_version.id), "Restore response references archived source")
        check(restore_payload["status"] == "DRAFT", "Restore creates a DRAFT")

        restored_preview = client.get(f"/api/v1/workflow-catalog/draft-preview/{restored_draft_id}", headers=headers)
        check(restored_preview.status_code == 200, "Restored draft preview returns 200", f"Status: {restored_preview.status_code}")
        restored_public_preview = client.get(f"/api/v1/workflow-catalog/workflow-preview/{restored_draft_id}", headers=headers)
        check(restored_public_preview.status_code == 404, "Restored draft is not Android-preview visible", f"Status: {restored_public_preview.status_code}")

        audit = client.get(f"/api/v1/workflow-catalog/templates/{rice.id}/audit", headers=headers)
        check(audit.status_code == 200, "Workflow audit trail returns 200", f"Status: {audit.status_code}")
        audit_payload = audit.json()
        check(audit_payload["workflow_template_id"] == str(rice.id), "Audit response references workflow template")
        audit_actions = [event["action"] for event in audit_payload["events"]]
        for action in [
            "CLONE_DRAFT",
            "UPDATE_STAGE",
            "UPDATE_RECOMMENDATION",
            "CREATE_RECOMMENDATION",
            "DELETE_RECOMMENDATION",
            "VALIDATE_DRAFT",
            "PUBLISH_DRAFT",
            "RESTORE_DRAFT",
        ]:
            check(action in audit_actions, f"Audit trail records {action}")
        update_stage_event = next(event for event in audit_payload["events"] if event["action"] == "UPDATE_STAGE" and event["workflow_template_version_id"] == draft_version_id)
        check(update_stage_event["before"]["stage_code"] == "NURSERY", "Stage audit captures before snapshot")
        check(update_stage_event["after"]["duration_days"] == 19, "Stage audit captures after snapshot")
        publish_event = next(event for event in audit_payload["events"] if event["action"] == "PUBLISH_DRAFT" and event["workflow_template_version_id"] == draft_version_id)
        check(publish_event["metadata"]["validation_counts"]["stages"] > 0, "Publish audit stores validation counts")
    finally:
        if source_version_id:
            source = db.query(WorkflowTemplateVersion).filter(WorkflowTemplateVersion.id == source_version_id).first()
            if source:
                source.status = "PUBLISHED"
                source.effective_to = source_effective_to
                db.commit()
        cleanup_draft(db, restored_draft_id)
        cleanup_draft(db, draft_version_id)
        db.close()

    print("\n" + "=" * 72)
    print("Workflow draft clone validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
