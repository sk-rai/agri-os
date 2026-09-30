#!/usr/bin/env python3
"""Static safety contract for post-LGD runtime activation wrapper."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "run_nwdp_post_lgd_runtime_activation.py"
)


def main():
    source = SCRIPT.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        (
            "run_national_direct_village_runtime_activation",
            "Existing national activation engine is reused",
        ),
        (
            "engine.activate_state",
            "Existing state activation function is reused",
        ),
        (
            "engine.deactivate_state",
            "Existing state rollback function is reused",
        ),
        (
            "EXPECTED_ROWS = 17_498",
            "Exact cohort count is pinned",
        ),
        (
            "BASELINE = 449_899",
            "Active baseline is pinned",
        ),
        (
            "FINAL_TOTAL = 467_397",
            "Expected final total is pinned",
        ),
        (
            "SOURCE_ARTIFACTS",
            "Source artifacts are pinned",
        ),
        (
            "validate_source_artifacts",
            "Source artifact hashes are validated",
        ),
        (
            "ce78c6ad48541069d3c949a1e8ae78cd",
            "Staging manifest hash is pinned",
        ),
        (
            "1ebe99f17e952985c2db40991666bc1ba",
            "Staging proposal hash is pinned",
        ),
        (
            "dd9b985c1181a6bfb2fb734b307f5f01",
            "Completed staging checkpoint hash is pinned",
        ),
        (
            "b786c1b6f8192d52560a2caca9f50445",
            "Staging authorization hash is pinned",
        ),
        (
            "APPLY_POST_LGD_RUNTIME_ACTIVATION",
            "Apply confirmation is explicit",
        ),
        (
            "ROLLBACK_POST_LGD_RUNTIME_ACTIVATION",
            "Rollback confirmation is explicit",
        ),
        (
            "pg_advisory_xact_lock",
            "Advisory locking is required",
        ),
        (
            "set local lock_timeout",
            "Lock timeout is bounded",
        ),
        (
            "set local statement_timeout",
            "Statement timeout is bounded",
        ),
        (
            "checkpoint_checksum",
            "Checkpoint is checksummed",
        ),
        (
            "load_resume_checkpoint",
            "Resume checkpoint is validated",
        ),
        (
            "RESUME_CHECKPOINT_INVALID",
            "Invalid resume fails closed",
        ),
        (
            "IN_PROGRESS_CHECKPOINT_REQUIRES_RESUME",
            "Incomplete work requires resume",
        ),
        (
            "validate_execution_start",
            "Checkpoint is bound to database state",
        ),
        (
            "EXECUTION_START_STATE_INVALID",
            "Database disagreement fails closed",
        ),
        (
            "candidate_state_unchanged",
            "Candidate state is protected",
        ),
        (
            "project_matches_unchanged",
            "Project state is protected",
        ),
        (
            '"lookup_exposure_changed": False',
            "Lookup exposure remains unchanged",
        ),
        (
            '"canonical_changes": False',
            "Canonical geography remains unchanged",
        ),
        (
            '"android_changes": False',
            "Android behavior remains unchanged",
        ),
        (
            "transaction.rollback()",
            "Rollback rehearsal is explicit",
        ),
        (
            "transaction.commit()",
            "State-scoped commit is explicit",
        ),
    ]

    for needle, label in checks:
        if needle not in normalized:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    if len(source.split("expected_row_count")) < 9:
        raise AssertionError(
            "Eight state partitions are not explicit"
        )
    print("PASS Eight state partitions are explicit")

    credential_markers = [
        "postgresql://",
        "postgresql+psycopg2://",
        "password=",
        "agri_os_dev",
    ]
    present = [
        marker
        for marker in credential_markers
        if marker in source.lower()
    ]
    if present:
        raise AssertionError(
            f"Embedded credential material found: {present}"
        )
    print("PASS No credential material is embedded")

    print(
        "NWDP POST-LGD RUNTIME ACTIVATION "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
