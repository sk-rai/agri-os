"""Regression for the admin system readiness report."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin


REQUIRED_CHECKS = {
    "PROJECT_SETUP",
    "WORKFLOW_RUNTIME",
    "WORKFLOW_ASSIGNMENTS",
    "INPUT_CATALOG",
    "PRODUCT_CATALOG",
    "FARMER_SYNC",
    "PARCEL_GEOMETRY",
    "ACTIVITY_EVIDENCE",
    "SYNC_HEALTH",
}


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main():
    print("=" * 72)
    print("SYSTEM READINESS REPORT REGRESSION")
    print("=" * 72)
    db = SessionLocal()
    admin = None
    try:
        client = TestClient(app)
        unauthenticated = client.get("/api/v1/reports/system-readiness", headers={"X-Tenant-ID": "default"})
        check(unauthenticated.status_code == 401, "system readiness requires admin authentication", unauthenticated.text)

        admin, headers = create_test_admin(db, role="ADMIN_VIEWER", tenant_id="default")
        response = client.get("/api/v1/reports/system-readiness", headers=headers)
        check(response.status_code == 200, "ADMIN_VIEWER can read system readiness", response.text[:500])
        payload = response.json()
        check(payload["schema_version"] == "system_readiness.v1", "schema version is stable")
        check(payload["tenant_id"] == "default", "tenant id is returned")
        check("summary" in payload and "checks" in payload, "payload has summary and checks")
        check(payload["summary"]["check_count"] == len(payload["checks"]), "summary check_count matches checks length")
        check(0 <= payload["summary"]["ready_count"] <= payload["summary"]["check_count"], "ready_count is in range")
        check(REQUIRED_CHECKS.issubset({item["code"] for item in payload["checks"]}), "required readiness checks are present")
        for item in payload["checks"]:
            check(isinstance(item["ready"], bool), f"{item['code']} ready is boolean")
            check(item["severity"] in {"OK", "WARN", "INFO"}, f"{item['code']} severity is valid")
            check(bool(item["label"]) and bool(item["detail"]) and bool(item["href"]), f"{item['code']} has label/detail/href")
    finally:
        if admin:
            delete_test_admin(db, admin.id)
        db.close()

    print("=" * 72)
    print("System readiness report validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
