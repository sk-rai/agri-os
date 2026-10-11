#!/usr/bin/env python3
"""Static authorization contract for weather administration mutations."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "app/modules/media/weather_api.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8-sig")
TREE = ast.parse(SOURCE)

TARGETS = {
    "create_weather_provider",
    "run_due_weather_provider_adapters",
    "record_weather_provider_refresh",
    "run_weather_provider_adapter_endpoint",
    "create_weather_snapshot",
    "run_due_weather_refresh_worker",
}


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


functions = {
    node.name: node
    for node in ast.walk(TREE)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}

for function_name in sorted(TARGETS):
    node = functions.get(function_name)
    check(node is not None, f"{function_name} exists")
    body = ast.unparse(node)

    check(
        "AdminPermission.EDIT" in body,
        f"{function_name} requires edit permission",
    )
    check(
        "tenant_id = principal.tenant_id" in body,
        f"{function_name} derives tenant from verified administrator",
    )
    check(
        "actor_id = principal.user_id" in body,
        f"{function_name} derives actor from verified administrator",
    )
    check(
        body.count("x_tenant_id") == 1,
        f"{function_name} does not use tenant header as mutation authority",
    )

check(
    "_record_weather_provider_admin_attribution" in SOURCE,
    "Weather provider persistence records administrative attribution",
)
check(
    "_record_weather_snapshot_admin_attribution" in SOURCE,
    "Weather snapshot persistence records administrative attribution",
)

worker = ast.unparse(functions["_run_due_weather_refresh_worker"])
check(
    "actor_id: uuid.UUID" in worker,
    "Weather refresh worker receives verified actor",
)
check(
    "action='RUN_REFRESH_WORKER'" in worker,
    "Weather refresh worker attributes provider and snapshot writes",
)

create_provider = ast.unparse(functions["create_weather_provider"])
check(
    "action='UPSERT_WEATHER_PROVIDER'" in create_provider,
    "Provider creation records verified administrative action",
)

manual_refresh = ast.unparse(functions["record_weather_provider_refresh"])
check(
    "action='RECORD_PROVIDER_REFRESH'" in manual_refresh,
    "Manual refresh records verified administrative action",
)

adapter = ast.unparse(functions["run_weather_provider_adapter_endpoint"])
check(
    "action='RUN_PROVIDER_ADAPTER'" in adapter,
    "Adapter execution records verified administrative action",
)

due = ast.unparse(functions["run_due_weather_provider_adapters"])
check(
    "action='RUN_DUE_PROVIDER_ADAPTERS'" in due,
    "Due-provider execution records verified administrative action",
)

snapshot = ast.unparse(functions["create_weather_snapshot"])
check(
    "action='CREATE_WEATHER_SNAPSHOT'" in snapshot,
    "Manual snapshot creation records verified administrative action",
)

print("WEATHER ADMINISTRATION AUTH STATIC CONTRACT PASSED")
