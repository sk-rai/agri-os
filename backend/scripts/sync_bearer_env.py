"""Bearer-token headers for persistent Android sync fixtures."""

from __future__ import annotations

import os


def authenticated_sync_headers(
    tenant_id: str,
    fallback_actor_id: str | None = None,
) -> dict[str, str]:
    """Load explicit credentials without creating or mutating users."""

    token = os.environ.get("ANDROID_SYNC_BEARER_TOKEN")
    actor_id = (
        os.environ.get("ANDROID_SYNC_ACTOR_ID")
        or fallback_actor_id
    )

    missing = []
    if not token:
        missing.append("ANDROID_SYNC_BEARER_TOKEN")
    if not actor_id:
        missing.append("ANDROID_SYNC_ACTOR_ID")

    if missing:
        raise SystemExit(
            "Missing sync fixture authentication: "
            + ", ".join(missing)
            + ". Generate a token for the persisted fixture user and "
              "export both ANDROID_SYNC_BEARER_TOKEN and "
              "ANDROID_SYNC_ACTOR_ID."
        )

    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": str(tenant_id),
        "X-Actor-ID": str(actor_id),
    }
