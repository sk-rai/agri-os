#!/usr/bin/env python3
"""Regression for the production runtime lookup design contract."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv/bin/python"
SCRIPT = (
    ROOT
    / "backend/scripts/"
    / "plan_nwdp_runtime_lookup_production_design.py"
)


def check(
    label: str,
    condition: bool,
    payload=None,
) -> None:
    if not condition:
        print(f"FAIL {label}")
        if payload is not None:
            print(json.dumps(
                payload,
                indent=2,
                default=str,
            )[:4000])
        raise SystemExit(1)
    print(f"PASS {label}")


def main() -> None:
    with tempfile.TemporaryDirectory(
        prefix="runtime-lookup-production-design-",
    ) as directory:
        output = Path(directory) / "design.json"

        proc = subprocess.run(
            [
                str(PYTHON),
                str(SCRIPT),
                "--output",
                str(output),
            ],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        check(
            "Design exits zero",
            proc.returncode == 0,
            proc.stdout,
        )
        check(
            "Design output is written",
            output.exists(),
        )

        data = json.loads(
            output.read_text(encoding="utf-8")
        )
        storage = data["storage_design"]
        query = data["lookup_query_design"]
        api = data["api_contract"]
        enablement = data["enablement_design"]
        readiness = data["readiness"]
        guardrails = data["guardrails"]
        reuse = data["reuse_decision"]

        check(
            "Design is healthy",
            data["healthy"] is True,
            data,
        )
        check(
            "Design remains unauthorized",
            data["status"]
            == "DESIGNED_NOT_AUTHORIZED",
            data,
        )
        check(
            "Runtime identities and crosswalks are reused",
            reuse["reuse_runtime_feature_identity"]
            and reuse["reuse_runtime_crosswalk_identity"]
            and reuse["reuse_village_crosswalks"],
            reuse,
        )
        check(
            "JSONB is rejected for production lookup",
            reuse["reuse_jsonb_geometry_for_production"]
            is False,
            reuse,
        )
        check(
            "Native PostGIS geometry is designed",
            storage["new_geometry_column"]["type"]
            == "geometry(Geometry,4326)",
            storage,
        )
        check(
            "Partial GiST index is required",
            storage["index"]["method"] == "GIST"
            and "is_active = true"
            in storage["index"]["predicate"],
            storage["index"],
        )
        check(
            "ST_Covers behavior is retained",
            query["spatial_predicate"]
            == "ST_Covers",
            query,
        )
        check(
            "Ambiguity fails closed",
            query["result_policy"]["multiple_matches"]
            == "AMBIGUOUS_CONFLICT_NO_AUTOMATIC_SELECTION",
            query,
        )
        check(
            "Initial API remains admin-only",
            api["authorization"]["initial_permission"]
            == "AdminPermission.VIEW"
            and api["authorization"][
                "public_or_android_access"
            ] is False,
            api,
        )
        check(
            "Feature flag defaults off",
            enablement["feature_flag"]["default"]
            is False
            and enablement["feature_flag"]["fail_closed"]
            is True,
            enablement,
        )
        check(
            "Backfill requires separate authorization",
            data["backfill_contract"][
                "authorization_required"
            ] is True,
            data["backfill_contract"],
        )
        check(
            "Only migration proposal is ready",
            readiness[
                "ready_for_schema_migration_proposal"
            ] is True
            and readiness[
                "ready_for_geometry_backfill"
            ] is False
            and readiness[
                "ready_for_endpoint_implementation"
            ] is False
            and readiness[
                "ready_for_lookup_enablement"
            ] is False,
            readiness,
        )
        check(
            "All mutation guardrails remain closed",
            all(
                value is False
                for value in guardrails.values()
            ),
            guardrails,
        )

    print()
    print(
        "# NWDP RUNTIME LOOKUP PRODUCTION "
        "DESIGN REGRESSION PASSED"
    )


if __name__ == "__main__":
    main()
