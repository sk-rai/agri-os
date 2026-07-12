"""Regression for crop taxonomy CSV validate-only import workflow."""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
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
        "/api/v1/crop-catalog/csv/taxonomy/validate",
        files={"file": ("taxonomy.csv", io.BytesIO(content.encode("utf-8")), "text/csv")},
    )


def main():
    print("=" * 72)
    print("CROP TAXONOMY CSV VALIDATION REGRESSION")
    print("=" * 72)

    anonymous = TestClient(app)
    denied = anonymous.post(
        "/api/v1/crop-catalog/csv/taxonomy/validate",
        files={"file": ("taxonomy.csv", b"code,canonical_name,node_type,level\n", "text/csv")},
    )
    check(denied.status_code == 401, "taxonomy validation requires admin authentication", denied.text)

    db = SessionLocal()
    admin, headers = create_test_admin(db)
    try:
        client = TestClient(app, headers=headers)

        template = client.get("/api/v1/crop-catalog/csv/taxonomy/template")
        check(template.status_code == 200, "viewer can download taxonomy template")
        check("parent_codes" in template.text, "template includes parent_codes column")

        export = client.get("/api/v1/crop-catalog/csv/taxonomy/export")
        check(export.status_code == 200, "viewer can export taxonomy catalog")
        check("FIELD_CROP" in export.text, "export includes seeded taxonomy rows")

        missing = upload_csv(client, "code,canonical_name\nBAD,Bad\n")
        check(missing.status_code == 400, "missing required columns returns 400", missing.text)
        check("MISSING_COLUMNS" in missing.text, "missing column response identifies contract error")

        invalid_csv = """code,canonical_name,node_type,level,display_order,parent_codes,description,aliases_json,metadata_json\nBAD NODE,Bad Node,UNKNOWN,abc,1,NO_SUCH_PARENT,Invalid row,not-json,[]\n"""
        invalid = upload_csv(client, invalid_csv)
        check(invalid.status_code == 200, "invalid rows return validation report", invalid.text)
        invalid_report = invalid.json()
        check(invalid_report["schema_version"] == "crop_taxonomy_csv_validation.v1", "validation schema version is stable")
        check(invalid_report["mode"] == "VALIDATE_ONLY", "validation is explicitly validate-only")
        check(not invalid_report["can_apply"], "invalid taxonomy report cannot apply")
        error_codes = {error["code"] for error in invalid_report["rows"][0]["errors"]}
        check({"INVALID_NODE_TYPE", "INVALID_INTEGER", "UNKNOWN_PARENT", "INVALID_JSON"}.issubset(error_codes), "invalid row reports expected errors", sorted(error_codes))

        valid_csv = """code,canonical_name,node_type,level,display_order,parent_codes,description,aliases_json,metadata_json\nREGRESSION_TEST_TAXONOMY,Regression Test Taxonomy,AGRONOMIC,2,99,FIELD_CROP,Validate only row,[],{"source":"regression"}\n"""
        valid = upload_csv(client, valid_csv)
        check(valid.status_code == 200, "valid taxonomy dry-run returns 200", valid.text)
        report = valid.json()
        check(report["can_apply"], "valid taxonomy report is apply-ready for future apply step")
        check(report["summary"]["create"] == 1, "valid dry-run reports one create")
        check(report["summary"]["errors"] == 0, "valid dry-run has no errors")
        check(report["rows"][0]["action"] == "CREATE", "valid new taxonomy row action is CREATE")

        duplicate_csv = valid_csv + "REGRESSION_TEST_TAXONOMY,Duplicate Taxonomy,AGRONOMIC,2,100,FIELD_CROP,Duplicate row,[],{}\n"
        duplicate = upload_csv(client, duplicate_csv)
        check(duplicate.status_code == 200, "duplicate code returns validation report")
        duplicate_codes = {error["code"] for row in duplicate.json()["rows"] for error in row["errors"]}
        check("DUPLICATE_CODE_IN_FILE" in duplicate_codes, "duplicate code in file is reported")

        existing_csv = """code,canonical_name,node_type,level,display_order,parent_codes,description,aliases_json,metadata_json\nFIELD_CROP,Field Crop,AGRONOMIC,1,10,AGRICULTURE,Crops grown in open fields,[],{}\n"""
        existing = upload_csv(client, existing_csv)
        check(existing.status_code == 200, "existing taxonomy row validates")
        check(existing.json()["rows"][0]["action"] in {"UNCHANGED", "UPDATE"}, "existing taxonomy row is classified as unchanged/update")

        print("=" * 72)
        print("Crop taxonomy CSV validation passed")
        print("=" * 72)
    finally:
        delete_test_admin(db, admin.id)
        db.close()


if __name__ == "__main__":
    main()
