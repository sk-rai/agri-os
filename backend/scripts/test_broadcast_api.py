"""Regression for read-only broadcast campaign API."""

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import engine, SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Project, Tenant
from app.modules.media.models import BroadcastAuditEvent, BroadcastAudienceRule, BroadcastCampaign, BroadcastContent, BroadcastDelivery, MediaAsset, MediaAttachment


def now():
    return datetime.now(timezone.utc)


def check(condition, label, detail=None):
    print(f"  {'PASS' if condition else 'FAIL'} {label}")
    if detail is not None:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(label)


def main():
    from app.modules.workflow.models import CropCycle, CropStageInstance
    from app.modules.master_data.models.crop import CropCategory, Crop, CropLifecycleTemplate
    from app.modules.farmer.models import Parcel
    print("=" * 72)
    print("BROADCAST API REGRESSION")
    print("=" * 72)

    tenant_id = f"broadcast-api-{uuid.uuid4().hex[:8]}"
    campaign_id = uuid.uuid4()
    project_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    all_farmer_id = uuid.uuid4()
    crop_farmer_id = uuid.uuid4()
    crop_parcel_id = uuid.uuid4()
    headers = {"X-Tenant-ID": tenant_id}

    BroadcastAuditEvent.__table__.create(bind=engine, checkfirst=True)

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Broadcast API Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.flush()
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name="Broadcast API Project",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="PLANNED",
            crop_scope=["RICE"],
            geography_scope={},
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(Farmer(
            id=farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            mobile_number=f"+9193{uuid.uuid4().int % 100000000:08d}",
            display_name="Broadcast API Farmer",
            village_name_manual="Broadcast Village",
            language_preference="kn",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()

        db.add(Farmer(
            id=all_farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            mobile_number=f"+9192{uuid.uuid4().int % 100000000:08d}",
            display_name="Broadcast API All Farmer",
            village_name_manual="Broadcast Village",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()

        db.add(Farmer(
            id=crop_farmer_id,
            tenant_id=tenant_id,
            project_id=project_id,
            mobile_number=f"+9191{uuid.uuid4().int % 100000000:08d}",
            display_name="Broadcast API Crop Farmer",
            village_name_manual="Broadcast Village",
            status="ACTIVE",
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()

        crop_category = db.query(CropCategory).filter(CropCategory.code == "CEREAL").first()
        if crop_category is None:
            crop_category = CropCategory(
                id=uuid.uuid4(),
                code="CEREAL",
                canonical_name="Cereals",
                description="Broadcast targeting regression crop category",
                aliases=[],
                is_active=True,
                created_at=now(),
                updated_at=now(),
            )
            db.add(crop_category)
            db.flush()

        crop = db.query(Crop).filter(Crop.code == "RICE").first()
        if crop is None:
            crop = Crop(
                id=uuid.uuid4(),
                code="RICE",
                category_id=crop_category.id,
                canonical_name="Rice",
                scientific_name="Oryza sativa",
                description="Broadcast targeting regression crop",
                typical_duration_days=120,
                suitable_seasons=["KHARIF"],
                suitable_soil_types=[],
                aliases=[],
                is_active=True,
                created_at=now(),
                updated_at=now(),
            )
            db.add(crop)
            db.flush()

        lifecycle_template = db.query(CropLifecycleTemplate).filter(
            CropLifecycleTemplate.crop_id == crop.id,
            CropLifecycleTemplate.season_code == "KHARIF",
        ).first()
        if lifecycle_template is None:
            lifecycle_template = CropLifecycleTemplate(
                id=uuid.uuid4(),
                code=f"BROADCAST_RICE_KHARIF_{uuid.uuid4().hex[:8]}",
                crop_id=crop.id,
                season_code="KHARIF",
                canonical_name="Broadcast Rice Template",
                description="Broadcast targeting regression template",
                total_duration_days=120,
                stages=[],
                is_default=False,
                aliases=[],
                is_active=True,
                created_at=now(),
                updated_at=now(),
            )
            db.add(lifecycle_template)
            db.flush()

        db.add(Parcel(
            id=crop_parcel_id,
            tenant_id=tenant_id,
            farmer_id=crop_farmer_id,
            survey_number="BROADCAST-CROP-PARCEL",
            reported_area=1,
            reported_area_unit="ACRE",
            ownership_type="OWNED",
            village_name_manual="Broadcast Village",
            created_at=now(),
            updated_at=now(),
        ))

        crop_cycle_id = uuid.uuid4()
        db.add(CropCycle(
            id=crop_cycle_id,
            tenant_id=tenant_id,
            farmer_id=crop_farmer_id,
            parcel_id=crop_parcel_id,
            project_id=project_id,
            crop_code="RICE",
            season_code="KHARIF",
            lifecycle_template_id=lifecycle_template.id,
            workflow_template_version_id=None,
            status="ACTIVE",
            planned_sowing_date=now().date(),
            expected_harvest_date=now().date(),
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()
        db.add(CropStageInstance(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            crop_cycle_id=crop_cycle_id,
            stage_code="FLOWERING",
            stage_name="Flowering",
            stage_order=4,
            expected_duration_days=15,
            status="ACTIVE",
            actual_start_date=now().date(),
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()

        db.add(BroadcastCampaign(
            id=campaign_id,
            tenant_id=tenant_id,
            title="Rice pest advisory",
            category="ADVISORY",
            priority="HIGH",
            status="DRAFT",
            metadata_={"targeting_mode": "RULE_BASED"},
            created_at=now(),
            updated_at=now(),
        ))
        db.flush()

        seeded_content = BroadcastContent(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            language_code="en",
            title="Rice pest advisory",
            body_text="Inspect crop for pests.",
            cta_label="View",
            deeplink_url="agrios://broadcast/rice-pest",
            created_at=now(),
            updated_at=now(),
        )
        db.add(seeded_content)
        db.flush()
        seeded_asset = MediaAsset(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            media_type="PHOTO",
            mime_type="image/jpeg",
            storage_url="https://example.test/rice-pest.jpg",
            thumbnail_url="https://example.test/rice-pest-thumb.jpg",
            upload_status="UPLOADED",
            metadata_={"source": "broadcast_regression"},
            created_at=now(),
            updated_at=now(),
        )
        db.add(seeded_asset)
        db.flush()
        db.add(MediaAttachment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            media_asset_id=seeded_asset.id,
            entity_type="ADVISORY",
            entity_id=seeded_content.id,
            purpose="ADVISORY_ATTACHMENT",
            caption="Rice pest reference image",
            display_order=1,
            is_primary=True,
            metadata_={"placement": "hero"},
            created_at=now(),
            updated_at=now(),
        ))
        db.add(BroadcastContent(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            language_code="hi",
            title="Rice pest advisory Hindi",
            body_text="Inspect crop for pests.",
            created_at=now(),
            updated_at=now(),
        ))
        db.add(BroadcastAudienceRule(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            rule_type="CROP",
            operator="IN",
            values=["RICE"],
            created_at=now(),
        ))
        db.add(BroadcastDelivery(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            farmer_id=farmer_id,
            delivery_status="PENDING",
            created_at=now(),
            updated_at=now(),
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    print("\n[1] Create draft campaign via API")
    created_id = uuid.uuid4()
    create = client.post("/api/v1/broadcasts", headers=headers, json={
        "id": str(created_id),
        "title": "Weather alert draft",
        "category": "WEATHER",
        "priority": "URGENT",
        "metadata": {"targeting_mode": "RULE_BASED"},
        "contents": [
            {
                "language_code": "en",
                "title": "Weather alert",
                "body_text": "Heavy rainfall expected.",
                "cta_label": "View details",
                "deeplink_url": "agrios://broadcast/weather-alert"
            },
            {
                "language_code": "hi",
                "title": "Weather alert Hindi",
                "body_text": "Heavy rainfall expected."
            }
        ],
                "audience_rules": [
            {
                "rule_type": "LOCATION",
                "operator": "IN",
                "values": ["Broadcast Village"]
            },
            {
                "rule_type": "CROP",
                "operator": "IN",
                "values": ["RICE"]
            },
            {
                "rule_type": "FARMER",
                "operator": "IN",
                "values": [str(farmer_id)]
            },
            {
                "rule_type": "PROJECT",
                "operator": "IN",
                "values": [str(project_id)]
            },
            {
                "rule_type": "STAGE",
                "operator": "IN",
                "values": ["FLOWERING"]
            },
            {
                "rule_type": "ALL",
                "operator": "ANY",
                "values": []
            },
        ]
    })
    check(create.status_code == 201, "Create broadcast draft returns 201", create.text)
    created = create.json()
    check(created["id"] == str(created_id), "Create preserves requested campaign id")
    check(created["status"] == "DRAFT", "Created campaign starts as draft")
    check(created["category"] == "WEATHER", "Create normalizes category")
    check(created["priority"] == "URGENT", "Create normalizes priority")
    check(len(created["contents"]) == 2, "Create returns content rows")
    check(len(created["audience_rules"]) == 6, "Create returns audience rules")
    check(created["delivery_summary"]["total"] == 0, "Create does not generate deliveries yet")

    print("\n[1a] Edit draft content and audience rules")
    add_content = client.post(f"/api/v1/broadcasts/{created_id}/contents", headers=headers, json={
        "language_code": "kn",
        "title": "Weather alert Kannada",
        "body_text": "Heavy rainfall expected.",
        "metadata": {"source": "regression"}
    })
    check(add_content.status_code == 201, "Add draft content returns 201", add_content.text)
    check(any(item["language_code"] == "kn" for item in add_content.json()["contents"]), "Added draft content is returned")
    add_rule = client.post(f"/api/v1/broadcasts/{created_id}/audience-rules", headers=headers, json={
        "rule_type": "LANGUAGE",
        "operator": "IN",
        "values": ["kn"],
        "metadata": {"source": "regression"}
    })
    check(add_rule.status_code == 201, "Add draft audience rule returns 201", add_rule.text)
    check(any(item["rule_type"] == "LANGUAGE" for item in add_rule.json()["audience_rules"]), "Added draft audience rule is returned")
    print("\n[1b] Publish draft campaign")
    publish = client.post(f"/api/v1/broadcasts/{created_id}/publish", headers=headers, json={
        "approved_by": str(uuid.uuid4()),
        "reason": "Regression publish test"
    })
    check(publish.status_code == 200, "Publish broadcast draft returns 200", publish.text)
    published = publish.json()
    check(published["status"] == "PUBLISHED", "Publish changes status")
    check(published["starts_at"] is not None, "Publish sets starts_at")
    check(published["metadata"]["delivery_generation"] == "NOT_STARTED", "Publish does not generate deliveries yet")

    published_edit = client.post(f"/api/v1/broadcasts/{created_id}/contents", headers=headers, json={
        "language_code": "ta",
        "title": "Should fail",
        "body_text": "Published campaigns cannot be edited."
    })
    check(published_edit.status_code == 409, "Published broadcast rejects draft content edits", published_edit.text)

    print("\n[1c-pre] Preview audience")
    preview = client.get(f"/api/v1/broadcasts/{created_id}/audience-preview", headers=headers)
    check(preview.status_code == 200, "Audience preview returns 200", preview.text)
    preview_body = preview.json()
    check(preview_body["schema_version"] == "broadcast_audience_preview.v1", "Audience preview schema stable")
    check(preview_body["campaign_id"] == str(created_id), "Audience preview references campaign")
    check(preview_body["audience_match_mode"] == "ANY", "Audience preview defaults to ANY match mode")
    check(preview_body["estimated_farmer_count"] == 3, "Audience preview estimates unique farmers")
    check(preview_body["existing_delivery_count"] == 0, "Audience preview does not create deliveries")
    check(preview_body["unsupported_rule_count"] == 0, "Audience preview expands all configured rules")
    check(preview_body["match_reason_counts"]["LOCATION"] == 3, "Audience preview exposes LOCATION match reason count")
    check(any("LOCATION" in row["matched_by"] for row in preview_body["sample_matches"]), "Audience preview explains sample match reasons")
    rule_counts = {row["rule_type"]: row["matched_farmer_count"] for row in preview_body["rule_summaries"]}
    check(rule_counts.get("ALL") == 3, "Audience preview expands ALL rule")
    check(rule_counts.get("FARMER") == 1, "Audience preview expands FARMER rule")
    check(rule_counts.get("PROJECT") == 3, "Audience preview expands PROJECT rule")
    check(rule_counts.get("CROP") == 1, "Audience preview expands CROP rule")
    check(rule_counts.get("LOCATION") == 3, "Audience preview expands LOCATION rule")
    check(rule_counts.get("LANGUAGE") == 1, "Audience preview expands LANGUAGE rule")
    check(rule_counts.get("STAGE") == 1, "Audience preview expands STAGE rule")

    print("\n[1c-all] Preview ALL/intersection audience mode")
    all_mode_id = uuid.uuid4()
    all_mode_create = client.post("/api/v1/broadcasts", headers=headers, json={
        "id": str(all_mode_id),
        "title": "Intersection targeting draft",
        "category": "ADVISORY",
        "priority": "NORMAL",
        "metadata": {"audience_match_mode": "ALL"},
        "contents": [{"language_code": "en", "title": "Intersection targeting", "body_text": "Only matching crop farmers."}],
        "audience_rules": [
            {"rule_type": "PROJECT", "operator": "IN", "values": [str(project_id)]},
            {"rule_type": "CROP", "operator": "IN", "values": ["RICE"]},
            {"rule_type": "STAGE", "operator": "IN", "values": ["FLOWERING"]},
            {"rule_type": "LOCATION", "operator": "IN", "values": ["Broadcast Village"]},
        ],
    })
    check(all_mode_create.status_code == 201, "Create ALL match-mode draft returns 201", all_mode_create.text)
    all_mode_preview = client.get(f"/api/v1/broadcasts/{all_mode_id}/audience-preview", headers=headers)
    check(all_mode_preview.status_code == 200, "ALL match-mode preview returns 200", all_mode_preview.text)
    all_mode_body = all_mode_preview.json()
    check(all_mode_body["audience_match_mode"] == "ALL", "Audience preview preserves ALL match mode")
    check(all_mode_body["estimated_farmer_count"] == 1, "ALL match mode intersects supported rules")
    check(all_mode_body["sample_farmer_ids"] == [str(crop_farmer_id)], "ALL match mode returns only farmer matching every rule")
    check(set(all_mode_body["sample_matches"][0]["matched_by"]) == {"CROP", "LOCATION", "PROJECT", "STAGE"}, "ALL match mode explains intersected rules")
    print("\n[1c] Generate deliveries")
    generate = client.post(f"/api/v1/broadcasts/{created_id}/generate-deliveries", headers=headers)
    check(generate.status_code == 200, "Generate broadcast deliveries returns 200", generate.text)
    generated = generate.json()
    check(generated["delivery_summary"]["total"] == 3, "Generate creates deliveries for unique targeted farmers")
    check(generated["delivery_summary"]["pending"] == 3, "Generated deliveries start pending")
    check(generated["metadata"]["delivery_generation"] == "GENERATED", "Generation metadata updated")
    check(generated["metadata"]["last_delivery_generation_targeted"] == 3, "Generation metadata records targeted count")
    check(generated["metadata"]["last_delivery_generation_existing"] == 0, "Generation metadata records initial existing count")
    check(generated["metadata"]["last_delivery_generation_created"] == 3, "Generation metadata records created count")
    check(generated["metadata"]["last_delivery_generation_skipped_existing"] == 0, "Generation metadata records skipped existing count")
    generate_again = client.post(f"/api/v1/broadcasts/{created_id}/generate-deliveries", headers=headers)
    check(generate_again.status_code == 200, "Generate deliveries is idempotent", generate_again.text)
    generate_again_body = generate_again.json()
    check(generate_again_body["delivery_summary"]["total"] == 3, "Generate does not duplicate deliveries")
    check(generate_again_body["metadata"]["last_delivery_generation_created"] == 0, "Second generation records zero created")
    check(generate_again_body["metadata"]["last_delivery_generation_skipped_existing"] == 3, "Second generation records skipped existing rows")

    print("\n[1c-detail] Delivery drilldown")
    deliveries = client.get(f"/api/v1/broadcasts/{created_id}/deliveries", headers=headers)
    check(deliveries.status_code == 200, "Broadcast deliveries list returns 200", deliveries.text)
    deliveries_body = deliveries.json()
    check(deliveries_body["schema_version"] == "broadcast_deliveries.v1", "Broadcast deliveries schema stable")
    check(deliveries_body["campaign_id"] == str(created_id), "Broadcast deliveries reference campaign")
    check(deliveries_body["count"] == 3, "Broadcast deliveries list generated rows")
    check(any(row.get("farmer") for row in deliveries_body["deliveries"]), "Broadcast deliveries include farmer context")
    pending_deliveries = client.get(f"/api/v1/broadcasts/{created_id}/deliveries?status=PENDING", headers=headers)
    check(pending_deliveries.status_code == 200, "Broadcast deliveries status filter returns 200", pending_deliveries.text)
    check(pending_deliveries.json()["count"] == 3, "Broadcast deliveries status filter matches pending rows")

    print("\n[1d] Farmer broadcast consumption")
    farmer_feed = client.get(f"/api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code=hi", headers=headers)
    check(farmer_feed.status_code == 200, "Farmer broadcast feed returns 200", farmer_feed.text)
    feed = farmer_feed.json()
    check(feed["schema_version"] == "farmer_broadcasts.v1", "Farmer feed schema stable")
    check(feed["farmer_id"] == str(farmer_id), "Farmer feed preserves farmer id")
    check(feed["count"] == 1, "Farmer feed returns generated delivery")
    check(feed["broadcasts"][0]["campaign"]["id"] == str(created_id), "Farmer feed returns published campaign")
    check(feed["broadcasts"][0]["content"]["language_code"] == "hi", "Farmer feed selects requested language")
    check(feed["broadcasts"][0]["delivery"]["delivery_status"] == "PENDING", "Farmer feed includes delivery state")
    delivery_id = feed["broadcasts"][0]["delivery"]["id"]

    from datetime import timedelta
    db = SessionLocal()
    try:
        future_id = uuid.uuid4()
        expired_id = uuid.uuid4()
        future_campaign = BroadcastCampaign(
            id=future_id,
            tenant_id=tenant_id,
            title="Future scheduled advisory",
            category="GENERAL",
            priority="NORMAL",
            status="PUBLISHED",
            starts_at=now() + timedelta(days=2),
            metadata_={},
            created_at=now(),
            updated_at=now(),
        )
        expired_campaign = BroadcastCampaign(
            id=expired_id,
            tenant_id=tenant_id,
            title="Expired advisory",
            category="GENERAL",
            priority="NORMAL",
            status="PUBLISHED",
            starts_at=now() - timedelta(days=3),
            expires_at=now() - timedelta(days=1),
            metadata_={},
            created_at=now(),
            updated_at=now(),
        )
        db.add(future_campaign)
        db.add(expired_campaign)
        db.flush()
        for campaign_row in [future_campaign, expired_campaign]:
            db.add(BroadcastContent(
                tenant_id=tenant_id,
                campaign_id=campaign_row.id,
                language_code="en",
                title=campaign_row.title,
                body_text="Visibility regression",
                created_at=now(),
                updated_at=now(),
            ))
            db.add(BroadcastDelivery(
                tenant_id=tenant_id,
                campaign_id=campaign_row.id,
                farmer_id=farmer_id,
                delivery_status="PENDING",
                created_at=now(),
                updated_at=now(),
            ))
        db.commit()
    finally:
        db.close()

    visibility_feed = client.get(f"/api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code=en", headers=headers)
    check(visibility_feed.status_code == 200, "Farmer feed visibility filter returns 200", visibility_feed.text)
    visibility_ids = {row["campaign"]["id"] for row in visibility_feed.json()["broadcasts"]}
    check(str(future_id) not in visibility_ids, "Future scheduled broadcast is hidden from farmer feed")
    check(str(expired_id) not in visibility_ids, "Expired broadcast is hidden from farmer feed")

    print("\n[1e] Read and acknowledge delivery")
    read = client.post(f"/api/v1/broadcasts/deliveries/{delivery_id}/read", headers=headers)
    check(read.status_code == 200, "Mark delivery read returns 200", read.text)
    read_body = read.json()
    check(read_body["read_at"] is not None, "Read endpoint sets read_at")
    check(read_body["delivered_at"] is not None, "Read endpoint sets delivered_at")
    check(read_body["delivery_status"] == "DELIVERED", "Read endpoint marks delivery delivered")

    ack = client.post(f"/api/v1/broadcasts/deliveries/{delivery_id}/acknowledge", headers=headers)
    check(ack.status_code == 200, "Acknowledge delivery returns 200", ack.text)
    ack_body = ack.json()
    check(ack_body["acknowledged_at"] is not None, "Acknowledge endpoint sets acknowledged_at")
    check(ack_body["delivery_status"] == "ACKNOWLEDGED", "Acknowledge endpoint marks delivery acknowledged")

    print("\n[1f] Broadcast audit history")
    audit = client.get(f"/api/v1/broadcasts/{created_id}/audit", headers=headers)
    check(audit.status_code == 200, "Broadcast audit returns 200", audit.text)
    audit_body = audit.json()
    check(audit_body["schema_version"] == "broadcast_audit_events.v1", "Broadcast audit schema stable")
    actions = {row["action"] for row in audit_body["events"]}
    check("CREATE_CAMPAIGN" in actions, "Broadcast audit includes create")
    check("PUBLISH_CAMPAIGN" in actions, "Broadcast audit includes publish")
    check("GENERATE_DELIVERIES" in actions, "Broadcast audit includes delivery generation")
    check("MARK_DELIVERY_READ" in actions, "Broadcast audit includes read")
    check("ACKNOWLEDGE_DELIVERY" in actions, "Broadcast audit includes acknowledgement")
    filtered_audit = client.get(f"/api/v1/broadcasts/{created_id}/audit?action=PUBLISH_CAMPAIGN", headers=headers)
    check(filtered_audit.status_code == 200, "Broadcast audit action filter returns 200", filtered_audit.text)
    check(filtered_audit.json()["count"] == 1, "Broadcast audit action filter narrows results")

    isolated_ack = client.post(f"/api/v1/broadcasts/deliveries/{delivery_id}/acknowledge", headers={"X-Tenant-ID": "default"})
    check(isolated_ack.status_code == 404, "Delivery acknowledgement is tenant isolated", isolated_ack.text)
    republish = client.post(f"/api/v1/broadcasts/{created_id}/publish", headers=headers, json={})
    check(republish.status_code == 409, "Published broadcast cannot be republished", republish.text)

    listing = client.get("/api/v1/broadcasts?status=DRAFT", headers=headers)
    check(listing.status_code == 200, "Broadcast list returns 200", listing.text)
    body = listing.json()
    check(body["schema_version"] == "broadcast_campaigns.v1", "Schema version stable")
    check(body["count"] >= 1, "List returns seeded draft campaign")
    row = next(item for item in body["campaigns"] if item["id"] == str(campaign_id))
    check(row["id"] == str(campaign_id), "List preserves seeded campaign id")
    check(row["content_count"] == 2, "List includes content count")
    check(row["audience_rule_count"] == 1, "List includes rule count")
    check(row["delivery_count"] == 1, "List includes delivery count")

    detail = client.get(f"/api/v1/broadcasts/{campaign_id}", headers=headers)
    check(detail.status_code == 200, "Broadcast detail returns 200", detail.text)
    detail_body = detail.json()
    check(len(detail_body["contents"]) == 2, "Detail includes localized content")
    check(any(content.get("media_attachments") for content in detail_body["contents"]), "Detail includes broadcast media attachment")
    check({item["language_code"] for item in detail_body["contents"]} == {"en", "hi"}, "Detail preserves languages")
    check(len(detail_body["audience_rules"]) == 1, "Detail includes audience rules")
    check(detail_body["delivery_summary"]["total"] == 1, "Detail includes delivery summary")

    print("\n[1c-retry] Retry undelivered delivery rows")
    retry1 = client.post(f"/api/v1/broadcasts/{created_id}/retry-undelivered", headers=headers)
    check(retry1.status_code == 200, "Retry undelivered deliveries returns 200", retry1.text)
    retry1_body = retry1.json()
    check(retry1_body["metadata"]["last_delivery_retry_retried"] == 2, "First retry records pending rows only")
    check(retry1_body["metadata"]["last_delivery_retry_marked_failed"] == 0, "First retry does not mark failed")
    retry2 = client.post(f"/api/v1/broadcasts/{created_id}/retry-undelivered", headers=headers)
    check(retry2.status_code == 200, "Second retry returns 200", retry2.text)
    retry3 = client.post(f"/api/v1/broadcasts/{created_id}/retry-undelivered", headers=headers)
    check(retry3.status_code == 200, "Third retry returns 200", retry3.text)
    retry3_body = retry3.json()
    check(retry3_body["metadata"]["last_delivery_retry_marked_failed"] == 2, "Third retry marks remaining pending rows failed")
    failed_after_retry = client.get(f"/api/v1/broadcasts/{created_id}/deliveries?status=FAILED", headers=headers)
    check(failed_after_retry.status_code == 200, "Failed delivery filter returns 200 after retries", failed_after_retry.text)
    check(failed_after_retry.json()["count"] == 2, "Failed delivery filter shows max-retry rows")



    print("\n[1c-life] Broadcast lifecycle transitions")
    expire = client.post(f"/api/v1/broadcasts/{created_id}/expire", headers=headers, json={"reason": "Regression expiry"})
    check(expire.status_code == 200, "Expire published broadcast returns 200", expire.text)
    expired = expire.json()
    check(expired["status"] == "EXPIRED", "Expire changes broadcast status")
    check(expired["delivery_summary"]["total"] == 3, "Expire preserves delivery history")
    generate_after_expire = client.post(f"/api/v1/broadcasts/{created_id}/generate-deliveries", headers=headers)
    check(generate_after_expire.status_code == 409, "Expired broadcast cannot regenerate deliveries", generate_after_expire.text)

    cancel_id = uuid.uuid4()
    cancel_create = client.post("/api/v1/broadcasts", headers=headers, json={
        "id": str(cancel_id),
        "title": "Cancelled draft",
        "category": "GENERAL",
        "priority": "NORMAL",
        "contents": [{"language_code": "en", "title": "Cancelled draft", "body_text": "Not sent."}],
        "audience_rules": [{"rule_type": "FARMER", "operator": "IN", "values": [str(farmer_id)]}],
    })
    check(cancel_create.status_code == 201, "Create cancel regression draft returns 201", cancel_create.text)
    cancel = client.post(f"/api/v1/broadcasts/{cancel_id}/cancel", headers=headers, json={"reason": "Regression cancellation"})
    check(cancel.status_code == 200, "Cancel draft broadcast returns 200", cancel.text)
    check(cancel.json()["status"] == "CANCELLED", "Cancel changes draft broadcast status")

    isolated = client.get(f"/api/v1/broadcasts/{campaign_id}", headers={"X-Tenant-ID": "default"})
    check(isolated.status_code == 404, "Broadcast detail tenant isolated", isolated.text)

    db = SessionLocal()
    try:
        db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(MediaAttachment).filter(MediaAttachment.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastContent).filter(BroadcastContent.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(MediaAsset).filter(MediaAsset.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(CropStageInstance).filter(CropStageInstance.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(CropCycle).filter(CropCycle.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    print("=" * 72)
    print("Broadcast API validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
