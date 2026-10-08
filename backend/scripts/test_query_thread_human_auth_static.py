#!/usr/bin/env python3
"""Static contract for authenticated query-thread mutations."""

from pathlib import Path


ROOT = Path(__file__).resolve()
for parent in ROOT.parents:
    candidate = parent / "backend" / "app" / "modules" / "media" / "query_api.py"
    if candidate.exists():
        API_PATH = candidate
        break
else:
    API_PATH = Path("backend/app/modules/media/query_api.py")

API = API_PATH.read_text()


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def route_slice(start: str, end: str | None = None) -> str:
    begin = API.index(start)
    finish = API.index(end, begin) if end else len(API)
    return API[begin:finish]


def main() -> int:
    create = route_slice('@router.post("", status_code=201)', 'def _query_visible_farmer_ids')
    listing = route_slice('@router.get("")', '@router.get("/{thread_id}")')
    detail = route_slice(
        '@router.get("/{thread_id}")',
        '@router.post("/{thread_id}/messages", status_code=201)',
    )
    message = route_slice(
        '@router.post("/{thread_id}/messages", status_code=201)',
        '@router.patch("/{thread_id}/status")',
    )
    status = route_slice('@router.patch("/{thread_id}/status")')
    helper = route_slice("def _query_scope_forbidden", '@router.post("", status_code=201)')

    require("Depends(require_authenticated_human())" in create, "Thread creation requires an authenticated human")
    require("Depends(require_authenticated_human())" in listing, "Thread listing requires an authenticated human")
    require("Depends(require_authenticated_human())" in detail, "Thread detail requires an authenticated human")
    require("Depends(require_authenticated_human())" in message, "Message creation requires an authenticated human")
    require("Depends(require_authenticated_human())" in status, "Status mutation requires an authenticated human")
    require("tenant_id = principal.tenant_id" in create, "Thread tenant is derived from verified identity")
    require("tenant_id = principal.tenant_id" in listing, "List tenant is derived from verified identity")
    require("tenant_id = principal.tenant_id" in detail, "Detail tenant is derived from verified identity")
    require("tenant_id = principal.tenant_id" in message, "Message tenant is derived from verified identity")
    require("tenant_id = principal.tenant_id" in status, "Status tenant is derived from verified identity")
    require("def _query_visible_farmer_ids" in API, "Query read visibility helper exists")
    require("scope.own_farmer_ids | scope.assigned_farmer_ids" in API, "Read visibility combines personal and assigned farmers")
    require("QueryThread.farmer_id.in_(visible_farmer_ids)" in listing, "Thread listing applies persona farmer visibility")
    require("thread.farmer_id not in visible_farmer_ids" in detail, "Thread detail rejects inaccessible farmers")
    require('raise HTTPException(404, "Query thread not found")' in detail, "Thread detail fails closed without existence disclosure")
    require("MediaAsset.tenant_id == tenant_id" in detail, "Detail tenant-bounds joined attachment assets")
    require("_require_media_creation_scope(" in helper, "Query scope reuses strict farmer and project capability")
    require("resolve_human_persona_scope" in helper, "Query actor resolves operational persona")
    require("scope.owns_farmer" in helper, "Personal farmer capability is explicit")
    require("scope.is_assigned_to_farmer" in helper, "Assigned agent capability is explicit")
    require("sender_id must match the authenticated user" in helper, "Sender impersonation is rejected")
    require('"sender_id": principal.user_id' in helper, "Message sender is server derived")
    require("asset.farmer_id != thread.farmer_id" in helper, "Inline assets must match thread farmer")
    require("asset.project_id != thread.project_id" in helper, "Inline assets must match thread project")
    require("actor_id=principal.user_id" in create, "Thread audit records verified actor")
    require("actor_id=principal.user_id" in message, "Message audit records verified actor")
    require("actor_id=principal.user_id" in status, "Status audit records verified actor")
    require('actor_type == "FARMER"' in status, "Farmer workflow transitions are denied")
    require("Only a web administrator may assign" in create and "Only a web administrator may assign" in status, "Thread assignment remains web-admin controlled")
    require('"actor_user_id": str(principal.user_id)' in status, "Status history records verified actor")
    require("x_tenant_id" not in create and "x_tenant_id" not in message and "x_tenant_id" not in status, "Query mutations do not trust tenant headers directly")
    require("x_tenant_id" not in listing and "x_tenant_id" not in detail, "Query reads do not trust tenant headers directly")
    print("QUERY THREAD HUMAN AUTH STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
