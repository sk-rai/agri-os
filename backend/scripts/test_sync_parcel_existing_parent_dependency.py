"""Focused regression for parcel dependencies on pre-existing farmers."""

import uuid

from app.core.database import SessionLocal
from app.core.human_auth import AuthenticatedPrincipal
from app.modules.auth.models import User
from app.modules.farmer.models import Farmer, Parcel, Tenant
from app.modules.master_data.models.geography import GeographyVillage  # noqa: F401
from app.modules.sync.authorization import authorize_sync_events
from app.modules.sync.api import process_validated_sync_events
from app.modules.sync.schemas import SyncBatchRequest
from app.modules.sync.models import AuditChainEntry, SyncProcessedEvent
from app.modules.sync.service import (
    SyncEvent,
    _materialize_parcel_event,
    process_sync_batch,
    validate_dependencies,
)


checks = 0


def check(condition: bool, label: str) -> None:
    global checks
    checks += 1
    if not condition:
        raise AssertionError(label)


def parcel_event(*, event_id, entity_id, farmer_id, dependency_id):
    return {
        "event_id": str(event_id),
        "entity_type": "parcel",
        "entity_id": str(entity_id),
        "operation": "CREATE",
        "payload": {
            "farmer_id": str(farmer_id),
            "reported_area": "1.00",
            "reported_area_unit": "BIGHA",
            "ownership_type": "OWNED",
            "geometry_source": "PIN_DROP",
            "centroid_lat": "26.80000000",
            "centroid_lng": "82.46000000",
        },
        "version": 1,
        "dependency_ids": [str(dependency_id)],
        "metadata": {"source": "synthetic-focused-regression"},
    }


db = SessionLocal()
tenant_id = f"parcel-parent-{uuid.uuid4().hex[:12]}"
other_tenant_id = f"parcel-parent-other-{uuid.uuid4().hex[:12]}"
actor_id = uuid.uuid4()
try:
    db.add_all(
        [
            Tenant(id=tenant_id, name="Parcel Parent Regression", type="ENTERPRISE"),
            Tenant(id=other_tenant_id, name="Other Parcel Parent", type="ENTERPRISE"),
        ]
    )
    db.commit()
    farmer_id = uuid.uuid4()
    owner_user_id = uuid.uuid4()
    destination_farmer_id = uuid.uuid4()
    other_farmer_id = uuid.uuid4()
    inactive_farmer_id = uuid.uuid4()
    db.add_all(
        [
            User(
                id=owner_user_id,
                tenant_id=tenant_id,
                mobile_number="+919700000010",
                role="FARMER",
                display_name="Synthetic Parcel Owner",
            ),
            Farmer(
                id=farmer_id,
                tenant_id=tenant_id,
                user_id=owner_user_id,
                mobile_number="+919700000001",
                display_name="Synthetic Existing Farmer",
                status="ACTIVE",
            ),
            Farmer(
                id=destination_farmer_id,
                tenant_id=tenant_id,
                mobile_number="+919700000011",
                display_name="Unauthorized Destination Farmer",
                status="ACTIVE",
            ),
            Farmer(
                id=other_farmer_id,
                tenant_id=other_tenant_id,
                mobile_number="+919700000002",
                display_name="Synthetic Cross Tenant Farmer",
                status="ACTIVE",
            ),
            Farmer(
                id=inactive_farmer_id,
                tenant_id=tenant_id,
                mobile_number="+919700000003",
                display_name="Synthetic Inactive Farmer",
                status="INACTIVE",
            ),
        ]
    )
    db.commit()

    event_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    event = parcel_event(
        event_id=event_id,
        entity_id=parcel_id,
        farmer_id=farmer_id,
        dependency_id=farmer_id,
    )
    result = process_sync_batch(db, tenant_id, str(actor_id), [event])
    check(result.accepted == [str(event_id)], "existing same-tenant farmer accepted")
    check(result.failed == [], "existing farmer has no dependency failure")
    rows = db.query(Parcel).filter(Parcel.id == parcel_id).all()
    check(len(rows) == 1, "exactly one parcel materialized")
    check(rows[0].farmer_id == farmer_id, "parcel keeps farmer identity")
    committed = db.query(SyncProcessedEvent).filter(
        SyncProcessedEvent.event_id == event_id
    ).one()
    check(committed.entity_id == parcel_id, "event keeps parcel identity")
    check(committed.status == "COMMITTED", "event committed after materialization")
    audit_count = db.query(AuditChainEntry).filter(
        AuditChainEntry.tenant_id == tenant_id,
        AuditChainEntry.entity_id == parcel_id,
    ).count()

    replay = process_sync_batch(db, tenant_id, str(actor_id), [event])
    check(replay.accepted == [str(event_id)], "exact replay accepted")
    check(db.query(Parcel).filter(Parcel.id == parcel_id).count() == 1, "replay creates no parcel")
    check(
        db.query(AuditChainEntry).filter(
            AuditChainEntry.tenant_id == tenant_id,
            AuditChainEntry.entity_id == parcel_id,
        ).count()
        == audit_count,
        "replay creates no operational audit",
    )

    missing_farmer_id = uuid.uuid4()
    missing_event_id = uuid.uuid4()
    missing_parcel_id = uuid.uuid4()
    missing = process_sync_batch(
        db,
        tenant_id,
        str(actor_id),
        [
            parcel_event(
                event_id=missing_event_id,
                entity_id=missing_parcel_id,
                farmer_id=missing_farmer_id,
                dependency_id=missing_farmer_id,
            )
        ],
    )
    check(missing.failed[0]["error_code"] == "DEPENDENCY_MISSING", "missing farmer rejected")
    check(db.query(Parcel).filter(Parcel.id == missing_parcel_id).count() == 0, "missing farmer has no parcel")
    check(
        db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == missing_event_id,
            SyncProcessedEvent.status == "COMMITTED",
        ).count()
        == 0,
        "missing farmer has no committed event",
    )

    cross_event_id = uuid.uuid4()
    cross_parcel_id = uuid.uuid4()
    cross = process_sync_batch(
        db,
        tenant_id,
        str(actor_id),
        [
            parcel_event(
                event_id=cross_event_id,
                entity_id=cross_parcel_id,
                farmer_id=other_farmer_id,
                dependency_id=other_farmer_id,
            )
        ],
    )
    check(cross.failed[0]["error_code"] == "DEPENDENCY_MISSING", "cross-tenant farmer rejected")
    check(db.query(Parcel).filter(Parcel.id == cross_parcel_id).count() == 0, "cross-tenant farmer has no parcel")

    inactive_event_id = uuid.uuid4()
    inactive = process_sync_batch(
        db,
        tenant_id,
        str(actor_id),
        [
            parcel_event(
                event_id=inactive_event_id,
                entity_id=uuid.uuid4(),
                farmer_id=inactive_farmer_id,
                dependency_id=inactive_farmer_id,
            )
        ],
    )
    check(inactive.failed[0]["error_code"] == "DEPENDENCY_MISSING", "inactive farmer rejected")

    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        mobile_number="+919700000004",
        role="FIELD_AGENT",
        display_name="Unassigned Synthetic Agent",
    )
    db.add(user)
    db.commit()
    unauthorized_event = parcel_event(
        event_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        farmer_id=farmer_id,
        dependency_id=farmer_id,
    )
    authorized, denied = authorize_sync_events(
        db,
        principal=AuthenticatedPrincipal(
            user_id=user.id,
            tenant_id=tenant_id,
            role="FIELD_AGENT",
        ),
        events=[unauthorized_event],
    )
    check(authorized == [], "unauthorized event is not admitted")
    check(denied[0]["error_code"] == "SYNC_SCOPE_DENIED", "unauthorized rejection is sanitized")

    parent_event_id = uuid.uuid4()
    db.add(
        SyncProcessedEvent(
            event_id=parent_event_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            entity_type="farmer",
            entity_id=uuid.uuid4(),
            operation="CREATE",
            server_version=1,
            status="DEPENDENCY_MISSING",
        )
    )
    db.commit()
    blocked_event = SyncEvent(
        parcel_event(
            event_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            farmer_id=farmer_id,
            dependency_id=parent_event_id,
        )
    )
    check(
        validate_dependencies(db, tenant_id, blocked_event.dependency_ids, blocked_event)
        == [str(parent_event_id)],
        "uncommitted parent event remains blocked",
    )

    unrelated = SyncEvent(
        {
            "event_id": str(uuid.uuid4()),
            "entity_type": "crop_cycle",
            "entity_id": str(uuid.uuid4()),
            "operation": "CREATE",
            "payload": {"farmer_id": str(farmer_id)},
            "version": 1,
            "dependency_ids": [str(farmer_id)],
        }
    )
    check(
        validate_dependencies(db, tenant_id, unrelated.dependency_ids, unrelated)
        == [str(farmer_id)],
        "unrelated entity dependency behavior unchanged",
    )

    existing_parcel_id = uuid.uuid4()
    mismatch_event_id = uuid.uuid4()
    db.add(
        Parcel(
            id=existing_parcel_id,
            tenant_id=tenant_id,
            farmer_id=farmer_id,
            reported_area="1.00",
            reported_area_unit="BIGHA",
            ownership_type="OWNED",
            status="ACTIVE",
        )
    )
    db.commit()
    mismatch_event = parcel_event(
        event_id=mismatch_event_id,
        entity_id=existing_parcel_id,
        farmer_id=destination_farmer_id,
        dependency_id=destination_farmer_id,
    )
    authorized, denied = authorize_sync_events(
        db,
        principal=AuthenticatedPrincipal(
            user_id=owner_user_id,
            tenant_id=tenant_id,
            role="FARMER",
        ),
        events=[mismatch_event],
    )
    check(authorized == [], "existing parcel farmer mismatch is not admitted")
    check(denied[0]["error_code"] == "SYNC_SCOPE_DENIED", "farmer mismatch is sanitized")
    check(
        db.query(Parcel).filter(Parcel.id == existing_parcel_id).one().farmer_id
        == farmer_id,
        "rejected mismatch leaves parcel farmer unchanged",
    )
    check(
        db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == mismatch_event_id,
            SyncProcessedEvent.status == "COMMITTED",
        ).count()
        == 0,
        "rejected mismatch creates no committed ledger event",
    )

    ingress_result = process_validated_sync_events(
        events=SyncBatchRequest(events=[mismatch_event]).events,
        principal=AuthenticatedPrincipal(
            user_id=owner_user_id,
            tenant_id=tenant_id,
            role="FARMER",
        ),
        db=db,
    )
    check(ingress_result.accepted == [], "sync ingress does not forward farmer mismatch")
    check(
        ingress_result.failed[0].detail_code == "PARCEL_FARMER_MISMATCH",
        "sync ingress preserves sanitized mismatch category",
    )
    check(
        db.query(SyncProcessedEvent).filter(
            SyncProcessedEvent.event_id == mismatch_event_id,
        ).count()
        == 0,
        "sync ingress mismatch creates no ledger row",
    )

    mismatch_sync_event = SyncEvent(mismatch_event)
    check(
        validate_dependencies(
            db,
            tenant_id,
            mismatch_sync_event.dependency_ids,
            mismatch_sync_event,
        )
        == [str(destination_farmer_id)],
        "dependency guard retains mismatched destination farmer dependency",
    )
    try:
        _materialize_parcel_event(db, tenant_id, mismatch_sync_event)
    except ValueError as exc:
        check(
            "farmer does not match" in str(exc),
            "materializer independently rejects farmer reassignment",
        )
    else:
        raise AssertionError("materializer accepted farmer reassignment")
    check(
        db.query(Parcel).filter(Parcel.id == existing_parcel_id).one().farmer_id
        == farmer_id,
        "materializer rejection leaves parcel farmer unchanged",
    )

    same_owner_event_id = uuid.uuid4()
    same_owner_event = parcel_event(
        event_id=same_owner_event_id,
        entity_id=existing_parcel_id,
        farmer_id=farmer_id,
        dependency_id=farmer_id,
    )
    same_owner_result = process_validated_sync_events(
        events=SyncBatchRequest(events=[same_owner_event]).events,
        principal=AuthenticatedPrincipal(
            user_id=owner_user_id,
            tenant_id=tenant_id,
            role="FARMER",
        ),
        db=db,
    )
    check(
        same_owner_result.accepted == [str(same_owner_event_id)],
        "same-owner existing parcel CREATE remains accepted",
    )
    check(
        db.query(Parcel).filter(Parcel.id == existing_parcel_id).count() == 1,
        "same-owner CREATE reuse preserves one parcel",
    )
    check(
        db.query(Parcel).filter(Parcel.id == existing_parcel_id).one().farmer_id
        == farmer_id,
        "same-owner CREATE reuse preserves farmer binding",
    )

    print(f"PASS checks={checks}")
finally:
    db.rollback()
    db.close()
