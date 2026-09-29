#!/usr/bin/env python3
"""Build one precomputed district geography-layer readiness snapshot.

Default mode is dry-run. The expensive readiness calculation is intentionally
confined to this offline command and must never run in the interactive snapshot
read path.

Apply requires both --apply and:
--confirm REFRESH_DISTRICT_READINESS_SNAPSHOT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal
from app.modules.master_data.api.geography import (
    _build_geography_layer_readiness_matrix,
)


CONFIRMATION = "REFRESH_DISTRICT_READINESS_SNAPSHOT"
SNAPSHOT_SCHEMA_VERSION = "geography_layer_readiness_snapshot.v1"
READINESS_SCHEMA_VERSION = "geography_layer_readiness_matrix.v1"
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
SOURCE_VERSION = "20260824T110250Z"


def json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (Decimal, uuid.UUID)):
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--district", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist and activate the computed snapshot.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Required with --apply: {CONFIRMATION}",
    )
    return parser.parse_args()


def resolve_scope(db, state_name: str, district_name: str) -> dict:
    row = db.execute(
        text(
            """
            select
              s.id::text as state_id,
              d.id::text as district_id,
              s.lgd_code::text as state_lgd_code,
              d.lgd_code::text as district_lgd_code,
              s.canonical_name as state_or_ut,
              d.canonical_name as district
            from geography_states s
            join geography_districts d
              on d.state_id = s.id
             and d.is_active = true
            where s.is_active = true
              and lower(trim(s.canonical_name))
                    = lower(trim(:state_name))
              and lower(trim(d.canonical_name))
                    = lower(trim(:district_name))
            """
        ),
        {
            "state_name": state_name,
            "district_name": district_name,
        },
    ).mappings().all()

    if len(row) != 1:
        raise RuntimeError(
            "Expected exactly one canonical state/district scope, "
            f"found {len(row)}"
        )
    return dict(row[0])


def protected_counts(db) -> dict[str, int]:
    return {
        "states": int(
            db.execute(
                text("select count(*) from geography_states")
            ).scalar_one()
        ),
        "districts": int(
            db.execute(
                text("select count(*) from geography_districts")
            ).scalar_one()
        ),
        "villages": int(
            db.execute(
                text("select count(*) from geography_villages")
            ).scalar_one()
        ),
        "climate_mappings": int(
            db.execute(
                text(
                    "select count(*) "
                    "from geography_climate_region_mappings"
                )
            ).scalar_one()
        ),
        "boundary_candidates": int(
            db.execute(
                text(
                    "select count(*) "
                    "from geography_boundary_crosswalk_candidates"
                )
            ).scalar_one()
        ),
        "project_overrides": int(
            db.execute(
                text(
                    "select count(*) "
                    "from geography_core_layer_project_overrides"
                )
            ).scalar_one()
        ),
    }


def active_snapshot_count(db, scope: dict) -> int:
    return int(
        db.execute(
            text(
                """
                select count(*)
                from geography_layer_readiness_snapshots
                where state_id = cast(:state_id as uuid)
                  and district_id = cast(:district_id as uuid)
                  and is_active = true
                """
            ),
            scope,
        ).scalar_one()
    )


def main() -> int:
    args = parse_args()

    if args.apply and args.confirm != CONFIRMATION:
        print(
            json.dumps(
                {
                    "schema_version": SNAPSHOT_SCHEMA_VERSION,
                    "status": "APPLY_CONFIRMATION_REQUIRED",
                    "database_writes_attempted": False,
                    "required_confirmation": CONFIRMATION,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    refresh_run_id = (
        "district-readiness-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )

    with SessionLocal() as db:
        scope = resolve_scope(db, args.state, args.district)
        protected_before = protected_counts(db)
        active_before = active_snapshot_count(db, scope)

        started = time.perf_counter()
        readiness = _build_geography_layer_readiness_matrix(
            db=db,
            state_or_ut=scope["state_or_ut"],
            district=scope["district"],
            limit=50,
        )
        computation_elapsed_ms = round(
            (time.perf_counter() - started) * 1000,
            3,
        )

        rows = readiness.get("rows") or []
        scope_exact = (
            len(rows) == 1
            and rows[0].get("state_lgd_code")
                == scope["state_lgd_code"]
            and rows[0].get("district_lgd_code")
                == scope["district_lgd_code"]
            and rows[0].get("state_or_ut")
                == scope["state_or_ut"]
            and rows[0].get("district")
                == scope["district"]
        )
        schema_exact = (
            readiness.get("schema_version")
            == READINESS_SCHEMA_VERSION
        )
        computation_healthy = bool(
            readiness.get("healthy")
            and scope_exact
            and schema_exact
        )

        computed_at = datetime.now(timezone.utc)
        source_versions = {
            "lgd_identity": "DATABASE_CANONICAL_ACTIVE",
            "boundary_source_system": SOURCE_SYSTEM,
            "boundary_source_version": SOURCE_VERSION,
            "readiness_schema_version": READINESS_SCHEMA_VERSION,
        }
        evidence_metadata = {
            "calculation_mode":
                "OFFLINE_PRECOMPUTED_DISTRICT_SNAPSHOT",
            "geometry_computation_allowed_only_offline": True,
            "interactive_geometry_computation_authorized": False,
            "canonical_geography_changes_authorized": False,
            "global_mapping_changes_authorized": False,
            "project_override_changes_authorized": False,
            "runtime_activation_authorized": False,
            "android_behavior_change_authorized": False,
            "computation_elapsed_ms": computation_elapsed_ms,
            "readiness_payload_sha256": sha256_json(readiness),
        }

        database_writes_attempted = False
        action = "DRY_RUN_READY_NOT_APPLIED"
        snapshot_id = None

        if args.apply:
            if not computation_healthy:
                raise RuntimeError(
                    "Refusing apply because the computed snapshot "
                    "failed scope/schema/health validation"
                )

            database_writes_attempted = True
            snapshot_id = str(uuid.uuid4())

            db.execute(
                text(
                    """
                    update geography_layer_readiness_snapshots
                    set
                      is_active = false,
                      updated_at = now()
                    where state_id = cast(:state_id as uuid)
                      and district_id = cast(:district_id as uuid)
                      and is_active = true
                    """
                ),
                scope,
            )
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
                    **scope,
                    "id": snapshot_id,
                    "snapshot_schema_version":
                        SNAPSHOT_SCHEMA_VERSION,
                    "readiness_payload":
                        canonical_json(readiness),
                    "source_versions":
                        canonical_json(source_versions),
                    "evidence_metadata":
                        canonical_json(evidence_metadata),
                    "computed_at": computed_at,
                    "refresh_run_id": refresh_run_id,
                },
            )
            db.commit()
            action = "SNAPSHOT_APPLIED"

        protected_after = protected_counts(db)
        active_after = active_snapshot_count(db, scope)

        checks = {
            "canonical_scope_resolved": True,
            "readiness_schema_exact": schema_exact,
            "computed_scope_exact": scope_exact,
            "computed_readiness_healthy":
                bool(readiness.get("healthy")),
            "protected_counts_unchanged":
                protected_before == protected_after,
            "no_interactive_geometry_authorized": True,
            "no_runtime_activation_authorized": True,
            "no_android_behavior_change_authorized": True,
            "active_snapshot_count_valid": (
                active_after == 1
                if args.apply
                else active_after == active_before
            ),
            "dry_run_made_no_writes": (
                True
                if args.apply
                else not database_writes_attempted
            ),
        }

        healthy = computation_healthy and all(checks.values())
        result = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "status": action if healthy else "SNAPSHOT_INVALID",
            "healthy": healthy,
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "database_writes_attempted":
                database_writes_attempted,
            "refresh_run_id": refresh_run_id,
            "snapshot_id": snapshot_id,
            "scope": scope,
            "computed_at": computed_at.isoformat(),
            "computation_elapsed_ms": computation_elapsed_ms,
            "readiness_payload_sha256":
                evidence_metadata["readiness_payload_sha256"],
            "readiness_row_count": len(rows),
            "source_versions": source_versions,
            "evidence_metadata": evidence_metadata,
            "active_snapshot_count_before": active_before,
            "active_snapshot_count_after": active_after,
            "protected_counts_before": protected_before,
            "protected_counts_after": protected_after,
            "checks": checks,
            "policy": {
                "offline_computation_only": True,
                "interactive_geometry_computation_authorized":
                    False,
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
