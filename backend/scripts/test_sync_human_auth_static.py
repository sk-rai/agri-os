#!/usr/bin/env python3
"""Static contract for the offline sync authenticated-human boundary."""

from __future__ import annotations

import ast
from pathlib import Path


SOURCE_PATH = Path(__file__).resolve().parents[1] / "app/modules/sync/api.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8-sig")


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def function_block(name: str) -> str:
    tree = ast.parse(SOURCE)
    lines = SOURCE.splitlines()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            start = min(
                [node.lineno]
                + [decorator.lineno for decorator in node.decorator_list]
            )
            return "\n".join(lines[start - 1:node.end_lineno])
    raise AssertionError(f"Function not found: {name}")


def main() -> None:
    block = function_block("process_sync_events")

    check(
        "principal: AuthenticatedPrincipal = Depends(" in block
        and "require_authenticated_human()" in block,
        "Sync events requires an authenticated human",
    )
    check(
        "tenant_id=principal.tenant_id" in block,
        "Sync events derives tenant from verified identity",
    )
    check(
        "actor_id=str(principal.user_id)" in block,
        "Sync events derives actor from verified identity",
    )
    check(
        'Header(' not in block
        and 'request.headers.get("X-Actor-ID")' not in block,
        "Sync events does not trust identity headers directly",
    )
    check(
        "service.process_sync_batch(" in block,
        "Sync events preserves batch processing",
    )
    check(
        "authorize_sync_events(" in block,
        "Sync events applies per-event persona authorization",
    )
    check(
        "result.failed.extend(denied_events)" in block,
        "Sync events preserves per-event denial results",
    )
    check(
        "total_processed=len(events_data)" in block,
        "Sync events counts authorized and denied events",
    )

    authorization_source = (
        SOURCE_PATH.parent / "authorization.py"
    ).read_text(encoding="utf-8")
    service_source = (
        SOURCE_PATH.parent / "service.py"
    ).read_text(encoding="utf-8-sig")

    check(
        'payload["user_id"] = str(principal.user_id)'
        in authorization_source,
        "Self-sync enrollment binds verified user",
    )
    check(
        'payload["assigned_user_ids"] = ['
        in authorization_source,
        "Agent sync enrollment binds verified assignment",
    )
    check(
        '"SYNC_SCOPE_DENIED"' in authorization_source,
        "Sync persona denial has stable error",
    )
    check(
        '"assigned_user_ids"' in service_source
        and "_uuid_string_list_or_empty(" in service_source,
        "Farmer materialization persists verified assignment",
    )

    print("SYNC HUMAN AUTH STATIC CONTRACT PASSED")


if __name__ == "__main__":
    main()
