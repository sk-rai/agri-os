#!/usr/bin/env python3
"""Build authorization and initial checkpoint for post-LGD staging.

This script records the user's bounded inactive-only authorization. It does
not write to PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lgd_priority_state_common import (
    DEFAULT_OUTPUT_DIR,
    atomic_write_json,
    canonical_checksum,
    sha256_file,
)

SCHEMA_VERSION = (
    "nwdp_post_lgd_staging_authorization.v1"
)
CHECKPOINT_SCHEMA_VERSION = (
    "nwdp_post_lgd_staging_checkpoint.v1"
)

DEFAULT_MANIFEST = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_staging_manifest.json"
)
DEFAULT_PROPOSAL = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_staging_proposal.json"
)
DEFAULT_AUTHORIZATION = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_staging_authorization.json"
)
DEFAULT_CHECKPOINT = (
    DEFAULT_OUTPUT_DIR
    / "nwdp_post_lgd_staging_checkpoint.json"
)

MANIFEST_CHECKSUM = (
    "72663edc2b5e27273d7d8516c40842f9"
    "7358842d4cde2a1a215353b3b281e16a"
)
MANIFEST_FILE_SHA256 = (
    "ce78c6ad48541069d3c949a1e8ae78cd"
    "4eb1af856014b361cfa1db7348191a76"
)
PROPOSAL_CHECKSUM = (
    "80bbbe640c7675d9d9882c3489e53cc4"
    "81159eee222341e03d24a3121d7d0cae"
)
PROPOSAL_FILE_SHA256 = (
    "1ebe99f17e952985c2db40991666bc1ba"
    "bbc1e17f2679ba8174126c75335f0f5"
)
ORDERED_ROW_MANIFEST_SHA256 = (
    "32bef4c7f99af2792410a2505d70d56f"
    "7fe42d126388de37e9ed376e8043a139"
)

EXPECTED_ROWS = 17_498
EXPECTED_STATES = 8
RUNTIME_SET_ID = (
    "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
)

PERMISSIONS = {
    "bounded_review_metadata_write_allowed": True,
    "bounded_runtime_eligibility_write_allowed": True,
    "inactive_runtime_feature_write_allowed": True,
    "inactive_runtime_crosswalk_write_allowed": True,
    "inactive_promotion_event_write_allowed": True,
    "native_geometry_write_allowed": True,
    "checkpoint_write_allowed": True,

    "runtime_activation_change_allowed": False,
    "lookup_scope_change_allowed": False,
    "candidate_activation_allowed": False,
    "candidate_identity_change_allowed": False,
    "candidate_promotion_allowed": False,
    "canonical_geography_write_allowed": False,
    "canonical_reparenting_allowed": False,
    "project_match_write_allowed": False,
    "source_file_write_allowed": False,
    "source_geometry_write_allowed": False,
    "android_behavior_change_allowed": False,
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def validate_inputs(
    manifest_path: Path,
    proposal_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if sha256_file(manifest_path) != MANIFEST_FILE_SHA256:
        raise ValueError("MANIFEST_FILE_PIN_MISMATCH")
    if sha256_file(proposal_path) != PROPOSAL_FILE_SHA256:
        raise ValueError("PROPOSAL_FILE_PIN_MISMATCH")

    manifest = load_json(manifest_path)
    proposal = load_json(proposal_path)

    checks = {
        "manifest_healthy":
            manifest.get("healthy") is True,
        "manifest_not_authorized":
            manifest.get("authorized") is False,
        "manifest_no_writes":
            manifest.get(
                "database_writes_attempted"
            ) is False,
        "manifest_status":
            manifest.get("status")
            == "MANIFESTED_NOT_AUTHORIZED",
        "manifest_checksum":
            manifest.get("manifest_checksum")
            == MANIFEST_CHECKSUM,
        "manifest_rows":
            manifest.get("row_count")
            == EXPECTED_ROWS,
        "manifest_states":
            manifest.get("state_count")
            == EXPECTED_STATES,
        "manifest_ordered_rows":
            manifest.get(
                "ordered_national_row_manifest_sha256"
            ) == ORDERED_ROW_MANIFEST_SHA256,

        "proposal_healthy":
            proposal.get("healthy") is True,
        "proposal_not_authorized":
            proposal.get("authorized") is False,
        "proposal_no_writes":
            proposal.get(
                "database_writes_attempted"
            ) is False,
        "proposal_status":
            proposal.get("status")
            == "PROPOSED_NOT_AUTHORIZED",
        "proposal_checksum":
            proposal.get("proposal_checksum")
            == PROPOSAL_CHECKSUM,
        "proposal_manifest":
            proposal.get("manifest_checksum")
            == MANIFEST_CHECKSUM,
        "proposal_rows":
            proposal.get("row_count")
            == EXPECTED_ROWS,
        "proposal_states":
            proposal.get("state_count")
            == EXPECTED_STATES,
        "proposal_permissions_all_false":
            all(
                value is False
                for value in proposal.get(
                    "permissions",
                    {},
                ).values()
            ),
    }

    failed = sorted(
        key
        for key, value in checks.items()
        if not value
    )
    if failed:
        raise ValueError(
            "AUTHORIZATION_INPUT_VALIDATION_FAILED:"
            + ",".join(failed)
        )

    return manifest, proposal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument(
        "--proposal",
        type=Path,
        default=DEFAULT_PROPOSAL,
    )
    parser.add_argument(
        "--authorization-output",
        type=Path,
        default=DEFAULT_AUTHORIZATION,
    )
    parser.add_argument(
        "--checkpoint-output",
        type=Path,
        default=DEFAULT_CHECKPOINT,
    )
    args = parser.parse_args()

    try:
        manifest, proposal = validate_inputs(
            args.manifest,
            args.proposal,
        )

        authorization = {
            "schema_version": SCHEMA_VERSION,
            "status": "AUTHORIZED",
            "authorized": True,
            "database_writes_attempted": False,
            "scope": (
                "EXACT_CHECKSUM_PINNED_INACTIVE_"
                "NWDP_RUNTIME_STAGING_ONLY"
            ),
            "proposal_checksum":
                PROPOSAL_CHECKSUM,
            "proposal_file_sha256":
                PROPOSAL_FILE_SHA256,
            "manifest_checksum":
                MANIFEST_CHECKSUM,
            "manifest_file_sha256":
                MANIFEST_FILE_SHA256,
            "ordered_national_row_manifest_sha256":
                ORDERED_ROW_MANIFEST_SHA256,
            "runtime_set_id": RUNTIME_SET_ID,
            "authorized_row_count":
                EXPECTED_ROWS,
            "authorized_state_count":
                EXPECTED_STATES,
            "permissions": PERMISSIONS,
            "excluded": proposal["excluded"],
            "authorization_statement": (
                "Authorized inactive-only staging of "
                "exactly 17,498 checksum-pinned rows. "
                "Activation, lookup exposure, candidate "
                "activation or promotion, canonical "
                "geography changes or reparenting, "
                "project matching, source writes, and "
                "Android changes remain prohibited."
            ),
        }
        authorization["authorization_checksum"] = (
            canonical_checksum(authorization)
        )
        atomic_write_json(
            args.authorization_output,
            authorization,
        )

        states = []
        for state in manifest["states"]:
            states.append({
                "sequence": state["sequence"],
                "state": state["state"],
                "state_lgd_code":
                    state["state_lgd_code"],
                "import_batch_id":
                    state["import_batch_id"],
                "source_file":
                    state["source_file"],
                "source_file_sha256":
                    state["source_file_sha256"],
                "expected_row_count":
                    state["row_count"],
                "ordered_row_manifest_sha256":
                    state[
                        "ordered_row_manifest_sha256"
                    ],
                "status": "READY",
                "completed_row_count": 0,
                "remaining_row_count":
                    state["row_count"],
                "last_source_feature_index": -1,
                "transaction_ids": [],
            })

        checkpoint = {
            "schema_version":
                CHECKPOINT_SCHEMA_VERSION,
            "status": "READY",
            "authorized": True,
            "database_writes_attempted": False,
            "database_writes_committed": False,
            "execution_started": False,
            "execution_completed": False,
            "resume_required": False,
            "single_writer": True,
            "writer_count": 1,
            "active_state": None,
            "active_transaction": None,
            "runtime_set_id": RUNTIME_SET_ID,
            "proposal_checksum":
                PROPOSAL_CHECKSUM,
            "manifest_checksum":
                MANIFEST_CHECKSUM,
            "authorization_checksum":
                authorization[
                    "authorization_checksum"
                ],
            "ordered_national_row_manifest_sha256":
                ORDERED_ROW_MANIFEST_SHA256,
            "authorized_row_count":
                EXPECTED_ROWS,
            "authorized_state_count":
                EXPECTED_STATES,
            "completed_row_count": 0,
            "remaining_row_count":
                EXPECTED_ROWS,
            "completed_state_count": 0,
            "transaction_count": 0,
            "states": states,
        }
        checkpoint["checkpoint_checksum"] = (
            canonical_checksum(checkpoint)
        )
        atomic_write_json(
            args.checkpoint_output,
            checkpoint,
        )

        checks = {
            "authorization_status":
                authorization["status"]
                == "AUTHORIZED",
            "authorization_exact_rows":
                authorization[
                    "authorized_row_count"
                ] == EXPECTED_ROWS,
            "authorization_exact_states":
                authorization[
                    "authorized_state_count"
                ] == EXPECTED_STATES,
            "required_permissions_true":
                all(
                    authorization["permissions"][key]
                    is True
                    for key in (
                        "bounded_review_metadata_write_allowed",
                        "bounded_runtime_eligibility_write_allowed",
                        "inactive_runtime_feature_write_allowed",
                        "inactive_runtime_crosswalk_write_allowed",
                        "inactive_promotion_event_write_allowed",
                        "native_geometry_write_allowed",
                        "checkpoint_write_allowed",
                    )
                ),
            "prohibited_permissions_false":
                all(
                    authorization["permissions"][key]
                    is False
                    for key in (
                        "runtime_activation_change_allowed",
                        "lookup_scope_change_allowed",
                        "candidate_activation_allowed",
                        "candidate_identity_change_allowed",
                        "candidate_promotion_allowed",
                        "canonical_geography_write_allowed",
                        "canonical_reparenting_allowed",
                        "project_match_write_allowed",
                        "source_file_write_allowed",
                        "source_geometry_write_allowed",
                        "android_behavior_change_allowed",
                    )
                ),
            "checkpoint_ready":
                checkpoint["status"] == "READY",
            "checkpoint_not_started":
                checkpoint["execution_started"]
                is False,
            "checkpoint_no_active_state":
                checkpoint["active_state"] is None,
            "checkpoint_no_active_transaction":
                checkpoint[
                    "active_transaction"
                ] is None,
            "checkpoint_rows":
                sum(
                    state["expected_row_count"]
                    for state in states
                ) == EXPECTED_ROWS,
            "checkpoint_states":
                len(states) == EXPECTED_STATES,
            "no_database_writes": True,
        }

        print(json.dumps({
            "healthy": all(checks.values()),
            "checks": checks,
            "authorized": True,
            "database_writes_attempted": False,
            "authorization_checksum":
                authorization[
                    "authorization_checksum"
                ],
            "authorization_file_sha256":
                sha256_file(
                    args.authorization_output
                ),
            "checkpoint_checksum":
                checkpoint["checkpoint_checksum"],
            "checkpoint_file_sha256":
                sha256_file(
                    args.checkpoint_output
                ),
            "row_count": EXPECTED_ROWS,
            "state_count": EXPECTED_STATES,
        }, indent=2, sort_keys=True))

        return 0 if all(checks.values()) else 1

    except Exception as exc:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "healthy": False,
            "fail_closed": True,
            "authorized": False,
            "database_writes_attempted": False,
            "error": f"{type(exc).__name__}:{exc}",
        }, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
