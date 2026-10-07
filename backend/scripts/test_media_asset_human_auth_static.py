#!/usr/bin/env python3
"""Static contract for authenticated media asset mutations."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = (ROOT / "backend/app/modules/media/api.py").read_text(encoding="utf-8")
FIELD_LOOP = (
    ROOT / "backend/scripts/prepare_android_field_event_advisory_loop.py"
).read_text(encoding="utf-8")
LANGUAGE_FIXTURE = (
    ROOT / "backend/scripts/verify_broadcast_language_fallback_delivery.py"
).read_text(encoding="utf-8")
MEDIA_FIXTURE = (
    ROOT / "backend/scripts/verify_broadcast_media_attachment_delivery.py"
).read_text(encoding="utf-8")
FIELD_EVENT_TEST = (
    ROOT / "backend/scripts/test_field_event_reports.py"
).read_text(encoding="utf-8")


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def route_body(start: str, end: str) -> str:
    return API.split(start, 1)[1].split(end, 1)[0]


def main() -> int:
    create = route_body(
        'def create_media_asset(',
        '@router.post("/assets/{asset_id}/complete")',
    )
    complete = route_body(
        'def complete_media_asset(',
        '@router.get("/assets/{asset_id}")',
    )

    require(
        "require_authenticated_human()" in create,
        "Asset creation requires an authenticated human",
    )
    require(
        "require_authenticated_human()" in complete,
        "Asset completion requires an authenticated human",
    )
    require(
        "tenant_id=principal.tenant_id" in create,
        "Asset tenant is derived from verified identity",
    )
    require(
        "uploaded_by=principal.user_id" in create,
        "Uploader is derived from verified identity",
    )
    require(
        "body.uploaded_by != principal.user_id" in create,
        "Uploader impersonation is rejected",
    )
    require(
        "resolve_human_persona_scope" in API,
        "Farmer and agent personas are resolved",
    )
    require(
        "scope.can_operate_farmer(farmer.id)" in API,
        "Personal and assigned farmer capabilities are accepted",
    )
    require(
        "FarmerProjectEnrollment.status == \"ACTIVE\"" in API,
        "Project/farmer relationship requires active enrollment",
    )
    require(
        "AdminPermission.EDIT" in API,
        "Existing web-admin edit capability is retained",
    )
    require(
        "MEDIA_WEB_ADMIN_ROLES" in API,
        "Web-admin media bypass uses an explicit role boundary",
    )
    require(
        '"AGRONOMIST"' not in API.split(
            "MEDIA_WEB_ADMIN_ROLES =",
            1,
        )[1].split("}", 1)[0],
        "Agronomist is not treated as a web administrator",
    )
    require(
        '"FIELD_AGENT"' not in API.split(
            "MEDIA_WEB_ADMIN_ROLES =",
            1,
        )[1].split("}", 1)[0],
        "Field agent is not treated as a web administrator",
    )
    require(
        "Project-only media requires an authorised web administrator." in API,
        "Project-only media remains web-admin controlled",
    )
    require(
        "asset.uploaded_by != principal.user_id" in complete,
        "Original uploader may complete their asset",
    )
    require(
        "MediaAsset.tenant_id == principal.tenant_id" in complete,
        "Asset completion is tenant isolated",
    )
    require(
        '"/assets"' in API and '"/assets/{asset_id}/complete"' in API,
        "Existing endpoint paths remain stable",
    )
    require(
        "x_tenant_id" not in create and "x_tenant_id" not in complete,
        "Asset mutations do not trust tenant headers directly",
    )
    for source, label in (
        (FIELD_LOOP, "Field-event advisory fixture"),
        (LANGUAGE_FIXTURE, "Language fallback fixture"),
        (MEDIA_FIXTURE, "Broadcast media fixture"),
    ):
        require(
            "def authenticated_headers()" in source,
            f"{label} resolves a persisted identity",
        )
        require(
            '"Authorization": f"Bearer {token}"' in source,
            f"{label} sends a bearer token",
        )
        require(
            "User.id == ACTOR_ID" in source,
            f"{label} binds its deterministic actor",
        )
    require(
        "create_test_admin" in FIELD_EVENT_TEST
        and "delete_test_admin" in FIELD_EVENT_TEST,
        "Field-event regression bounds its temporary identity",
    )
    print("MEDIA ASSET HUMAN AUTH STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
