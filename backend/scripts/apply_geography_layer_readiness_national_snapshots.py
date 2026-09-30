#!/usr/bin/env python3
"""Apply a validated national district-readiness snapshot plan.

Default mode is dry-run. Apply requires:
- --apply
- --confirm APPLY_NATIONAL_DISTRICT_READINESS_SNAPSHOTS
- --expected-plan-id matching the reviewed plan

The command performs no readiness calculation, geometry operation, boundary
reconciliation, canonical geography change, or runtime activation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal


EXPECTED_DISTRICT_COUNT = 779
CONFIRMATION = "APPLY_NATIONAL_DISTRICT_READINESS_SNAPSHOTS"
PLAN_SCHEMA_VERSION = (
    "geography_layer_readiness_national_snapshot_plan.v1"
)
SNAPSHOT_SCHEMA_VERSION = "geography_layer_readiness_snapshot.v1"
DEFAULT_PLAN_DIR = (
    ROOT
    / "data/staged/core_stack/"
    "geography_readiness_snapshots"
)


def json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    raise TypeError(
        f"Object of type {type(value).__name__} "
        "is not JSON serializable"
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=json_default,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        type=Path,
        default=(
            DEFAULT_PLAN_DIR
            / "geography_layer_readiness_national_snapshot_plan.json"
        ),
    )
    parser.add_argument(
        "--rows",
        type=Path,
        default=(
            DEFAULT_PLAN_DIR
            / "geography_layer_readiness_national_snapshot_plan_rows.jsonl"
        ),
    )
    parser.add_argument("--expected-plan-id", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid JSONL at line {line_number}: {exc}"
                ) from exc
    return rows


def load_canonical_identities(db) -> dict[tuple[str, str], tuple[str, str]]:
    rows = db.execute(
        text(
            """
            select
              state.lgd_code::text as state_lgd_code,
              district.lgd_code::text as district_lgd_code,
              state.id::text as state_id,
              district.id::text as district_id
            from geography_states state
            join geography_districts district
              on district.state_id = state.id
             and district.is_active = true
            where state.is_active = true
            """
        )
    ).mappings()

    return {
        (
            str(row["state_lgd_code"]),
            str(row["district_lgd_code"]),
        ): (
            str(row["state_id"]),
            str(row["district_id"]),
        )
        for row in rows
    }


def load_active_snapshots(db) -> dict[tuple[str, str], dict[str, Any]]:
    rows = db.execute(
        text(
            """
            select
              id::text as snapshot_id,
              state_lgd_code,
              district_lgd_code,
              readiness_payload
            from geography_layer_readiness_snapshots
            where is_active = true
              and calculation_status = 'READY'
            """
        )
    ).mappings()

    return {
        (
            str(row["state_lgd_code"]),
            str(row["district_lgd_code"]),
        ): dict(row)
        for row in rows
    }


def protected_counts(db) -> dict[str, int]:
    tables = {
        "states": "geography_states",
        "districts": "geography_districts",
        "villages": "geography_villages",
        "climate_mappings":
            "geography_climate_region_mappings",
        "boundary_candidates":
            "geography_boundary_crosswalk_candidates",
        "project_overrides":
            "geography_core_layer_project_overrides",
    }
    return {
        label: int(
            db.execute(
                text(f"select count(*) from {table}")
            ).scalar_one()
        )
        for label, table in tables.items()
    }


def main() -> int:
    args = parse_args()

    if args.apply and (
        args.confirm != CONFIRMATION
        or not args.expected_plan_id
    ):
        print(json.dumps({
            "schema_version":
                "geography_layer_readiness_national_snapshot_apply.v1",
            "status": "APPLY_CONFIRMATION_AND_PLAN_ID_REQUIRED",
            "database_writes_attempted": False,
            "required_confirmation": CONFIRMATION,
        }, indent=2, sort_keys=True))
        return 1

    summary = load_json(args.summary)
    candidates = load_jsonl(args.rows)

    rows_file_sha256 = sha256_file(args.rows)
    identities = [
        (
            str(row.get("state_lgd_code")),
            str(row.get("district_lgd_code")),
        )
        for row in candidates
    ]
    duplicate_identity_count = (
        len(identities) - len(set(identities))
    )

    candidate_hashes_valid = all(
        row.get("planned_payload_sha256")
        == sha256_json(row.get("readiness_payload"))
        for row in candidates
    )
    candidate_plan_ids_exact = all(
        row.get("plan_id") == summary.get("plan_id")
        for row in candidates
    )
    candidate_schema_exact = all(
        row.get("snapshot_schema_version")
        == SNAPSHOT_SCHEMA_VERSION
        for row in candidates
    )
    candidate_scope_exact = all(
        len(row.get("readiness_payload", {}).get("rows", []))
        == 1
        and str(
            row["readiness_payload"]["rows"][0].get(
                "state_lgd_code"
            )
        )
        == str(row.get("state_lgd_code"))
        and str(
            row["readiness_payload"]["rows"][0].get(
                "district_lgd_code"
            )
        )
        == str(row.get("district_lgd_code"))
        for row in candidates
    )

    with SessionLocal() as db:
        canonical = load_canonical_identities(db)
        active_before = load_active_snapshots(db)
        protected_before = protected_counts(db)

        canonical_exact = (
            len(canonical) == EXPECTED_DISTRICT_COUNT
            and set(identities) == set(canonical)
            and all(
                canonical[identity]
                == (
                    str(row["state_id"]),
                    str(row["district_id"]),
                )
                for identity, row in zip(
                    identities,
                    candidates,
                )
            )
        )

        action_counts = dict(
            sorted(
                Counter(
                    row["plan_action"]
                    for row in candidates
                ).items()
            )
        )
        allowed_actions = {
            "INSERT_NEW_ACTIVE_SNAPSHOT",
            "RETAIN_IDENTICAL_ACTIVE_SNAPSHOT",
            "REPLACE_CHANGED_ACTIVE_SNAPSHOT",
        }
        actions_valid = all(
            row["plan_action"] in allowed_actions
            for row in candidates
        )

        existing_state_valid = True
        for row in candidates:
            key = (
                str(row["state_lgd_code"]),
                str(row["district_lgd_code"]),
            )
            existing = active_before.get(key)
            action = row["plan_action"]

            if action == "INSERT_NEW_ACTIVE_SNAPSHOT":
                existing_state_valid &= existing is None
            elif action == "RETAIN_IDENTICAL_ACTIVE_SNAPSHOT":
                existing_state_valid &= (
                    existing is not None
                    and sha256_json(
                        existing["readiness_payload"]
                    )
                    == row["planned_payload_sha256"]
                )
            elif action == "REPLACE_CHANGED_ACTIVE_SNAPSHOT":
                existing_state_valid &= (
                    existing is not None
                    and sha256_json(
                        existing["readiness_payload"]
                    )
                    == row["existing_payload_sha256"]
                )

        checks = {
            "plan_schema_exact": (
                summary.get("schema_version")
                == PLAN_SCHEMA_VERSION
            ),
            "plan_status_exact": (
                summary.get("status")
                == "NATIONAL_DISTRICT_SNAPSHOT_PLAN_READY_NOT_AUTHORIZED"
            ),
            "plan_healthy": summary.get("healthy") is True,
            "plan_checks_all_true": all(
                summary.get("checks", {}).values()
            ),
            "summary_candidate_count_exact": (
                summary.get("candidate_count")
                == EXPECTED_DISTRICT_COUNT
            ),
            "candidate_count_exact": (
                len(candidates) == EXPECTED_DISTRICT_COUNT
            ),
            "rows_sha256_pinned": (
                rows_file_sha256
                == summary.get("rows_sha256")
            ),
            "candidate_plan_ids_exact":
                candidate_plan_ids_exact,
            "candidate_schema_exact":
                candidate_schema_exact,
            "candidate_payload_hashes_valid":
                candidate_hashes_valid,
            "candidate_scope_exact":
                candidate_scope_exact,
            "identity_unique":
                duplicate_identity_count == 0,
            "canonical_partition_exact":
                canonical_exact,
            "actions_valid": actions_valid,
            "existing_snapshot_state_matches_plan":
                existing_state_valid,
            "expected_plan_id_exact": (
                True
                if not args.apply
                else args.expected_plan_id
                == summary.get("plan_id")
            ),
            "no_readiness_computation": True,
            "no_geometry_computation": True,
            "runtime_activation_unchanged": True,
            "android_behavior_unchanged": True,
        }

        validation_healthy = all(checks.values())
        database_writes_attempted = False
        inserted = 0
        replaced = 0
        retained = 0
        apply_run_id = None

        if args.apply:
            if not validation_healthy:
                raise RuntimeError(
                    "Refusing national snapshot apply because "
                    "validation failed"
                )

            database_writes_attempted = True
            apply_run_id = (
                "national-snapshot-apply-"
                + datetime.now(timezone.utc).strftime(
                    "%Y%m%dT%H%M%SZ"
                )
                + "-"
                + uuid.uuid4().hex[:8]
            )
            computed_at = datetime.now(timezone.utc)

            for row in candidates:
                action = row["plan_action"]
                key_params = {
                    "state_id": row["state_id"],
                    "district_id": row["district_id"],
                }

                if action == "RETAIN_IDENTICAL_ACTIVE_SNAPSHOT":
                    retained += 1
                    continue

                if action == "REPLACE_CHANGED_ACTIVE_SNAPSHOT":
                    db.execute(
                        text(
                            """
                            update geography_layer_readiness_snapshots
                            set is_active = false,
                                updated_at = now()
                            where state_id = cast(:state_id as uuid)
                              and district_id = cast(:district_id as uuid)
                              and is_active = true
                            """
                        ),
                        key_params,
                    )
                    replaced += 1
                else:
                    inserted += 1

                evidence = {
                    **row["evidence_metadata"],
                    "apply_run_id": apply_run_id,
                    "reviewed_plan_id": summary["plan_id"],
                    "reviewed_rows_sha256":
                        summary["rows_sha256"],
                    "bulk_apply_transactional": True,
                }

                db.execute(
                    text(
                        """
                        insert into geography_layer_readiness_snapshots (
                          id,
                          state_id,
                          district_id,
                          state_lgd_code,
                          district_lgd_code,
                          state_or_ut,
                          district,
                          snapshot_schema_version,
                          calculation_status,
                          readiness_payload,
                          source_versions,
                          evidence_metadata,
                          computed_at,
                          refresh_run_id,
                          failure_reason,
                          created_at,
                          updated_at,
                          version,
                          is_active
                        ) values (
                          cast(:id as uuid),
                          cast(:state_id as uuid),
                          cast(:district_id as uuid),
                          :state_lgd_code,
                          :district_lgd_code,
                          :state_or_ut,
                          :district,
                          :snapshot_schema_version,
                          'READY',
                          cast(:readiness_payload as jsonb),
                          cast(:source_versions as jsonb),
                          cast(:evidence_metadata as jsonb),
                          :computed_at,
                          :refresh_run_id,
                          null,
                          now(),
                          now(),
                          'v1.0',
                          true
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "state_id": row["state_id"],
                        "district_id": row["district_id"],
                        "state_lgd_code":
                            row["state_lgd_code"],
                        "district_lgd_code":
                            row["district_lgd_code"],
                        "state_or_ut": row["state_or_ut"],
                        "district": row["district"],
                        "snapshot_schema_version":
                            SNAPSHOT_SCHEMA_VERSION,
                        "readiness_payload":
                            canonical_json(
                                row["readiness_payload"]
                            ),
                        "source_versions":
                            canonical_json(
                                row["source_versions"]
                            ),
                        "evidence_metadata":
                            canonical_json(evidence),
                        "computed_at": computed_at,
                        "refresh_run_id": apply_run_id,
                    },
                )

            active_after_count = int(
                db.execute(
                    text(
                        """
                        select count(*)
                        from geography_layer_readiness_snapshots
                        where is_active = true
                          and calculation_status = 'READY'
                        """
                    )
                ).scalar_one()
            )
            active_identity_count = int(
                db.execute(
                    text(
                        """
                        select count(distinct (
                          state_lgd_code,
                          district_lgd_code
                        ))
                        from geography_layer_readiness_snapshots
                        where is_active = true
                          and calculation_status = 'READY'
                        """
                    )
                ).scalar_one()
            )

            if (
                active_after_count != EXPECTED_DISTRICT_COUNT
                or active_identity_count
                    != EXPECTED_DISTRICT_COUNT
            ):
                db.rollback()
                raise RuntimeError(
                    "National snapshot apply failed active "
                    "coverage verification"
                )

            protected_after = protected_counts(db)
            if protected_after != protected_before:
                db.rollback()
                raise RuntimeError(
                    "Protected domain counts changed during apply"
                )

            db.commit()
            status = "NATIONAL_DISTRICT_SNAPSHOTS_APPLIED"
        else:
            inserted = action_counts.get(
                "INSERT_NEW_ACTIVE_SNAPSHOT",
                0,
            )
            replaced = action_counts.get(
                "REPLACE_CHANGED_ACTIVE_SNAPSHOT",
                0,
            )
            retained = action_counts.get(
                "RETAIN_IDENTICAL_ACTIVE_SNAPSHOT",
                0,
            )
            active_after_count = len(active_before)
            active_identity_count = len(active_before)
            protected_after = protected_counts(db)
            status = (
                "NATIONAL_DISTRICT_SNAPSHOT_APPLY_READY"
                if validation_healthy
                else "NATIONAL_DISTRICT_SNAPSHOT_PLAN_INVALID"
            )

        checks["protected_counts_unchanged"] = (
            protected_before == protected_after
        )
        checks["dry_run_made_no_writes"] = (
            database_writes_attempted
            if args.apply
            else not database_writes_attempted
        )

        healthy = validation_healthy and all(checks.values())

        result = {
            "schema_version":
                "geography_layer_readiness_national_snapshot_apply.v1",
            "status": status if healthy else "APPLY_INVALID",
            "healthy": healthy,
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "database_writes_attempted":
                database_writes_attempted,
            "plan_id": summary.get("plan_id"),
            "rows_sha256": rows_file_sha256,
            "candidate_count": len(candidates),
            "counts_by_plan_action": action_counts,
            "would_or_did_insert": inserted,
            "would_or_did_replace": replaced,
            "retained_identical": retained,
            "active_snapshot_count_before":
                len(active_before),
            "active_snapshot_count_after":
                active_after_count,
            "active_identity_count_after":
                active_identity_count,
            "apply_run_id": apply_run_id,
            "duplicate_identity_count":
                duplicate_identity_count,
            "protected_counts_before": protected_before,
            "protected_counts_after": protected_after,
            "checks": checks,
            "policy": {
                "offline_plan_required": True,
                "single_transaction_required": True,
                "historical_snapshots_preserved": True,
                "readiness_recomputation_authorized": False,
                "geometry_computation_authorized": False,
                "canonical_geography_changes_authorized": False,
                "global_mapping_changes_authorized": False,
                "project_override_changes_authorized": False,
                "runtime_activation_authorized": False,
                "android_behavior_change_authorized": False,
            },
        }

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
