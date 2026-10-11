#!/usr/bin/env python3
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = (ROOT / "app/modules/media/broadcast_api.py").read_text(
    encoding="utf-8-sig"
)
BEHAVIOR = (ROOT / "scripts/test_broadcast_api.py").read_text(
    encoding="utf-8-sig"
)


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def function_block(name: str) -> str:
    tree = ast.parse(API)
    node = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    lines = API.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def main() -> int:
    edit_routes = {
        "create_broadcast_campaign",
        "add_broadcast_content",
        "add_broadcast_audience_rule",
    }
    publish_routes = {
        "publish_broadcast_campaign",
        "generate_broadcast_deliveries",
        "retry_undelivered_broadcast_deliveries",
        "expire_broadcast_campaign",
        "cancel_broadcast_campaign",
    }

    for name in sorted(edit_routes):
        block = function_block(name)
        require(
            "require_admin_permission(AdminPermission.EDIT)" in block,
            f"{name} requires administrator edit permission",
        )
        require(
            "principal.tenant_id" in block,
            f"{name} derives tenant from verified administrator",
        )
        require(
            "principal.user_id" in block,
            f"{name} derives actor from verified administrator",
        )
        require(
            "X-Tenant-ID" not in block
            and "X-Actor-ID" not in block,
            f"{name} does not trust identity headers directly",
        )

    for name in sorted(publish_routes):
        block = function_block(name)
        require(
            "require_admin_permission(AdminPermission.PUBLISH)" in block,
            f"{name} requires administrator publish permission",
        )
        require(
            "principal.tenant_id" in block,
            f"{name} derives tenant from verified administrator",
        )
        require(
            "principal.user_id" in block,
            f"{name} derives actor from verified administrator",
        )
        require(
            "X-Tenant-ID" not in block
            and "X-Actor-ID" not in block,
            f"{name} does not trust identity headers directly",
        )

    create = function_block("create_broadcast_campaign")
    publish = function_block("publish_broadcast_campaign")
    transition = function_block("_transition_broadcast_status")

    require(
        "created_by=actor_id" in create
        and "actor_id=body.created_by" not in create,
        "Campaign creation persists verified administrator",
    )
    require(
        "_assert_broadcast_project_scope" in create,
        "Campaign creation tenant-bounds optional project",
    )
    require(
        "campaign.approved_by = actor_id" in publish,
        "Campaign publication persists verified administrator",
    )
    require(
        "actor_id=actor_id" in transition
        and "body.actor_id" not in transition,
        "Terminal lifecycle audit persists verified administrator",
    )
    require(
        "Broadcast creation rejects project outside verified tenant scope"
        in BEHAVIOR,
        "Project-scope denial behavior is tested",
    )
    require(
        "Every administrative broadcast audit uses verified administrator"
        in BEHAVIOR,
        "Administrative audit attribution behavior is tested",
    )
    require(
        '"/deliveries/{delivery_id}/read"' in API
        and '"/deliveries/{delivery_id}/acknowledge"' in API,
        "Farmer delivery mutations retain their separate contract",
    )
    require(
        "android" not in API.lower(),
        "Admin authorization does not claim Android exposure",
    )

    print("BROADCAST ADMIN AUTHORIZATION STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
