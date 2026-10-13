#!/usr/bin/env python3
from __future__ import annotations

import uuid
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import User
from app.modules.farmer.models import (
    Tenant,
    TenantProvisioningAuditEvent,
)
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)


def check(condition: bool, label: str, detail=None) -> None:
    marker = "PASS" if condition else "FAIL"
    print(f"  {marker} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def now():
    return datetime.now(timezone.utc)


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    ordinary_tenant_id = f"tenant-provisioning-source-{suffix}"
    target_tenant_id = f"tenant-provisioning-target-{suffix}"

    platform_admin_id = None
    platform_viewer_id = None
    ordinary_admin_id = None
    created_default_tenant = False

    client = TestClient(app)
    db = SessionLocal()

    try:
        default_tenant = (
            db.query(Tenant)
            .filter(Tenant.id == "default")
            .first()
        )
        if default_tenant is None:
            default_tenant = Tenant(
                id="default",
                name="Default Platform Tenant",
                type="GOVERNMENT",
                created_at=now(),
                updated_at=now(),
            )
            db.add(default_tenant)
            db.commit()
            created_default_tenant = True

        ordinary_tenant = Tenant(
            id=ordinary_tenant_id,
            name="Ordinary Provisioning Source Tenant",
            type="ENTERPRISE",
            created_at=now(),
            updated_at=now(),
        )
        db.add(ordinary_tenant)
        db.commit()

        platform_admin, platform_headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id="default",
        )
        platform_admin_id = platform_admin.id

        platform_viewer, viewer_headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id="default",
        )
        platform_viewer_id = platform_viewer.id

        ordinary_admin, ordinary_headers = create_test_admin(
            db,
            role="ENTERPRISE_ADMIN",
            tenant_id=ordinary_tenant_id,
        )
        ordinary_admin_id = ordinary_admin.id
    finally:
        db.close()

    url = "/api/v1/tenants"
    payload = {
        "id": target_tenant_id,
        "name": "Provisioning Authorization Target",
        "type": "FPO",
        "contact_email": "provisioning@example.test",
        "contact_phone": "+919999999999",
    }

    try:
        print("=" * 72)
        print("TENANT PROVISIONING AUTHORIZATION REGRESSION")
        print("=" * 72)

        missing = client.post(
            url,
            headers={"X-Tenant-ID": "default"},
            json=payload,
        )
        check(
            missing.status_code == 401,
            "Tenant provisioning rejects missing bearer",
            missing.text,
        )

        viewer = client.post(
            url,
            headers=viewer_headers,
            json=payload,
        )
        check(
            viewer.status_code == 403,
            "Tenant provisioning rejects view-only administrator",
            viewer.text,
        )
        check(
            viewer.json()["detail"]["error"]
            == "ADMIN_PERMISSION_DENIED",
            "View-only denial uses stable permission error",
        )

        ordinary = client.post(
            url,
            headers=ordinary_headers,
            json=payload,
        )
        check(
            ordinary.status_code == 403,
            "Tenant provisioning rejects ordinary tenant administrator",
            ordinary.text,
        )
        check(
            ordinary.json()["detail"]["error"]
            == "PLATFORM_TENANT_PROVISIONING_REQUIRED",
            "Ordinary tenant denial uses stable platform-boundary error",
        )

        impersonated = client.post(
            url,
            headers={
                **platform_headers,
                "X-Actor-ID": str(uuid.uuid4()),
            },
            json=payload,
        )
        check(
            impersonated.status_code == 403,
            "Tenant provisioning rejects actor impersonation",
            impersonated.text,
        )
        check(
            impersonated.json()["detail"]["error"]
            == "ACTOR_ID_MISMATCH",
            "Actor impersonation uses stable error code",
        )

        tenant_mismatch = client.post(
            url,
            headers={
                **platform_headers,
                "X-Tenant-ID": ordinary_tenant_id,
            },
            json=payload,
        )
        check(
            tenant_mismatch.status_code == 403,
            "Tenant provisioning rejects token/header tenant mismatch",
            tenant_mismatch.text,
        )
        check(
            tenant_mismatch.json()["detail"]["error"]
            == "ADMIN_PERMISSION_DENIED",
            "Tenant mismatch uses stable permission error",
        )

        created = client.post(
            url,
            headers=platform_headers,
            json=payload,
        )
        check(
            created.status_code == 201,
            "Platform administrator provisions tenant",
            created.text,
        )
        body = created.json()
        check(
            body["id"] == target_tenant_id,
            "Provisioned tenant id is returned",
        )
        check(
            body["name"] == payload["name"],
            "Provisioned tenant name is returned",
        )
        check(
            body["type"] == "FPO",
            "Provisioned tenant type is returned",
        )

        db = SessionLocal()
        try:
            tenant = (
                db.query(Tenant)
                .filter(Tenant.id == target_tenant_id)
                .one()
            )
            events = (
                db.query(TenantProvisioningAuditEvent)
                .filter(
                    TenantProvisioningAuditEvent.target_tenant_id
                    == target_tenant_id
                )
                .all()
            )
        finally:
            db.close()

        check(
            tenant.name == payload["name"],
            "Provisioned tenant is persisted",
        )
        check(
            len(events) == 1,
            "Tenant provisioning writes one immutable audit event",
            len(events),
        )

        event = events[0]
        check(
            event.actor_tenant_id == "default",
            "Provisioning audit records verified platform tenant",
            event.actor_tenant_id,
        )
        check(
            event.actor_id == platform_admin_id,
            "Provisioning audit records verified administrator",
            event.actor_id,
        )
        check(
            event.action == "CREATE_TENANT",
            "Provisioning audit action is stable",
            event.action,
        )
        check(
            event.after_payload["id"] == target_tenant_id,
            "Provisioning audit preserves target tenant",
            event.after_payload,
        )
        check(
            event.after_payload["type"] == "FPO",
            "Provisioning audit preserves tenant type",
            event.after_payload,
        )

        duplicate = client.post(
            url,
            headers=platform_headers,
            json=payload,
        )
        check(
            duplicate.status_code == 409,
            "Duplicate tenant provisioning is rejected",
            duplicate.text,
        )

        db = SessionLocal()
        try:
            audit_count = (
                db.query(TenantProvisioningAuditEvent)
                .filter(
                    TenantProvisioningAuditEvent.target_tenant_id
                    == target_tenant_id
                )
                .count()
            )
        finally:
            db.close()

        check(
            audit_count == 1,
            "Duplicate rejection creates no extra audit event",
            audit_count,
        )

        print("=" * 72)
        print("Tenant provisioning authorization validated")
        print("=" * 72)
        return 0
    finally:
        db = SessionLocal()
        try:
            db.query(TenantProvisioningAuditEvent).filter(
                TenantProvisioningAuditEvent.target_tenant_id
                == target_tenant_id
            ).delete(synchronize_session=False)
            db.query(Tenant).filter(
                Tenant.id == target_tenant_id
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

        db = SessionLocal()
        try:
            for user_id in (
                platform_admin_id,
                platform_viewer_id,
                ordinary_admin_id,
            ):
                if user_id is not None:
                    delete_test_admin(db, user_id)

            db.query(Tenant).filter(
                Tenant.id == ordinary_tenant_id
            ).delete(synchronize_session=False)

            if created_default_tenant:
                remaining_default_users = (
                    db.query(User)
                    .filter(User.tenant_id == "default")
                    .count()
                )
                if remaining_default_users == 0:
                    db.query(Tenant).filter(
                        Tenant.id == "default"
                    ).delete(synchronize_session=False)

            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
