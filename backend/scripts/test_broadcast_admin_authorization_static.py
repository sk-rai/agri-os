#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = (ROOT / "app/modules/media/broadcast_api.py").read_text(encoding="utf-8")
BEHAVIOR = (ROOT / "scripts/test_broadcast_api.py").read_text(encoding="utf-8")


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main() -> int:
    require(API.count("Depends(require_admin_permission(AdminPermission.EDIT))") == 3, "Three edit mutations require admin EDIT")
    require(API.count("Depends(require_admin_permission(AdminPermission.PUBLISH))") == 5, "Five lifecycle mutations require admin PUBLISH")
    require("def create_broadcast_campaign(" in API, "Campaign creation route exists")
    require("def publish_broadcast_campaign(" in API, "Campaign publication route exists")
    require("def retry_undelivered_broadcast_deliveries(" in API, "Delivery retry route exists")
    require("Broadcast mutation rejects missing bearer" in BEHAVIOR, "Missing bearer behavior is tested")
    require("Broadcast mutation rejects actor mismatch" in BEHAVIOR, "Actor mismatch behavior is tested")
    require("Broadcast mutation rejects token/header tenant mismatch" in BEHAVIOR, "Tenant mismatch behavior is tested")
    require('"/deliveries/{delivery_id}/read"' in API and '"/deliveries/{delivery_id}/acknowledge"' in API, "Farmer delivery mutations retain their separate contract")
    require("android" not in API.lower(), "Admin authorization does not claim Android exposure")
    print("BROADCAST ADMIN AUTHORIZATION STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
