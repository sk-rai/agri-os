#!/usr/bin/env python3
"""Static guard for the bounded, lossless sync-ingress implementation.

This script reads source only. It does not import the application, open a
database, start HTTP, or execute the async request parser.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INGRESS = ROOT / "app/modules/sync/ingress.py"
API = ROOT / "app/modules/sync/api.py"
SCHEMAS = ROOT / "app/modules/sync/schemas.py"
PACKAGE = ROOT / "app/modules/sync/__init__.py"
MAIN = ROOT / "app/main.py"


def require(source: str, fragment: str) -> None:
    assert fragment in source, f"missing static contract: {fragment}"


def main() -> None:
    ingress = INGRESS.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    schemas = SCHEMAS.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")

    for fragment in (
        "MAX_SYNC_BODY_BYTES = 2 * 1024 * 1024",
        "async for chunk in request.stream()",
        "MAX_SYNC_BODY_BYTES + 1",
        "_scan_json_limits(text)",
        "MAX_JSON_NUMBER_CHARS",
        "parse_int=_number",
        "parse_float=_number",
        "object_pairs_hook=_object",
        "event_uuid = _event_id(event)",
        "_token_sensitive_preflight(event)",
        "_activity_preflight(event)",
        "DUPLICATE_EVENT_ID_CONFLICT",
        'frozenset({"crop_activity", "cropactivity"})',
        "ACTIVITY_OPERATION_UNSUPPORTED",
        "CYCLE_LOCK_PLAN_INVALID",
        "_canonical_lossless_envelope",
        "ActivityCreate.model_validate(activity_payload)",
        're.fullmatch(r"[1-9][0-9]*", version.token)',
        "Unsupported activity entity type spelling.",
    ):
        require(ingress, fragment)

    for fragment in (
        "async def process_sync_events(",
        "await preflight_sync_request(",
        "await run_in_threadpool(",
        "db = SessionLocal()",
        "db.close()",
        "return process_validated_sync_events(",
        "for item in events",
        '"_sync_envelope_canonical": canonical_envelope',
    ):
        require(api, fragment)

    for fragment in (
        "class SyncEventPayload(BaseModel):",
        "class SyncBatchRequest(BaseModel):",
        'model_config = ConfigDict(extra="forbid")',
    ):
        require(schemas, fragment)

    assert "app.modules.sync.api" not in package
    assert "app.modules.sync.dashboard" not in package
    assert "app.modules.sync.conflicts" not in package
    for fragment in (
        "from app.modules.sync.api import router as sync_router",
        "from app.modules.sync.dashboard import router as dashboard_router",
        "from app.modules.sync.conflicts import router as conflicts_router",
    ):
        require(main, fragment)

    print("SYNC_LOSSLESS_INGRESS_STATIC_OK")


if __name__ == "__main__":
    main()
