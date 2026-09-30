#!/usr/bin/env python3
"""Static safety contract for the J&K rollback-only rehearsal."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT / "backend/scripts/"
    "rehearse_nwdp_post_lgd_jammu_kashmir_activation.py"
)


def main():
    source = SCRIPT.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        ("EXPECTED_ROWS = 821", "Exact canary count is pinned"),
        ("PLAN_CHECKSUM", "Reviewed plan checksum is pinned"),
        ("ROWS_SHA256", "Reviewed rows hash is pinned"),
        ("pg_advisory_xact_lock", "Advisory lock is required"),
        ("set local lock_timeout", "Lock timeout is bounded"),
        ("set local statement_timeout", "Statement timeout is bounded"),
        ("TEMPORARY_ACTIVE = 450_720", "Temporary total is pinned"),
        ("transaction.rollback()", "Rollback is explicit"),
        ("database_snapshot_restored", "Database restoration is checked"),
        ("cohort_restored_inactive", "Cohort restoration is checked"),
        ('"commit_mode_available": False', "Commit mode is absent"),
        ('"activation_authorized": False', "Activation is unauthorized"),
        ('"lookup_exposure_authorized": False', "Lookup is unchanged"),
        ('"project_changes_authorized": False', "Projects are unchanged"),
        ('"android_changes_authorized": False', "Android is unchanged"),
    ]

    for needle, label in checks:
        if needle not in normalized:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    prohibited = [
        ".commit(",
        "insert into",
        "delete from",
        "alter table",
        "drop table",
    ]
    present = [
        item for item in prohibited
        if item in normalized.lower()
    ]
    if present:
        raise AssertionError(
            f"Rehearsal contains prohibited operations: {present}"
        )

    print("PASS Rehearsal has no commit-capable path")
    print(
        "NWDP POST-LGD JAMMU & KASHMIR "
        "ROLLBACK REHEARSAL STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
