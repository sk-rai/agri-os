#!/usr/bin/env python3
"""Behavior regression for company-discovery CSV authorization."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import (
    CompanyDiscoveryCandidate,
    CompanyProfileAuditEvent,
    Tenant,
)
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def csv_file(payload: str):
    return {
        "file": (
            "company-discovery-auth.csv",
            payload,
            "text/csv",
        )
    }


def main() -> int:
    print("=" * 72)
    print("COMPANY DISCOVERY CSV AUTHORIZATION REGRESSION")
    print("=" * 72)

    tenant_id = f"company-discovery-auth-{uuid.uuid4().hex[:8]}"
    foreign_tenant_id = (
        f"company-discovery-auth-foreign-{uuid.uuid4().hex[:8]}"
    )
    db = SessionLocal()
    editor = None
    viewer = None

    valid_csv = (
        "candidate_name,company_type,source,website_url,"
        "support_email,support_phone,state,district,crop_focus,"
        "confidence_score,source_url,source_label,notes\n"
        "Regression Seeds Pvt Ltd,SEED_COMPANY,PUBLIC_WEB,"
        "https://example.test/regression,"
        "seed@example.test,+910000000011,UTTAR_PRADESH,"
        "VARANASI,RICE|WHEAT,0.91,"
        "https://example.test/regression,Public search,"
        "Authorization regression\n"
    )
    invalid_csv = (
        "candidate_name,source,confidence_score\n"
        "Invalid Candidate,NOT_A_SOURCE,1.50\n"
    )

    try:
        now = datetime.now(timezone.utc)
        db.add(Tenant(
            id=tenant_id,
            name="Company Discovery Auth Tenant",
            type="ENTERPRISE",
            created_at=now,
            updated_at=now,
        ))
        db.add(Tenant(
            id=foreign_tenant_id,
            name="Company Discovery Foreign Tenant",
            type="ENTERPRISE",
            created_at=now,
            updated_at=now,
        ))
        db.commit()

        editor, editor_headers = create_test_admin(
            db,
            role="ADMIN_EDITOR",
            tenant_id=tenant_id,
        )
        viewer, viewer_headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id=tenant_id,
        )
        client = TestClient(app)

        missing_bearer = client.post(
            "/api/v1/company-discovery-candidates/csv/validate",
            headers={"X-Tenant-ID": tenant_id},
            files=csv_file(valid_csv),
        )
        check(
            missing_bearer.status_code == 401,
            "CSV validation rejects missing bearer",
            missing_bearer.text,
        )

        viewer_validate = client.post(
            "/api/v1/company-discovery-candidates/csv/validate",
            headers=viewer_headers,
            files=csv_file(valid_csv),
        )
        check(
            viewer_validate.status_code == 403,
            "CSV validation rejects view-only administrator",
            viewer_validate.text,
        )

        viewer_import = client.post(
            "/api/v1/company-discovery-candidates/csv/import",
            headers=viewer_headers,
            files=csv_file(valid_csv),
        )
        check(
            viewer_import.status_code == 403,
            "CSV import rejects view-only administrator",
            viewer_import.text,
        )

        impersonated_headers = dict(editor_headers)
        impersonated_headers["X-Actor-ID"] = str(uuid.uuid4())
        impersonated = client.post(
            "/api/v1/company-discovery-candidates/csv/import",
            headers=impersonated_headers,
            files=csv_file(valid_csv),
        )
        check(
            impersonated.status_code == 403,
            "CSV import rejects actor impersonation",
            impersonated.text,
        )
        check(
            impersonated.json()["detail"]["error"]
            == "ACTOR_ID_MISMATCH",
            "Actor impersonation has stable error code",
        )

        mismatched_headers = dict(editor_headers)
        mismatched_headers["X-Tenant-ID"] = foreign_tenant_id
        mismatched = client.post(
            "/api/v1/company-discovery-candidates/csv/import",
            headers=mismatched_headers,
            files=csv_file(valid_csv),
        )
        check(
            mismatched.status_code == 403,
            "CSV import rejects tenant mismatch",
            mismatched.text,
        )
        check(
            mismatched.json()["detail"]["error"]
            == "ADMIN_PERMISSION_DENIED",
            "Tenant mismatch has stable permission error",
        )

        validation = client.post(
            "/api/v1/company-discovery-candidates/csv/validate",
            headers=editor_headers,
            files=csv_file(valid_csv),
        )
        check(
            validation.status_code == 200,
            "Edit-capable administrator validates CSV",
            validation.text[:500],
        )
        validation_body = validation.json()
        check(
            validation_body["valid"] is True,
            "Valid CSV passes validation",
        )
        check(
            validation_body["tenant_id"] == tenant_id,
            "CSV validation uses verified tenant",
        )
        check(
            validation_body["validated_by"] == str(editor.id),
            "CSV validation reports verified administrator",
            validation_body,
        )

        invalid_import = client.post(
            "/api/v1/company-discovery-candidates/csv/import",
            headers=editor_headers,
            files=csv_file(invalid_csv),
        )
        check(
            invalid_import.status_code == 400,
            "Invalid CSV import is rejected",
            invalid_import.text[:500],
        )
        check(
            db.query(CompanyDiscoveryCandidate)
            .filter(
                CompanyDiscoveryCandidate.tenant_id == tenant_id
            )
            .count()
            == 0,
            "Invalid import creates no candidates",
        )
        check(
            db.query(CompanyProfileAuditEvent)
            .filter(
                CompanyProfileAuditEvent.tenant_id == tenant_id,
                CompanyProfileAuditEvent.action
                == "IMPORT_COMPANY_DISCOVERY_CSV",
            )
            .count()
            == 0,
            "Invalid import creates no audit event",
        )

        imported = client.post(
            "/api/v1/company-discovery-candidates/csv/import",
            headers=editor_headers,
            files=csv_file(valid_csv),
        )
        check(
            imported.status_code == 200,
            "Edit-capable administrator imports valid CSV",
            imported.text[:500],
        )
        imported_body = imported.json()
        check(
            imported_body["tenant_id"] == tenant_id,
            "CSV import uses verified tenant",
        )
        check(
            imported_body["imported_by"] == str(editor.id),
            "CSV import reports verified administrator",
        )
        check(
            imported_body["imported_count"] == 1,
            "CSV import creates expected candidate count",
        )

        candidate = (
            db.query(CompanyDiscoveryCandidate)
            .filter(
                CompanyDiscoveryCandidate.tenant_id == tenant_id
            )
            .one()
        )
        check(
            candidate.tenant_id == tenant_id,
            "Imported candidate is tenant bounded",
        )
        check(
            candidate.metadata_["imported_by"] == str(editor.id),
            "Candidate provenance records verified administrator",
            candidate.metadata_,
        )
        check(
            candidate.metadata_["csv_file_name"]
            == "company-discovery-auth.csv",
            "Candidate provenance records source filename",
        )
        check(
            candidate.metadata_["import_schema"]
            == "company_discovery_csv_validation.v1",
            "Candidate provenance records import schema",
        )

        audit = (
            db.query(CompanyProfileAuditEvent)
            .filter(
                CompanyProfileAuditEvent.tenant_id == tenant_id,
                CompanyProfileAuditEvent.action
                == "IMPORT_COMPANY_DISCOVERY_CSV",
            )
            .one()
        )
        check(
            str(audit.actor_id) == str(editor.id),
            "Import audit records verified administrator",
            audit.actor_id,
        )
        check(
            audit.source == "CSV_IMPORT",
            "Import audit records stable source",
        )
        check(
            audit.after_profile["imported_count"] == 1,
            "Import audit records imported count",
        )
        check(
            audit.after_profile["candidate_ids"]
            == [str(candidate.id)],
            "Import audit records imported candidate IDs",
        )

        foreign_count = (
            db.query(CompanyDiscoveryCandidate)
            .filter(
                CompanyDiscoveryCandidate.tenant_id
                == foreign_tenant_id
            )
            .count()
        )
        check(
            foreign_count == 0,
            "CSV import creates no foreign-tenant candidates",
        )

        print("=" * 72)
        print("Company discovery CSV authorization validated")
        print("=" * 72)
        return 0
    finally:
        db.rollback()
        for cleanup_tenant in (tenant_id, foreign_tenant_id):
            db.query(CompanyProfileAuditEvent).filter(
                CompanyProfileAuditEvent.tenant_id
                == cleanup_tenant
            ).delete(synchronize_session=False)
            db.query(CompanyDiscoveryCandidate).filter(
                CompanyDiscoveryCandidate.tenant_id
                == cleanup_tenant
            ).delete(synchronize_session=False)
        db.commit()

        if editor:
            delete_test_admin(db, editor.id)
        if viewer:
            delete_test_admin(db, viewer.id)

        db.query(Tenant).filter(
            Tenant.id.in_([tenant_id, foreign_tenant_id])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
