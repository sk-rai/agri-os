#!/usr/bin/env python3
"""Static contract for authenticated generic media attachment creation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = (ROOT / "backend/app/modules/media/api.py").read_text(encoding="utf-8")


def require(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main():
    attachment_start = API.index('@router.post("/attachments", status_code=201)')
    attachment_end = API.index('@router.get("/attachments")', attachment_start)
    route = API[attachment_start:attachment_end]

    read_start = API.index(
        "def _require_media_attachment_read_target_scope("
    )
    read_end = API.index("FIELD_EVENT_TRANSITIONS", read_start)
    read_route = API[read_start:read_end]

    helper_start = API.index("def _require_media_attachment_scope(")
    helper_end = API.index('@router.post("/assets", status_code=201)', helper_start)
    helper = API[helper_start:helper_end]

    require(
        "Depends(require_authenticated_human())" in route,
        "Attachment creation requires an authenticated human",
    )
    require(
        "principal.tenant_id" in route,
        "Attachment tenant is derived from verified identity",
    )
    require(
        '"created_by_user_id": str(principal.user_id)' in route,
        "Attachment actor is derived from verified identity",
    )
    require(
        "x_tenant_id" not in route,
        "Attachment creation does not trust tenant headers directly",
    )
    require(
        "_require_media_attachment_scope(" in route,
        "Attachment creation authorises asset and target",
    )
    require(
        "_require_media_creation_scope(" in helper,
        "Attachment helper authorises the asset context",
    )
    require(
        'entity_type == "FARMER"' in helper,
        "Farmer attachment target is explicit",
    )
    require(
        'entity_type == "PARCEL"' in helper,
        "Parcel attachment target is explicit",
    )
    require(
        'entity_type == "FIELD_EVENT"' in helper,
        "Field-event attachment target is explicit",
    )
    require(
        'entity_type == "ADVISORY"' in helper,
        "Advisory attachment target is explicit",
    )
    require(
        "_media_admin_can_edit(principal)" in helper,
        "Advisory attachment remains web-admin controlled",
    )
    require(
        "BroadcastContent.id == entity_id" in helper,
        "Advisory target resolves persisted broadcast content",
    )
    require(
        "BroadcastCampaign.is_active == True" in helper,
        "Advisory target requires an active campaign",
    )
    require(
        "asset.farmer_id != target_farmer_id" in helper,
        "Cross-farmer attachment is rejected",
    )
    require(
        "asset.project_id != target_project_id" in helper,
        "Cross-project attachment is rejected",
    )
    require(
        "MEDIA_ATTACHMENT_TARGET_UNSUPPORTED" in API,
        "Unmapped generic attachment targets fail closed",
    )
    require(
        'entity_type != "ADVISORY"' in helper,
        "Operational targets use persona-scoped authorization",
    )
    require(
        "Depends(require_authenticated_human())" in read_route,
        "Attachment listing requires an authenticated human",
    )
    require(
        "principal.tenant_id" in read_route
        and "x_tenant_id" not in read_route,
        "Attachment listing derives tenant from verified identity",
    )
    require(
        "_media_attachment_read_scope_required" in read_route,
        "Operational listing requires an exact target scope",
    )
    require(
        "_require_media_attachment_read_target_scope(" in read_route,
        "Attachment listing authorises its target",
    )
    require(
        'entity_type == "FARMER"' in read_route
        and 'entity_type == "PARCEL"' in read_route
        and 'entity_type == "FIELD_EVENT"' in read_route,
        "Operational read targets are explicit",
    )
    require(
        'entity_type == "ADVISORY"' in read_route
        and "_media_admin_can_edit(principal)" in read_route,
        "Advisory attachment listing remains web-admin controlled",
    )
    require(
        "MediaAsset.tenant_id == principal.tenant_id" in read_route,
        "Attachment listing tenant-bounds joined assets",
    )

    print("MEDIA ATTACHMENT HUMAN AUTH STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
