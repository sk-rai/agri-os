"""Regression for crop propagation CSV import workflow."""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.master_data.models import CropPropagationImportBatch
from app.modules.master_data.models.crop import CropPropagationType
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def check(condition: bool, label: str, detail=None):
    icon = f"{GREEN}?{RESET}" if condition else f"{RED}?{RESET}"
    print(f"  {icon} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def upload_csv(client: TestClient, content: str):
    return client.post(
        "/api/v1/crop-catalog/csv/propagation-types/validate",
        files={"file": ("propagation.csv", io.BytesIO(content.encode("utf-8")), "text/csv")},
    )


def cleanup(db):
    db.query(CropPropagationType).filter(CropPropagationType.code == "REGRESSION_PROPAGATION").delete(synchronize_session=False)
    db.query(CropPropagationImportBatch).filter(CropPropagationImportBatch.file_name == "propagation.csv").delete(synchronize_session=False)
    db.commit()


def main():
    print("=" * 72)
    print("CROP PROPAGATION CSV REGRESSION")
    print("=" * 72)

    anonymous = TestClient(app)
    denied = anonymous.post(
        "/api/v1/crop-catalog/csv/propagation-types/validate",
        files={"file": ("propagation.csv", b"code,canonical_name,establishment_type\n", "text/csv")},
    )
    check(denied.status_code == 401, "propagation validation requires admin authentication", denied.text)

    db = SessionLocal()
    cleanup(db)
    admin, headers = create_test_admin(db)
    try:
        client = TestClient(app, headers=headers)

        template = client.get("/api/v1/crop-catalog/csv/propagation-types/template")
        check(template.status_code == 200, "viewer can download propagation template")
        check("establishment_type" in template.text, "template includes establishment_type column")

        export = client.get("/api/v1/crop-catalog/csv/propagation-types/export")
        check(export.status_code == 200, "viewer can export propagation catalog")
        check("DIRECT_SEEDED" in export.text, "export includes seeded propagation rows")

        missing = upload_csv(client, "code,canonical_name\nBAD,Bad\n")
        check(missing.status_code == 400, "missing required columns returns 400", missing.text)
        check("MISSING_COLUMNS" in missing.text, "missing column response identifies contract error")

        invalid_csv = """code,canonical_name,establishment_type,description,aliases_json,metadata_json\nBAD PROP,Bad Propagation,UNKNOWN,Invalid row,not-json,[]\n"""
        invalid = upload_csv(client, invalid_csv)
        check(invalid.status_code == 200, "invalid propagation rows return validation report", invalid.text)
        invalid_report = invalid.json()
        check(invalid_report["schema_version"] == "crop_propagation_csv_validation.v1", "validation schema version is stable")
        check(invalid_report["status"] == "INVALID", "invalid validation batch is persisted as INVALID")
        error_codes = {error["code"] for error in invalid_report["rows"][0]["errors"]}
        check({"INVALID_ESTABLISHMENT_TYPE", "INVALID_JSON"}.issubset(error_codes), "invalid row reports expected errors", sorted(error_codes))

        valid_csv = """code,canonical_name,establishment_type,description,aliases_json,metadata_json\nREGRESSION_PROPAGATION,Regression Propagation,VEGETATIVE,Regression propagation type,[],{"source":"regression"}\n"""
        valid = upload_csv(client, valid_csv)
        check(valid.status_code == 200, "valid propagation dry-run returns 200", valid.text)
        report = valid.json()
        check(report["can_apply"], "valid propagation report can apply")
        check(report["status"] == "VALIDATED", "valid propagation batch is persisted as VALIDATED")
        check(report["file_name"] == "propagation.csv", "valid propagation report includes uploaded file name")
        check(bool(report.get("batch_id")), "valid propagation report includes import batch id")
        required_summary_keys = {"total", "create", "update", "unchanged", "invalid", "errors", "warnings"}
        check(required_summary_keys.issubset(set(report["summary"].keys())), "valid propagation report exposes admin summary contract", sorted(report["summary"].keys()))
        check(report["summary"]["total"] == 1, "valid dry-run reports one uploaded row")
        check(report["summary"]["invalid"] == 0, "valid dry-run reports zero invalid rows")
        check(report["summary"]["create"] == 1, "valid dry-run reports one create")
        check(report["summary"]["errors"] == 0, "valid dry-run reports zero errors")

        apply_response = client.post(
            f"/api/v1/crop-catalog/csv/propagation-types/imports/{report['batch_id']}/apply",
            json={"reason": "Regression propagation apply"},
        )
        check(apply_response.status_code == 200, "validated propagation batch applies", apply_response.text)
        applied = apply_response.json()
        check(applied["status"] == "APPLIED", "applied propagation batch is marked APPLIED")
        check(applied["batch_id"] == report["batch_id"], "applied propagation response echoes batch id")
        required_applied_counts = {"created", "updated", "unchanged"}
        check(required_applied_counts.issubset(set(applied["report"]["applied_counts"].keys())), "applied propagation response exposes applied count contract", sorted(applied["report"]["applied_counts"].keys()))
        check(applied["report"]["applied_counts"]["created"] == 1, "apply creates one propagation type")
        check(applied["report"]["applied_counts"]["updated"] == 0, "apply reports zero updates")
        created = db.query(CropPropagationType).filter(CropPropagationType.code == "REGRESSION_PROPAGATION").first()
        check(created is not None and created.establishment_type == "VEGETATIVE", "applied propagation type exists in database")

        replay = client.post(
            f"/api/v1/crop-catalog/csv/propagation-types/imports/{report['batch_id']}/apply",
            json={"reason": "Replay should fail"},
        )
        check(replay.status_code == 409, "applied propagation batch cannot be replayed", replay.text)

        duplicate_csv = valid_csv + "REGRESSION_PROPAGATION,Duplicate Propagation,VEGETATIVE,Duplicate row,[],{}\n"
        duplicate = upload_csv(client, duplicate_csv)
        check(duplicate.status_code == 200, "duplicate code returns validation report")
        duplicate_codes = {error["code"] for row in duplicate.json()["rows"] for error in row["errors"]}
        check("DUPLICATE_CODE_IN_FILE" in duplicate_codes, "duplicate code in file is reported")
        invalid_apply = client.post(
            f"/api/v1/crop-catalog/csv/propagation-types/imports/{duplicate.json()['batch_id']}/apply",
            json={"reason": "Invalid batch should fail"},
        )
        check(invalid_apply.status_code == 409, "invalid propagation batch cannot be applied", invalid_apply.text)

        history = client.get("/api/v1/crop-catalog/csv/propagation-types/imports?limit=10")
        check(history.status_code == 200, "propagation import history returns 200", history.text)
        history_payload = history.json()
        check(history_payload["schema_version"] == "crop_propagation_imports.v1", "propagation import history schema version is stable")
        batch_ids = {item["batch_id"] for item in history_payload["imports"]}
        check(report["batch_id"] in batch_ids, "history includes valid propagation batch")
        check(invalid_report["batch_id"] in batch_ids, "history includes invalid propagation batch")

        validated_history = client.get("/api/v1/crop-catalog/csv/propagation-types/imports?status=VALIDATED")
        check(validated_history.status_code == 200, "validated propagation import history returns 200")
        check(all(item["status"] == "VALIDATED" for item in validated_history.json()["imports"]), "validated history filters by status")

        print("=" * 72)
        print("Crop propagation CSV import validated")
        print("=" * 72)
    finally:
        cleanup(db)
        delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    main()
