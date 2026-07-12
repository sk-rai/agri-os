"""Regression for crop catalog CSV import workflow."""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.master_data.models import CropCatalogImportBatch
from app.modules.master_data.models.crop import (
    Crop,
    CropCategory,
    CropPropagationOption,
    CropPropagationType,
    CropTaxonomyAssignment,
    CropTaxonomyNode,
)
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
        "/api/v1/crop-catalog/csv/crops/validate",
        files={"file": ("crops.csv", io.BytesIO(content.encode("utf-8")), "text/csv")},
    )


def cleanup(db):
    crop = db.query(Crop).filter(Crop.code == "REGRESSION_CROP").first()
    if crop:
        db.query(CropPropagationOption).filter(CropPropagationOption.crop_id == crop.id).delete(synchronize_session=False)
        db.query(CropTaxonomyAssignment).filter(CropTaxonomyAssignment.crop_id == crop.id).delete(synchronize_session=False)
        db.query(Crop).filter(Crop.id == crop.id).delete(synchronize_session=False)
    db.query(CropCatalogImportBatch).filter(CropCatalogImportBatch.file_name == "crops.csv").delete(synchronize_session=False)
    db.commit()


def pick_reference_codes(db):
    category = db.query(CropCategory).filter(CropCategory.is_active == True).order_by(CropCategory.code).first()
    taxonomy = db.query(CropTaxonomyNode).filter(CropTaxonomyNode.code == "FIELD_CROP", CropTaxonomyNode.is_active == True).first()
    taxonomy = taxonomy or db.query(CropTaxonomyNode).filter(CropTaxonomyNode.is_active == True).order_by(CropTaxonomyNode.code).first()
    propagation = db.query(CropPropagationType).filter(CropPropagationType.code == "DIRECT_SEEDED", CropPropagationType.is_active == True).first()
    propagation = propagation or db.query(CropPropagationType).filter(CropPropagationType.is_active == True).order_by(CropPropagationType.code).first()
    check(category is not None, "seeded crop category exists")
    check(taxonomy is not None, "seeded crop taxonomy node exists")
    check(propagation is not None, "seeded propagation type exists")
    return category.code, taxonomy.code, propagation.code


def main():
    print("=" * 72)
    print("CROP CATALOG CSV REGRESSION")
    print("=" * 72)

    anonymous = TestClient(app)
    denied = anonymous.post(
        "/api/v1/crop-catalog/csv/crops/validate",
        files={"file": ("crops.csv", b"code,category_code,canonical_name\n", "text/csv")},
    )
    check(denied.status_code == 401, "crop validation requires admin authentication", denied.text)

    db = SessionLocal()
    cleanup(db)
    admin, headers = create_test_admin(db)
    try:
        category_code, taxonomy_code, propagation_code = pick_reference_codes(db)
        client = TestClient(app, headers=headers)

        template = client.get("/api/v1/crop-catalog/csv/crops/template")
        check(template.status_code == 200, "viewer can download crop template")
        check("taxonomy_codes" in template.text and "propagation_options" in template.text, "template includes linkage columns")

        export = client.get("/api/v1/crop-catalog/csv/crops/export")
        check(export.status_code == 200, "viewer can export crop catalog")
        check("code,category_code,canonical_name" in export.text, "crop export includes expected headers")

        missing = upload_csv(client, "code,canonical_name\nBAD,Bad\n")
        check(missing.status_code == 400, "missing required columns returns 400", missing.text)
        check("MISSING_COLUMNS" in missing.text, "missing column response identifies contract error")

        invalid_csv = """code,category_code,canonical_name,scientific_name,typical_duration_days,suitable_seasons,suitable_soil_types,taxonomy_codes,primary_taxonomy_code,propagation_options,default_propagation_code,description,aliases_json
BAD-CROP,UNKNOWN,Bad Crop,,abc,KHARIF,LOAM,NO_SUCH,FIELD_CROP,NO_SUCH,DIRECT_SEEDED,Invalid row,not-json
"""
        invalid = upload_csv(client, invalid_csv)
        check(invalid.status_code == 200, "invalid crop rows return validation report", invalid.text)
        invalid_report = invalid.json()
        check(invalid_report["schema_version"] == "crop_catalog_csv_validation.v1", "validation schema version is stable")
        check(invalid_report["status"] == "INVALID", "invalid validation batch is persisted as INVALID")
        error_codes = {error["code"] for error in invalid_report["rows"][0]["errors"]}
        expected_errors = {"INVALID_CODE", "INVALID_INTEGER", "INVALID_JSON", "PRIMARY_NOT_IN_TAXONOMY_CODES", "DEFAULT_NOT_IN_PROPAGATION_OPTIONS", "UNKNOWN_CATEGORY", "UNKNOWN_TAXONOMY", "UNKNOWN_PROPAGATION"}
        check(expected_errors.issubset(error_codes), "invalid crop row reports expected errors", sorted(error_codes))

        valid_csv = f"""code,category_code,canonical_name,scientific_name,typical_duration_days,suitable_seasons,suitable_soil_types,taxonomy_codes,primary_taxonomy_code,propagation_options,default_propagation_code,description,aliases_json
REGRESSION_CROP,{category_code},Regression Crop,Regression crop scientific,120,KHARIF|RABI,LOAM|CLAY,{taxonomy_code},{taxonomy_code},{propagation_code},{propagation_code},Regression crop,[]
"""
        valid = upload_csv(client, valid_csv)
        check(valid.status_code == 200, "valid crop dry-run returns 200", valid.text)
        report = valid.json()
        check(report["can_apply"], "valid crop report can apply")
        check(report["status"] == "VALIDATED", "valid crop batch is persisted as VALIDATED")
        check(report["summary"]["create"] == 1, "valid dry-run reports one create")

        apply_response = client.post(
            f"/api/v1/crop-catalog/csv/crops/imports/{report['batch_id']}/apply",
            json={"reason": "Regression crop apply"},
        )
        check(apply_response.status_code == 200, "validated crop batch applies", apply_response.text)
        applied = apply_response.json()
        check(applied["status"] == "APPLIED", "applied crop batch is marked APPLIED")
        check(applied["report"]["applied_counts"]["created"] == 1, "apply creates one crop")
        check(applied["report"]["applied_counts"]["taxonomy_assignments_created"] == 1, "apply creates taxonomy assignment")
        check(applied["report"]["applied_counts"]["propagation_options_created"] == 1, "apply creates propagation option")

        db.expire_all()
        crop = db.query(Crop).filter(Crop.code == "REGRESSION_CROP").first()
        check(crop is not None and crop.canonical_name == "Regression Crop", "applied crop exists in database")
        assignment = db.query(CropTaxonomyAssignment).filter(CropTaxonomyAssignment.crop_id == crop.id, CropTaxonomyAssignment.is_active == True).first()
        check(assignment is not None and assignment.is_primary, "crop taxonomy assignment is active and primary")
        option = db.query(CropPropagationOption).filter(CropPropagationOption.crop_id == crop.id, CropPropagationOption.is_active == True).first()
        check(option is not None and option.is_default, "crop propagation option is active and default")

        replay = client.post(
            f"/api/v1/crop-catalog/csv/crops/imports/{report['batch_id']}/apply",
            json={"reason": "Replay should fail"},
        )
        check(replay.status_code == 409, "applied crop batch cannot be replayed", replay.text)

        duplicate_csv = valid_csv + f"REGRESSION_CROP,{category_code},Duplicate Crop,,100,KHARIF,LOAM,{taxonomy_code},{taxonomy_code},{propagation_code},{propagation_code},Duplicate row,[]\n"
        duplicate = upload_csv(client, duplicate_csv)
        check(duplicate.status_code == 200, "duplicate crop code returns validation report")
        duplicate_codes = {error["code"] for row in duplicate.json()["rows"] for error in row["errors"]}
        check("DUPLICATE_CODE_IN_FILE" in duplicate_codes, "duplicate code in file is reported")
        invalid_apply = client.post(
            f"/api/v1/crop-catalog/csv/crops/imports/{duplicate.json()['batch_id']}/apply",
            json={"reason": "Invalid batch should fail"},
        )
        check(invalid_apply.status_code == 409, "invalid crop batch cannot be applied", invalid_apply.text)

        history = client.get("/api/v1/crop-catalog/csv/crops/imports?limit=10")
        check(history.status_code == 200, "crop import history returns 200", history.text)
        history_payload = history.json()
        check(history_payload["schema_version"] == "crop_catalog_imports.v1", "crop import history schema version is stable")
        batch_ids = {item["batch_id"] for item in history_payload["imports"]}
        check(report["batch_id"] in batch_ids, "history includes valid crop batch")
        check(invalid_report["batch_id"] in batch_ids, "history includes invalid crop batch")

        validated_history = client.get("/api/v1/crop-catalog/csv/crops/imports?status=VALIDATED")
        check(validated_history.status_code == 200, "validated crop import history returns 200")
        check(all(item["status"] == "VALIDATED" for item in validated_history.json()["imports"]), "validated history filters by status")

        print("=" * 72)
        print("Crop catalog CSV import validated")
        print("=" * 72)
    finally:
        cleanup(db)
        delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    main()
