#!/usr/bin/env python3
"""Regression for the read-only throughput V2 proposal generator."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from generate_boundary_validation_metadata_throughput_v2_proposal import (
    proposal_from_inventory,
)
from boundary_validation_metadata_throughput_v2_campaign import (
    initial_checkpoint,
    validate_proposal,
)


def geojson() -> str:
    return json.dumps({
        "type": "FeatureCollection",
        "features": [],
    })


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="throughput-v2-proposal-"
    ) as temporary:
        raw_dir = Path(temporary)
        (raw_dir / "small.geojson").write_text(
            geojson(),
            encoding="utf-8",
        )
        (raw_dir / "large.geojson").write_text(
            geojson(),
            encoding="utf-8",
        )

        counts = {
            "source_feature_rows": 100,
            "not_validated_rows": 60,
            "validated_rows": 40,
            "runtime_eligible_source_rows": 0,
            "active_candidate_rows": 0,
            "promoted_candidate_rows": 0,
            "runtime_set_rows": 1,
            "runtime_feature_rows": 10,
            "runtime_crosswalk_rows": 10,
        }
        inventory = [
            {
                "state_or_ut": "Large",
                "import_batch_id":
                    "large-batch",
                "not_validated_count": 50,
            },
            {
                "state_or_ut": "Small",
                "import_batch_id":
                    "small-batch",
                "not_validated_count": 10,
            },
        ]

        proposal = proposal_from_inventory(
            campaign_id="fixture-campaign",
            database_counts=counts,
            inventory=inventory,
            raw_dir=raw_dir,
        )

    validate_proposal(
        proposal,
        proposal["campaign_checksum"],
    )

    assert [
        state["state_slug"]
        for state in proposal["states"]
    ] == ["small", "large"]
    assert (
        proposal["limits"][
            "maximum_campaign_row_count"
        ]
        == 60
    )
    assert proposal["authorization"] == {
        "campaign_execution_authorized": False,
    }

    checkpoint = initial_checkpoint(
        proposal
    )
    assert checkpoint["status"] == "READY"
    assert checkpoint["transactions"] == []
    assert (
        checkpoint["completed_row_count"]
        == 0
    )

    mismatch_counts = dict(counts)
    mismatch_counts[
        "not_validated_rows"
    ] = 61

    with tempfile.TemporaryDirectory(
        prefix="throughput-v2-mismatch-"
    ) as mismatch_temporary:
        mismatch_raw_dir = Path(
            mismatch_temporary
        )
        (
            mismatch_raw_dir
            / "small.geojson"
        ).write_text(
            geojson(),
            encoding="utf-8",
        )
        (
            mismatch_raw_dir
            / "large.geojson"
        ).write_text(
            geojson(),
            encoding="utf-8",
        )

        try:
            proposal_from_inventory(
                campaign_id="mismatch",
                database_counts=mismatch_counts,
                inventory=inventory,
                raw_dir=mismatch_raw_dir,
            )
        except ValueError as exc:
            assert str(exc) == (
                "V2_NATIONAL_NOT_VALIDATED_COUNT_MISMATCH"
            )
        else:
            raise AssertionError(
                "National count mismatch was accepted"
            )

    print("PASS source files are checksum-pinned")
    print("PASS national database count is reconciled")
    print("PASS states are ordered smallest first")
    print("PASS proposal remains unauthorized")
    print("PASS initial checkpoint is empty")
    print(
        "# VALIDATION METADATA THROUGHPUT V2 "
        "PROPOSAL GENERATOR REGRESSION PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
