#!/usr/bin/env python3
"""Behavior regression for authenticated broadcast reads."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import User
from app.modules.farmer.models import (
    Farmer,
    FarmerProjectEnrollment,
    Project,
    Tenant,
)
from app.modules.media.models import (
    BroadcastAuditEvent,
    BroadcastAudienceRule,
    BroadcastCampaign,
    BroadcastContent,
    BroadcastDelivery,
)
from scripts.admin_auth_test_utils import (
    create_test_admin,
    delete_test_admin,
)


def check(condition: bool, label: str, detail=None) -> None:
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def now() -> datetime:
    return datetime.now(timezone.utc)


def main() -> int:
    print("=" * 72)
    print("BROADCAST READ AUTHORIZATION REGRESSION")
    print("=" * 72)

    suffix = uuid.uuid4().hex[:8]
    tenant_id = f"broadcast-read-auth-{suffix}"
    foreign_tenant_id = (
        f"broadcast-read-auth-foreign-{suffix}"
    )

    project_id = uuid.uuid4()
    foreign_project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    foreign_farmer_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    foreign_campaign_id = uuid.uuid4()
    delivery_id = uuid.uuid4()

    created_user_ids: list[uuid.UUID] = []
    db = SessionLocal()

    try:
        db.add_all([
            Tenant(
                id=tenant_id,
                name="Broadcast Read Authorization Tenant",
                type="ENTERPRISE",
                is_active=True,
                created_at=now(),
                updated_at=now(),
            ),
            Tenant(
                id=foreign_tenant_id,
                name="Foreign Broadcast Read Tenant",
                type="ENTERPRISE",
                is_active=True,
                created_at=now(),
                updated_at=now(),
            ),
        ])
        db.commit()

        viewer, viewer_headers = create_test_admin(
            db,
            role="ADMIN_VIEWER",
            tenant_id=tenant_id,
        )
        owner, owner_headers = create_test_admin(
            db,
            role="FARMER",
            tenant_id=tenant_id,
        )
        assigned, assigned_headers = create_test_admin(
            db,
            role="FIELD_AGENT",
            tenant_id=tenant_id,
        )
        unrelated, unrelated_headers = create_test_admin(
            db,
            role="FARMER",
            tenant_id=tenant_id,
        )
        foreign_owner, foreign_headers = create_test_admin(
            db,
            role="FARMER",
            tenant_id=foreign_tenant_id,
        )
        created_user_ids.extend([
            viewer.id,
            owner.id,
            assigned.id,
            unrelated.id,
            foreign_owner.id,
        ])

        db.add_all([
            Project(
                id=project_id,
                tenant_id=tenant_id,
                name="Broadcast Read Project",
                start_date=date(2026, 10, 1),
                end_date=date(2027, 9, 30),
                status="PLANNED",
                created_at=now(),
                updated_at=now(),
            ),
            Project(
                id=foreign_project_id,
                tenant_id=foreign_tenant_id,
                name="Foreign Broadcast Read Project",
                start_date=date(2026, 10, 1),
                end_date=date(2027, 9, 30),
                status="PLANNED",
                created_at=now(),
                updated_at=now(),
            ),
        ])
        db.flush()

        db.add_all([
            Farmer(
                id=farmer_id,
                tenant_id=tenant_id,
                project_id=project_id,
                user_id=owner.id,
                mobile_number=(
                    f"+9177{uuid.uuid4().int % 100000000:08d}"
                ),
                display_name="Broadcast Owner Farmer",
                village_name_manual="Broadcast Village",
                primary_crop_code="RICE",
                status="ACTIVE",
                created_at=now(),
                updated_at=now(),
            ),
            Farmer(
                id=foreign_farmer_id,
                tenant_id=foreign_tenant_id,
                project_id=foreign_project_id,
                user_id=foreign_owner.id,
                mobile_number=(
                    f"+9176{uuid.uuid4().int % 100000000:08d}"
                ),
                display_name="Foreign Broadcast Farmer",
                village_name_manual="Foreign Village",
                primary_crop_code="WHEAT",
                status="ACTIVE",
                created_at=now(),
                updated_at=now(),
            ),
        ])
        db.flush()

        db.add(
            FarmerProjectEnrollment(
                tenant_id=tenant_id,
                farmer_id=farmer_id,
                project_id=project_id,
                enrollment_method="ASSISTED",
                enrollment_source="AUTH_REGRESSION",
                enrolled_by=assigned.id,
                status="ACTIVE",
                assigned_user_ids=[str(assigned.id)],
                metadata_={
                    "source":
                        "broadcast_read_authorization_regression"
                },
                created_at=now(),
                updated_at=now(),
            )
        )

        db.add_all([
            BroadcastCampaign(
                id=campaign_id,
                tenant_id=tenant_id,
                project_id=project_id,
                title="Authorized Broadcast",
                category="ADVISORY",
                priority="HIGH",
                status="PUBLISHED",
                starts_at=now() - timedelta(hours=1),
                created_by=viewer.id,
                metadata_={"fixture": "broadcast_read_auth"},
                is_active=True,
                created_at=now(),
                updated_at=now(),
            ),
            BroadcastCampaign(
                id=foreign_campaign_id,
                tenant_id=foreign_tenant_id,
                project_id=foreign_project_id,
                title="Foreign Broadcast",
                category="GENERAL",
                priority="NORMAL",
                status="PUBLISHED",
                starts_at=now() - timedelta(hours=1),
                created_by=foreign_owner.id,
                metadata_={"fixture": "broadcast_read_auth"},
                is_active=True,
                created_at=now(),
                updated_at=now(),
            ),
        ])
        db.flush()

        db.add(
            BroadcastContent(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                language_code="en",
                title="Authorized Broadcast",
                body_text="Authenticated broadcast content.",
                metadata_={"fixture": "broadcast_read_auth"},
                created_at=now(),
                updated_at=now(),
            )
        )
        db.add(
            BroadcastAudienceRule(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                rule_type="CROP",
                operator="IN",
                values=["RICE"],
                metadata_={"fixture": "broadcast_read_auth"},
                created_at=now(),
            )
        )
        db.add(
            BroadcastDelivery(
                id=delivery_id,
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                farmer_id=farmer_id,
                user_id=owner.id,
                delivery_status="PENDING",
                metadata_={"channel": "IN_APP"},
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.add(
            BroadcastAuditEvent(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                delivery_id=delivery_id,
                action="AUTHORIZATION_REGRESSION_SEEDED",
                actor_type="ADMIN_VIEWER",
                actor_id=viewer.id,
                before={},
                after={"delivery_status": "PENDING"},
                reason="Broadcast read authorization fixture.",
                metadata_={"fixture": "broadcast_read_auth"},
                created_at=now(),
            )
        )
        db.commit()

        client = TestClient(app)

        print(
            "\n[1] Tenant-administration reads require "
            "verified view permission"
        )
        missing = client.get(
            "/api/v1/broadcasts",
            headers={"X-Tenant-ID": tenant_id},
        )
        check(
            missing.status_code == 401,
            "Broadcast campaign list rejects missing bearer",
            missing.text[:500],
        )

        listing = client.get(
            "/api/v1/broadcasts",
            headers=viewer_headers,
        )
        check(
            listing.status_code == 200,
            "View administrator lists broadcasts",
            listing.text[:1000],
        )
        listing_body = listing.json()
        check(
            listing_body["tenant_id"] == tenant_id,
            "Campaign list reports verified tenant",
        )
        check(
            listing_body["count"] == 1,
            "Campaign list excludes foreign tenant",
            listing_body.get("campaigns"),
        )
        check(
            listing_body["campaigns"][0]["id"]
            == str(campaign_id),
            "Campaign list returns tenant campaign",
        )

        mismatch_headers = dict(viewer_headers)
        mismatch_headers["X-Tenant-ID"] = foreign_tenant_id
        mismatch = client.get(
            "/api/v1/broadcasts",
            headers=mismatch_headers,
        )
        check(
            mismatch.status_code == 403,
            "Campaign list rejects token/header mismatch",
            mismatch.text[:500],
        )

        detail = client.get(
            f"/api/v1/broadcasts/{campaign_id}",
            headers=viewer_headers,
        )
        check(
            detail.status_code == 200,
            "View administrator reads campaign detail",
            detail.text[:1000],
        )
        check(
            detail.json()["id"] == str(campaign_id),
            "Campaign detail is tenant-bounded",
        )

        hidden = client.get(
            f"/api/v1/broadcasts/{foreign_campaign_id}",
            headers=viewer_headers,
        )
        check(
            hidden.status_code == 404,
            "Campaign detail hides foreign campaign",
            hidden.text[:500],
        )

        deliveries = client.get(
            (
                f"/api/v1/broadcasts/{campaign_id}"
                "/deliveries"
            ),
            headers=viewer_headers,
        )
        check(
            deliveries.status_code == 200,
            "View administrator lists deliveries",
            deliveries.text[:1000],
        )
        check(
            deliveries.json()["count"] == 1,
            "Delivery list returns tenant delivery",
        )
        check(
            deliveries.json()["deliveries"][0]["id"]
            == str(delivery_id),
            "Delivery list retains tenant-bound delivery",
        )

        audience = client.get(
            (
                f"/api/v1/broadcasts/{campaign_id}"
                "/audience-preview"
            ),
            headers=viewer_headers,
        )
        check(
            audience.status_code == 200,
            "View administrator previews audience",
            audience.text[:1000],
        )
        check(
            audience.json()["tenant_id"] == tenant_id,
            "Audience preview reports verified tenant",
        )

        audit = client.get(
            (
                f"/api/v1/broadcasts/{campaign_id}"
                "/audit"
            ),
            headers=viewer_headers,
        )
        check(
            audit.status_code == 200,
            "View administrator lists broadcast audit",
            audit.text[:1000],
        )
        check(
            audit.json()["count"] == 1,
            "Audit read returns tenant event",
        )

        print(
            "\n[2] Farmer feed requires ownership "
            "or active assignment"
        )
        feed_path = (
            f"/api/v1/broadcasts/farmers/{farmer_id}"
            "/broadcasts?language_code=en"
        )

        missing_feed = client.get(
            feed_path,
            headers={"X-Tenant-ID": tenant_id},
        )
        check(
            missing_feed.status_code == 401,
            "Farmer feed rejects missing bearer",
            missing_feed.text[:500],
        )

        owner_feed = client.get(
            feed_path,
            headers=owner_headers,
        )
        check(
            owner_feed.status_code == 200,
            "Linked farmer owner reads broadcast feed",
            owner_feed.text[:1000],
        )
        check(
            owner_feed.json()["tenant_id"] == tenant_id,
            "Farmer feed reports verified tenant",
        )
        check(
            owner_feed.json()["count"] == 1,
            "Farmer owner sees delivered broadcast",
        )
        check(
            owner_feed.json()["broadcasts"][0]
            ["delivery"]["id"] == str(delivery_id),
            "Farmer owner sees own delivery",
        )

        assigned_feed = client.get(
            feed_path,
            headers=assigned_headers,
        )
        check(
            assigned_feed.status_code == 200,
            "Assigned field agent reads farmer feed",
            assigned_feed.text[:1000],
        )
        check(
            assigned_feed.json()["count"] == 1,
            "Assigned agent sees farmer delivery",
        )

        denied_feed = client.get(
            feed_path,
            headers=unrelated_headers,
        )
        check(
            denied_feed.status_code == 403,
            "Unrelated human cannot read farmer feed",
            denied_feed.text[:500],
        )
        check(
            denied_feed.json()["detail"]["code"]
            == "BROADCAST_FARMER_ACCESS_DENIED",
            "Farmer feed denial uses stable error code",
        )

        owner_mismatch = dict(owner_headers)
        owner_mismatch["X-Tenant-ID"] = foreign_tenant_id
        mismatch_feed = client.get(
            feed_path,
            headers=owner_mismatch,
        )
        check(
            mismatch_feed.status_code == 403,
            "Farmer feed rejects token/header mismatch",
            mismatch_feed.text[:500],
        )

        foreign_hidden = client.get(
            (
                f"/api/v1/broadcasts/farmers/"
                f"{foreign_farmer_id}/broadcasts"
            ),
            headers=owner_headers,
        )
        check(
            foreign_hidden.status_code == 404,
            "Farmer feed hides foreign-tenant farmer",
            foreign_hidden.text[:500],
        )

        print("=" * 72)
        print("Broadcast read authorization validated")
        print("=" * 72)
        return 0

    finally:
        db.rollback()

        db.query(BroadcastAuditEvent).filter(
            BroadcastAuditEvent.tenant_id.in_([
                tenant_id,
                foreign_tenant_id,
            ])
        ).delete(synchronize_session=False)
        db.query(BroadcastDelivery).filter(
            BroadcastDelivery.tenant_id.in_([
                tenant_id,
                foreign_tenant_id,
            ])
        ).delete(synchronize_session=False)
        db.query(BroadcastAudienceRule).filter(
            BroadcastAudienceRule.tenant_id.in_([
                tenant_id,
                foreign_tenant_id,
            ])
        ).delete(synchronize_session=False)
        db.query(BroadcastContent).filter(
            BroadcastContent.tenant_id.in_([
                tenant_id,
                foreign_tenant_id,
            ])
        ).delete(synchronize_session=False)
        db.query(BroadcastCampaign).filter(
            BroadcastCampaign.tenant_id.in_([
                tenant_id,
                foreign_tenant_id,
            ])
        ).delete(synchronize_session=False)
        db.query(FarmerProjectEnrollment).filter(
            FarmerProjectEnrollment.tenant_id.in_([
                tenant_id,
                foreign_tenant_id,
            ])
        ).delete(synchronize_session=False)
        db.query(Farmer).filter(
            Farmer.tenant_id.in_([
                tenant_id,
                foreign_tenant_id,
            ])
        ).delete(synchronize_session=False)
        db.query(Project).filter(
            Project.tenant_id.in_([
                tenant_id,
                foreign_tenant_id,
            ])
        ).delete(synchronize_session=False)
        db.commit()

        for user_id in created_user_ids:
            delete_test_admin(db, user_id)

        db.query(Tenant).filter(
            Tenant.id.in_([
                tenant_id,
                foreign_tenant_id,
            ])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
