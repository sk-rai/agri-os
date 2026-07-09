"""Regression for agricultural input draft/review/publish governance."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.core.database import SessionLocal
from app.main import app
from app.modules.master_data.models import AgriculturalInput, AgriculturalInputAuditEvent
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

CODES = ["LIFECYCLE_REGRESSION_A", "LIFECYCLE_REGRESSION_B"]


def check(value, label):
    if not value: raise AssertionError(label)
    print(f"  OK  {label}")


def cleanup(db, users=()):
    db.query(AgriculturalInputAuditEvent).filter(AgriculturalInputAuditEvent.input_code.in_(CODES)).delete(synchronize_session=False)
    db.query(AgriculturalInput).filter(AgriculturalInput.code.in_(CODES)).delete(synchronize_session=False)
    db.commit()
    for user in users: delete_test_admin(db, user.id)


def main():
    db = SessionLocal()
    editor, editor_headers = create_test_admin(db, role="AGRONOMIST")
    publisher, publisher_headers = create_test_admin(db, role="ADMIN_PUBLISHER")
    cleanup(db)
    editor_client = TestClient(app, headers=editor_headers)
    publisher_client = TestClient(app, headers=publisher_headers)
    try:
        created = editor_client.post("/api/v1/input-catalog/inputs", json={"code": CODES[0], "category_code": "FERTILIZER", "canonical_name": "Lifecycle Duplicate", "unit": "kg", "composition": "N test"})
        check(created.status_code == 200 and created.json()["catalog_status"] == "DRAFT", "new input starts DRAFT")
        runtime = editor_client.get(f"/api/v1/input-catalog/inputs?q={CODES[0]}")
        check(runtime.json()["count"] == 0, "draft is hidden from runtime catalog")
        public_unpublished = TestClient(app).get(f"/api/v1/input-catalog/inputs?q={CODES[0]}&include_unpublished=true")
        check(public_unpublished.status_code == 403, "public caller cannot request unpublished inputs")
        admin = editor_client.get(f"/api/v1/input-catalog/inputs?q={CODES[0]}&include_unpublished=true")
        check(admin.json()["count"] == 1, "admin can explicitly list unpublished input")
        report = editor_client.get(f"/api/v1/input-catalog/inputs/{CODES[0]}/governance").json()
        check(not report["validation"]["can_submit"], "missing crop scope blocks review")
        blocked = editor_client.post(f"/api/v1/input-catalog/inputs/{CODES[0]}/submit-review", json={"reason": "Ready for review"})
        check(blocked.status_code == 409, "blocking validation prevents submit")
        fixed = editor_client.put(f"/api/v1/input-catalog/inputs/{CODES[0]}", json={"applicable_crops": ["RICE"], "change_reason": "Add crop scope"})
        check(fixed.status_code == 200 and fixed.json()["catalog_status"] == "DRAFT", "editor fix remains draft")
        submitted = editor_client.post(f"/api/v1/input-catalog/inputs/{CODES[0]}/submit-review", json={"reason": "Agronomist review complete"})
        check(submitted.status_code == 200 and submitted.json()["input"]["catalog_status"] == "REVIEW", "editor submits for review")
        denied = editor_client.post(f"/api/v1/input-catalog/inputs/{CODES[0]}/publish", json={"reason": "Unauthorized publish"})
        check(denied.status_code == 403, "editor cannot publish")
        published = publisher_client.post(f"/api/v1/input-catalog/inputs/{CODES[0]}/publish", json={"reason": "Publisher approval"})
        check(published.status_code == 200 and published.json()["input"]["catalog_status"] == "PUBLISHED", "publisher approves reviewed input")
        runtime = editor_client.get(f"/api/v1/input-catalog/inputs?q={CODES[0]}")
        check(runtime.json()["count"] == 1, "published input appears in runtime catalog")

        duplicate = editor_client.post("/api/v1/input-catalog/inputs", json={"code": CODES[1], "category_code": "FERTILIZER", "canonical_name": "Lifecycle Duplicate", "unit": "kg", "composition": "N test", "applicable_crops": ["RICE"]})
        check(duplicate.status_code == 200, "second candidate is created")
        dup_report = editor_client.get(f"/api/v1/input-catalog/inputs/{CODES[1]}/governance").json()["validation"]
        check(dup_report["counts"]["duplicates"] == 1 and any(x["code"] == "POSSIBLE_DUPLICATE" for x in dup_report["warnings"]), "possible duplicate is reported")
        match_reasons = set(dup_report["duplicate_candidates"][0]["duplicate_match_reasons"])
        check({"CANONICAL_NAME", "COMPOSITION"}.issubset(match_reasons), "duplicate report explains name and composition matches")
        editor_client.post(f"/api/v1/input-catalog/inputs/{CODES[1]}/submit-review", json={"reason": "Submit duplicate candidate"})
        rejected = publisher_client.post(f"/api/v1/input-catalog/inputs/{CODES[1]}/reject", json={"reason": "Duplicate of lifecycle A"})
        check(rejected.status_code == 200 and rejected.json()["input"]["catalog_status"] == "REJECTED", "publisher can reject with reason")
        audit = editor_client.get(f"/api/v1/input-catalog/inputs/{CODES[0]}/audit").json()["events"]
        actions = {event["action"] for event in audit}
        check({"SUBMIT_INPUT_REVIEW", "PUBLISH_INPUT"}.issubset(actions), "submit and publish are audited")
        check(any(event.get("reason") == "Publisher approval" for event in audit), "reviewer reason is audited")
        print("PASS")
    finally:
        cleanup(db, (editor, publisher))
        db.close()


if __name__ == "__main__": main()