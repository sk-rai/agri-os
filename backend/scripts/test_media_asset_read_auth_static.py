#!/usr/bin/env python3
"""Static authorization contract for media asset detail reads."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "app/modules/media/api.py"
source = API_PATH.read_text(encoding="utf-8-sig")
tree = ast.parse(source)


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


node = next(
    (
        item
        for item in ast.walk(tree)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == "get_media_asset"
    ),
    None,
)
check(node is not None, "Media asset detail route exists")
route = ast.get_source_segment(source, node) or ""

check(
    "require_authenticated_human()" in route,
    "Media asset detail requires authenticated human",
)
check(
    "tenant_id = principal.tenant_id" in route,
    "Media asset detail derives verified tenant",
)
check(
    "actor_id = principal.user_id" in route,
    "Media asset detail derives verified actor",
)
check(
    "MediaAsset.tenant_id == tenant_id" in route,
    "Media asset detail tenant-bounds selected asset",
)
check(
    "asset.uploaded_by != actor_id" in route,
    "Media asset detail permits verified uploader",
)
check(
    "_require_media_creation_scope(" in route,
    "Media asset detail reuses persona scope",
)
check(
    "project_id=asset.project_id" in route,
    "Media asset detail preserves project scope",
)
check(
    "farmer_id=asset.farmer_id" in route,
    "Media asset detail preserves farmer scope",
)
check(
    "Header(" not in route and "x_tenant_id" not in route,
    "Media asset detail does not trust tenant header directly",
)
check(
    "db.add(" not in route
    and "db.commit(" not in route
    and "db.flush(" not in route
    and "db.delete(" not in route,
    "Media asset detail remains database read-only",
)

print("MEDIA ASSET READ AUTH STATIC CONTRACT PASSED")
