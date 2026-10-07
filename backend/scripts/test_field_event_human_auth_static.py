#!/usr/bin/env python3
"""Static contract for authenticated field-event mutations."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = (ROOT / "backend/app/modules/media/api.py").read_text(encoding="utf-8")
FIXTURE = (
    ROOT / "backend/scripts/prepare_android_field_event_advisory_loop.py"
).read_text(encoding="utf-8")


def require(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main():
    create_start = API.index('@field_events_router.post("", status_code=201)')
    create_end = API.index('@field_events_router.get("")', create_start)
    create = API[create_start:create_end]

    status_start = API.index(
        '@field_events_router.patch("/{event_id}/status")'
    )
    status = API[status_start:]

    require(
        "Depends(require_authenticated_human())" in create,
        "Field-event creation requires an authenticated human",
    )
    require(
        "Depends(require_authenticated_human())" in status,
        "Field-event status requires an authenticated human",
    )
    require(
        "principal.tenant_id" in create and "x_tenant_id" not in create,
        "Creation derives tenant from verified identity",
    )
    require(
        "principal.tenant_id" in status and "x_tenant_id" not in status,
        "Status derives tenant from verified identity",
    )
    require(
        '"reported_by_user_id": str(principal.user_id)' in create,
        "Creation records verified reporter",
    )
    require(
        '"actor_user_id": str(principal.user_id)' in status,
        "Status history records verified actor",
    )
    require(
        'body.status != "REPORTED"' in create,
        "New events must start reported",
    )
    require(
        'source=source' in create,
        "Event source is server derived",
    )
    require(
        '"FARMER_ANDROID"' in API
        and '"FIELD_AGENT_ANDROID"' in API
        and '"ADMIN_WEB"' in API,
        "Human persona sources are explicit",
    )
    require(
        "external_source=None" in create
        and "external_event_id=None" in create,
        "Human route cannot impersonate external providers",
    )
    require(
        "asset.farmer_id != body.farmer_id" in create,
        "Inline asset farmer must match",
    )
    require(
        "asset.project_id != body.project_id" in create,
        "Inline asset project must match",
    )
    require(
        "FIELD_EVENT_TRANSITIONS" in API,
        "Status transition matrix is explicit",
    )
    require(
        'target_status == "ADVISORY_SENT"' in API,
        "Advisory-sent transition has a dedicated boundary",
    )
    require(
        "scope.has_agent_persona" in API,
        "Operational status changes require an agent persona",
    )
    require(
        "scope.is_assigned_to_farmer(event.farmer_id)" in API,
        "Operational status changes require farmer assignment",
    )
    require(
        "reporting_farmer_headers()" in FIXTURE,
        "Deterministic Android fixture resolves the reporting farmer",
    )
    require(
        "headers=reporter_headers" in FIXTURE,
        "Farmer bearer creates media and field event",
    )
    require(
        'event["source"] == "FARMER_ANDROID"' in FIXTURE,
        "Fixture verifies server-derived farmer source",
    )
    require(
        'ADMIN_ACTOR_ID' in FIXTURE
        and 'authenticated_headers()' in FIXTURE,
        "Web-admin identity remains distinct",
    )
    require(
        '"reported_by_user_id"' in FIXTURE,
        "Fixture verifies authenticated reporter attribution",
    )

    print("FIELD EVENT HUMAN AUTH STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
