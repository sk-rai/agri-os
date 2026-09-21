#!/usr/bin/env python3
"""Regression for native runtime geometry backfill proposal."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venv/bin/python"
ASSESS = (
    ROOT
    / "backend/scripts/"
    / "assess_nwdp_runtime_geometry_reuse.py"
)
GENERATOR = (
    ROOT
    / "backend/scripts/"
    / "generate_nwdp_runtime_geometry_backfill_proposal.py"
)
RAW = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/"
    / "20260824T110250Z/karnataka.geojson"
)


def check(label: str, condition: bool, payload=None) -> None:
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
        prefix="runtime-geometry-backfill-proposal-",
    ) as directory:
        base = Path(directory)
        fixture = base / "fixture.geojson"
        assessment = base / "assessment.json"
        proposal_a = base / "proposal-a.json"
        proposal_b = base / "proposal-b.json"

        environment = dict(os.environ)
        environment.update({
            "PYTHONPATH": str(ROOT / "backend"),
            "RAW": str(RAW),
            "OUT_JSON": str(assessment),
            "EXTRACTED": str(fixture),
        })

        assessment_proc = subprocess.run(
            [str(PYTHON), str(ASSESS)],
            cwd=str(ROOT),
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        check(
            "Pinned fixture generation succeeds",
            assessment_proc.returncode == 0,
            assessment_proc.stdout,
        )

        checksums = []
        proposals = []

        for output in (proposal_a, proposal_b):
            proc = subprocess.run(
                [
                    str(PYTHON),
                    str(GENERATOR),
                    "--fixture",
                    str(fixture),
                    "--output",
                    str(output),
                ],
                cwd=str(ROOT),
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            check(
                "Proposal generation succeeds",
                proc.returncode == 0,
                proc.stdout,
            )
            proposal = json.loads(
                output.read_text(encoding="utf-8")
            )
            proposals.append(proposal)
            checksums.append(
                proposal["proposal_checksum"]
            )

        proposal = proposals[0]
        rows = proposal["rows"]
        policy = proposal["execution_policy"]
        guardrails = proposal["guardrails"]

        check(
            "Proposal is deterministic",
            checksums[0] == checksums[1],
            checksums,
        )
        check(
            "Proposal remains unauthorized",
            proposal["status"]
            == "PROPOSED_NOT_AUTHORIZED",
            proposal,
        )
        check(
            "Exactly ten rows are proposed",
            proposal["row_count"] == 10
            and len(rows) == 10,
            proposal,
        )
        check(
            "Every identity check passes",
            all(
                all(
                    row["identity_checks"].values()
                )
                for row in rows
            ),
            rows,
        )
        check(
            "Every native geometry starts null",
            all(
                row["native_geometry_before"]
                is None
                for row in rows
            )
            and proposal["database_counts"][
                "populated_native_geometry_rows"
            ] == 0,
            proposal,
        )
        check(
            "Every geometry targets WGS84",
            all(
                row["planned_srid"] == 4326
                and row["planned_geometry_type"]
                in {"Polygon", "MultiPolygon"}
                for row in rows
            ),
            rows,
        )
        check(
            "Row identities and checksums are unique",
            len({
                row["runtime_feature_id"]
                for row in rows
            }) == 10
            and len({
                row["row_checksum"]
                for row in rows
            }) == 10,
            rows,
        )
        check(
            "Only native geometry write is authorized by design",
            policy["target_column"]
            == "geometry_wgs84_geom"
            and policy[
                "lookup_enablement_allowed"
            ] is False
            and policy[
                "runtime_activation_change_allowed"
            ] is False,
            policy,
        )
        check(
            "All proposal guardrails remain closed",
            all(
                value is False
                for value in guardrails.values()
            ),
            guardrails,
        )
        check(
            "Exact authorization is required",
            proposal["required_confirmation"].startswith(
                "Authorize native runtime geometry backfill "
                + proposal["proposal_checksum"]
            )
            and proposal["readiness"][
                "ready_for_backfill_execution"
            ] is False,
            proposal["readiness"],
        )

    print()
    print(
        "# NWDP RUNTIME GEOMETRY BACKFILL "
        "PROPOSAL REGRESSION PASSED"
    )


if __name__ == "__main__":
    main()
