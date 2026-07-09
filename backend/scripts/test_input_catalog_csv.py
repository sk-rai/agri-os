"""Regression coverage for input catalog CSV dry-run and audited apply."""

import csv
from io import StringIO
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.master_data.models import AgriculturalInput, AgriculturalInputAuditEvent, InputCatalogImportBatch
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

CODE = "CSV_REGRESSION_INPUT"
FILE_NAME = "csv-regression.csv"


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"  OK  {label}")


def csv_bytes(composition="Regression composition"):
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=[
        "code", "category_code", "canonical_name", "brand_name", "composition",
        "unit", "standard_weight", "applicable_crops", "application_method",
        "safety_instructions", "aliases_json",
    ])
    writer.writeheader()
    writer.writerow({
        "code": CODE,
        "category_code": "FERTILIZER",
        "canonical_name": "CSV Regression Input",
        "composition": composition,
        "unit": "kg",
        "standard_weight": "1.5",
        "applicable_crops": "RICE|WHEAT",
        "aliases_json": "[]",
    })
    return output.getvalue().encode()


def cleanup(db, *user_ids):
    db.query(AgriculturalInputAuditEvent).filter(AgriculturalInputAuditEvent.input_code == CODE).delete(synchronize_session=False)
    db.query(AgriculturalInput).filter(AgriculturalInput.code == CODE).delete(synchronize_session=False)
    db.query(InputCatalogImportBatch).filter(InputCatalogImportBatch.file_name == FILE_NAME).delete(synchronize_session=False)
    db.commit()
    for user_id in user_ids:
        delete_test_admin(db, user_id)


def main():
    print("INPUT CATALOG CSV REGRESSION")
    db = SessionLocal()
    editor, editor_headers = create_test_admin(db, role="AGRONOMIST")
    viewer, viewer_headers = create_test_admin(db, role="ADMIN_VIEWER")
    cleanup_ids = (editor.id, viewer.id)
    try:
        db.query(AgriculturalInputAuditEvent).filter(AgriculturalInputAuditEvent.input_code == CODE).delete(synchronize_session=False)
        db.query(AgriculturalInput).filter(AgriculturalInput.code == CODE).delete(synchronize_session=False)
        db.query(InputCatalogImportBatch).filter(InputCatalogImportBatch.file_name == FILE_NAME).delete(synchronize_session=False)
        db.commit()

        viewer_client = TestClient(app, headers=viewer_headers)
        check(viewer_client.get("/api/v1/input-catalog/csv/template").status_code == 200, "viewer can download template")
        check(viewer_client.get("/api/v1/input-catalog/csv/export").status_code == 200, "viewer can export catalog")
        denied = viewer_client.post("/api/v1/input-catalog/csv/validate", files={"file": (FILE_NAME, csv_bytes(), "text/csv")})
        check(denied.status_code == 403, "viewer cannot validate an import")

        client = TestClient(app, headers=editor_headers)
        invalid_csv = csv_bytes().decode().replace("FERTILIZER", "UNKNOWN_CATEGORY")
        invalid = client.post("/api/v1/input-catalog/csv/validate", files={"file": (FILE_NAME, invalid_csv.encode(), "text/csv")})
        check(invalid.status_code == 200, "invalid CSV returns a validation report")
        check(invalid.json()["status"] == "INVALID" and not invalid.json()["can_apply"], "invalid batch cannot be applied")
        check(invalid.json()["report"]["rows"][0]["errors"][0]["code"] == "UNKNOWN_CATEGORY", "row diagnostic identifies unknown category")

        validated = client.post("/api/v1/input-catalog/csv/validate", files={"file": (FILE_NAME, csv_bytes(), "text/csv")})
        check(validated.status_code == 200, "valid CSV dry-run returns 200")
        payload = validated.json()
        check(payload["status"] == "VALIDATED" and payload["report"]["counts"]["create"] == 1, "dry-run reports one create")
        db.expire_all()
        check(db.query(AgriculturalInput).filter(AgriculturalInput.code == CODE).first() is None, "dry-run does not mutate catalog")

        applied = client.post(f"/api/v1/input-catalog/csv/imports/{payload['batch_id']}/apply", json={"reason": "CSV regression create"})
        check(applied.status_code == 200 and applied.json()["status"] == "APPLIED", "validated batch applies once")
        check(applied.json()["report"]["applied_counts"]["created"] == 1, "apply reports one create")
        repeat = client.post(f"/api/v1/input-catalog/csv/imports/{payload['batch_id']}/apply", json={"reason": "CSV regression repeat"})
        check(repeat.status_code == 409, "applied batch cannot be replayed")

        update_batch = client.post("/api/v1/input-catalog/csv/validate", files={"file": (FILE_NAME, csv_bytes("Updated composition"), "text/csv")}).json()
        check(update_batch["report"]["counts"]["update"] == 1, "second dry-run reports one update")
        updated = client.post(f"/api/v1/input-catalog/csv/imports/{update_batch['batch_id']}/apply", json={"reason": "CSV regression update"})
        check(updated.status_code == 200 and updated.json()["report"]["applied_counts"]["updated"] == 1, "update batch applies")
        db.expire_all()
        item = db.query(AgriculturalInput).filter(AgriculturalInput.code == CODE).one()
        check(item.composition == "Updated composition", "updated value is persisted")
        actions = {row.action for row in db.query(AgriculturalInputAuditEvent).filter(AgriculturalInputAuditEvent.input_code == CODE).all()}
        check({"IMPORT_CREATE_INPUT", "IMPORT_UPDATE_INPUT"}.issubset(actions), "create and update are audited")
        history = client.get("/api/v1/input-catalog/csv/imports")
        check(history.status_code == 200 and history.json()["count"] >= 2, "import history is available")
        print("PASS")
    finally:
        cleanup(db, *cleanup_ids)
        db.close()


if __name__ == "__main__":
    main()