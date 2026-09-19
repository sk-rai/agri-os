#!/usr/bin/env python3
"""Generate a read-only throughput V2 campaign proposal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from boundary_validation_metadata_throughput_v2_campaign import (  # noqa: E402
    build_proposal,
    initial_checkpoint,
    validate_proposal,
)
from plan_boundary_geometry_validation_metadata_national_rollout import (  # noqa: E402
    DEFAULT_RAW_DIR,
    database_inventory,
    slugify,
)
from report_boundary_geometry_validation_repair_dry_run import (  # noqa: E402
    sha256_file,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--campaign-id",
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
    )
    return parser.parse_args()


def atomic_write_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary = path.with_suffix(
        path.suffix + ".writing"
    )
    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def proposal_from_inventory(
    *,
    campaign_id: str,
    database_counts: dict[str, int],
    inventory: list[dict[str, Any]],
    raw_dir: Path,
) -> dict[str, Any]:
    states: list[dict[str, Any]] = []

    for item in inventory:
        slug = slugify(
            str(item["state_or_ut"])
        )
        source_path = raw_dir / f"{slug}.geojson"

        if not source_path.is_file():
            raise ValueError(
                f"V2_SOURCE_FILE_NOT_FOUND:{slug}"
            )

        states.append({
            "state_slug": slug,
            "state_or_ut":
                item["state_or_ut"],
            "import_batch_id":
                item["import_batch_id"],
            "source_sha256":
                sha256_file(source_path),
            "not_validated_count":
                int(
                    item.get(
                        "not_validated_count"
                    ) or 0
                ),
        })

    proposal = build_proposal(
        campaign_id=campaign_id,
        start_database_counts=database_counts,
        states=states,
    )

    expected_rows = int(
        database_counts.get(
            "not_validated_rows"
        ) or 0
    )
    proposed_rows = int(
        proposal["limits"][
            "maximum_campaign_row_count"
        ]
    )

    if proposed_rows != expected_rows:
        raise ValueError(
            "V2_NATIONAL_NOT_VALIDATED_COUNT_MISMATCH"
        )

    validate_proposal(
        proposal,
        proposal["campaign_checksum"],
    )
    return proposal


def main() -> int:
    args = arguments()

    proposal_path = (
        args.output_dir
        / (
            "boundary_validation_metadata_"
            "throughput_v2_campaign_proposal.json"
        )
    )
    checkpoint_path = (
        args.output_dir
        / (
            "boundary_validation_metadata_"
            "throughput_v2_campaign_checkpoint.json"
        )
    )

    if (
        proposal_path.exists()
        or checkpoint_path.exists()
    ):
        raise SystemExit(
            "V2_CAMPAIGN_ARTIFACT_ALREADY_EXISTS"
        )

    inventory, counts = database_inventory()

    proposal = proposal_from_inventory(
        campaign_id=args.campaign_id,
        database_counts=counts,
        inventory=inventory,
        raw_dir=args.raw_dir,
    )
    checkpoint = initial_checkpoint(
        proposal
    )

    atomic_write_json(
        proposal_path,
        proposal,
    )
    atomic_write_json(
        checkpoint_path,
        checkpoint,
    )

    print(json.dumps({
        "healthy": True,
        "status":
            "PROPOSED_NOT_AUTHORIZED",
        "execution_started": False,
        "database_writes_attempted": False,
        "campaign_id":
            proposal["campaign_id"],
        "campaign_checksum":
            proposal["campaign_checksum"],
        "state_count":
            len(proposal["states"]),
        "maximum_campaign_row_count":
            proposal["limits"][
                "maximum_campaign_row_count"
            ],
        "default_rows_per_state_transaction":
            proposal["limits"][
                "default_rows_per_state_transaction"
            ],
        "maximum_rows_per_state_transaction":
            proposal["limits"][
                "maximum_rows_per_state_transaction"
            ],
        "writer_count":
            proposal["limits"][
                "default_writer_count"
            ],
        "first_state":
            proposal["states"][0][
                "state_slug"
            ],
        "last_state":
            proposal["states"][-1][
                "state_slug"
            ],
        "proposal_json":
            str(proposal_path),
        "checkpoint_json":
            str(checkpoint_path),
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
