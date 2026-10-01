#!/usr/bin/env python3
"""Read-only admin-only runtime lookup enablement readiness audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from redis import Redis
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import settings  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.core.distributed_rate_limit import (  # noqa: E402
    SUPPORTED_TIERS,
    policy_for_tier,
)


SCHEMA_VERSION = (
    "nwdp_runtime_lookup_admin_enablement_readiness.v1"
)
RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"
EXPECTED_ACTIVE_TOTAL = 467_397
EXPECTED_STATES = 35
EXPECTED_DISTRICTS = 779
EXPECTED_BLOCKS = 7_066
EXPECTED_VILLAGES = 600_647

GEOGRAPHY_API = (
    ROOT
    / "backend"
    / "app"
    / "modules"
    / "master_data"
    / "api"
    / "geography.py"
)
LIMITER_MODULE = (
    ROOT
    / "backend"
    / "app"
    / "core"
    / "distributed_rate_limit.py"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def scalar(connection, sql: str, **params: Any) -> int:
    return int(
        connection.execute(
            text(sql),
            params,
        ).scalar_one()
    )


def database_snapshot(connection) -> dict[str, int]:
    return {
        "states": scalar(
            connection,
            """
            select count(*)
            from geography_states
            where is_active
            """,
        ),
        "districts": scalar(
            connection,
            """
            select count(*)
            from geography_districts
            where is_active
            """,
        ),
        "blocks": scalar(
            connection,
            """
            select count(*)
            from geography_blocks
            where is_active
            """,
        ),
        "villages": scalar(
            connection,
            """
            select count(*)
            from geography_villages
            where is_active
            """,
        ),
        "active_runtime_features": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_runtime_features
            where is_active
            """,
        ),
        "active_runtime_crosswalks": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_runtime_crosswalks
            where is_active
            """,
        ),
        "active_candidates": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_crosswalk_candidates
            where is_active
            """,
        ),
        "promoted_candidates": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_crosswalk_candidates
            where promotion_status = 'PROMOTED'
            """,
        ),
        "project_matches": scalar(
            connection,
            """
            select count(*)
            from geography_boundary_project_matches
            """,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    args = parser.parse_args()
    started = time.perf_counter()

    geography_source = GEOGRAPHY_API.read_text(
        encoding="utf-8"
    )
    limiter_source = LIMITER_MODULE.read_text(
        encoding="utf-8"
    )

    feature_flag_position = geography_source.index(
        "if not settings."
        "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED"
    )
    limiter_position = geography_source.index(
        "enforce_nwdp_runtime_lookup_rate_limit("
    )
    spatial_query_position = geography_source.index(
        "ST_Covers("
    )

    with engine.connect() as connection:
        before = database_snapshot(connection)

        runtime_set = dict(
            connection.execute(
                text("""
                    select
                      id::text as id,
                      status,
                      activation_status,
                      is_active
                    from geography_boundary_runtime_sets
                    where id = cast(:runtime_set_id as uuid)
                """),
                {"runtime_set_id": RUNTIME_SET_ID},
            ).mappings().one()
        )

        tenant = connection.execute(
            text("""
                select
                  id,
                  is_active,
                  coalesce(config, '{}'::jsonb) as config
                from tenants
                where id = 'default'
            """)
        ).mappings().one_or_none()

        gist_indexes = [
            dict(row)
            for row in connection.execute(
                text("""
                    select indexname, indexdef
                    from pg_indexes
                    where schemaname = 'public'
                      and tablename =
                        'geography_boundary_runtime_features'
                      and lower(indexdef) like '%using gist%'
                    order by indexname
                """)
            ).mappings()
        ]

        sample = connection.execute(
            text("""
                select
                  rf.id::text as runtime_feature_id,
                  rw.village_id::text as village_id,
                  ST_X(
                    ST_PointOnSurface(rf.geometry_wgs84_geom)
                  ) as longitude,
                  ST_Y(
                    ST_PointOnSurface(rf.geometry_wgs84_geom)
                  ) as latitude
                from geography_boundary_runtime_features rf
                join geography_boundary_runtime_crosswalks rw
                  on rw.runtime_feature_id = rf.id
                 and rw.runtime_set_id = rf.runtime_set_id
                 and rw.is_active
                where rf.runtime_set_id =
                      cast(:runtime_set_id as uuid)
                  and rf.is_active
                  and rf.geometry_wgs84_geom is not null
                order by rf.id
                limit 1
            """),
            {"runtime_set_id": RUNTIME_SET_ID},
        ).mappings().one()

        after = database_snapshot(connection)

    tenant_config = (
        tenant["config"]
        if tenant
        and isinstance(tenant["config"], dict)
        else {}
    )
    resolved_tier = str(
        tenant_config.get(
            "nwdp_runtime_lookup_tier"
        )
        or "FREE"
    ).strip().upper()
    tier_policy = (
        policy_for_tier(resolved_tier)
        if resolved_tier in SUPPORTED_TIERS
        else None
    )

    redis_url = (
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL
    )
    redis_ping = False
    if redis_url:
        client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        try:
            redis_ping = bool(client.ping())
        finally:
            client.close()

    service_active = subprocess.run(
        ["systemctl", "is-active", "redis-server"],
        check=False,
        text=True,
        capture_output=True,
    ).stdout.strip()
    service_enabled = subprocess.run(
        ["systemctl", "is-enabled", "redis-server"],
        check=False,
        text=True,
        capture_output=True,
    ).stdout.strip()

    checks = {
        "database_counts_unchanged":
            before == after,
        "canonical_baseline_exact":
            before["states"] == EXPECTED_STATES
            and before["districts"] == EXPECTED_DISTRICTS
            and before["blocks"] == EXPECTED_BLOCKS
            and before["villages"] == EXPECTED_VILLAGES,
        "active_runtime_total_exact":
            before["active_runtime_features"]
            == EXPECTED_ACTIVE_TOTAL
            and before["active_runtime_crosswalks"]
            == EXPECTED_ACTIVE_TOTAL,
        "candidate_state_unchanged":
            before["active_candidates"] == 0
            and before["promoted_candidates"] == 0,
        "project_matches_unchanged":
            before["project_matches"] == 0,
        "runtime_set_identity_exact":
            runtime_set["id"] == RUNTIME_SET_ID,
        "runtime_set_active":
            runtime_set["is_active"] is True,
        "runtime_set_status_supported":
            runtime_set["status"] == "PILOT_ACTIVE"
            and runtime_set["activation_status"] == "ACTIVE",
        "lookup_currently_disabled":
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED
            is False,
        "limiter_currently_enabled":
            settings
            .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED
            is True,
        "redis_url_configured":
            bool(redis_url),
        "redis_ping":
            redis_ping,
        "redis_service_active":
            service_active == "active",
        "redis_service_enabled":
            service_enabled == "enabled",
        "tenant_exists_and_active":
            tenant is not None
            and tenant["is_active"] is True,
        "tenant_tier_supported":
            resolved_tier in SUPPORTED_TIERS,
        "tier_policy_resolves":
            tier_policy is not None,
        "admin_view_permission_required":
            "require_admin_permission("
            "AdminPermission.VIEW"
            in geography_source,
        "runtime_set_scope_required":
            "runtime_set_id: UUID = Query(...)"
            in geography_source,
        "coordinate_bounds_present":
            "ge=-90, le=90" in geography_source
            and "ge=-180, le=180"
            in geography_source,
        "feature_flag_before_limiter":
            feature_flag_position < limiter_position,
        "limiter_before_spatial_query":
            limiter_position < spatial_query_position,
        "statement_timeout_present":
            "statement_timeout" in geography_source,
        "bounded_ambiguity_probe":
            "limit 2" in geography_source.lower(),
        "gist_index_present":
            bool(gist_indexes),
        "native_geometry_sample_present":
            bool(sample["runtime_feature_id"]),
        "observability_present":
            "rate_limit_observability_snapshot"
            in limiter_source
            and "nwdp_runtime_lookup_rate_limit "
            in limiter_source,
        "fail_closed_error_present":
            "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE"
            in limiter_source,
        "stable_429_present":
            "NWDP_RUNTIME_LOOKUP_RATE_LIMITED"
            in limiter_source,
    }

    ready = all(checks.values())

    authorization_plan = {
        "authorized": False,
        "authorization_scope": (
            "LOCAL_ADMIN_ONLY_RUNTIME_LOOKUP_PILOT"
        ),
        "proposed_behavior_change": {
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED":
                "false -> true",
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED":
                "remain true",
            "redis_target":
                "remain loopback-only local Redis",
            "allowed_callers":
                "authenticated AdminPermission.VIEW principals",
            "customer_android_public_access":
                "not authorized",
        },
        "pre_authorization_requirements": [
            "review this audit and its source hashes",
            "confirm local admin-only scope",
            "confirm current tenant tier and quotas",
            "confirm backend restart window",
            "confirm immediate rollback command",
        ],
        "apply_sequence_after_separate_authorization": [
            "capture database and Redis key baselines",
            "set only the lookup feature flag true",
            "restart the backend",
            "run one authenticated in-boundary canary",
            "run one authenticated outside-boundary canary",
            "verify rate-limit headers and structured event",
            "verify exact Redis key TTLs and dimensions",
            "verify database counts unchanged",
        ],
        "acceptance_criteria": [
            "admin authentication remains mandatory",
            "runtime_set_id remains mandatory",
            "exact expected runtime feature is returned",
            "outside point remains unmatched",
            "no ambiguous result is returned",
            "limiter executes before spatial SQL",
            "Redis outage returns fail-closed 503",
            "database and project counts remain unchanged",
        ],
        "rollback": [
            "set lookup feature flag false",
            "restart the backend",
            "confirm authenticated lookup returns "
            "NWDP_RUNTIME_LOOKUP_DISABLED",
            "preserve active runtime features and crosswalks",
            "do not alter candidate, project, or Android state",
        ],
        "not_authorized": [
            "production or public exposure",
            "Android lookup behavior",
            "customer self-service access",
            "canonical geography changes",
            "runtime data deactivation",
            "tenant tier mutation",
        ],
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "READY_FOR_SEPARATE_ADMIN_ONLY_AUTHORIZATION"
            if ready
            else "NOT_READY"
        ),
        "healthy": ready,
        "authorized": False,
        "database_writes_attempted": False,
        "database_before": before,
        "database_after": after,
        "runtime_set": runtime_set,
        "tenant_rate_limit": {
            "tenant_id":
                tenant["id"] if tenant else None,
            "tenant_active":
                tenant["is_active"] if tenant else None,
            "persisted_tier":
                tenant_config.get(
                    "nwdp_runtime_lookup_tier"
                ),
            "resolved_tier": resolved_tier,
            "uses_default_free_tier":
                "nwdp_runtime_lookup_tier"
                not in tenant_config,
            "policy": (
                {
                    "window_seconds":
                        tier_policy.window_seconds,
                    "actor_requests":
                        tier_policy.actor_requests,
                    "tenant_requests":
                        tier_policy.tenant_requests,
                    "global_requests":
                        tier_policy.global_requests,
                }
                if tier_policy
                else None
            ),
        },
        "redis": {
            "configured": bool(redis_url),
            "ping": redis_ping,
            "service_active": service_active,
            "service_enabled": service_enabled,
            "credentials_reported": False,
        },
        "endpoint_guardrails": {
            "api_sha256": sha256(GEOGRAPHY_API),
            "limiter_sha256": sha256(LIMITER_MODULE),
            "gist_indexes": gist_indexes,
            "sample_runtime_feature_id":
                sample["runtime_feature_id"],
            "sample_village_id": sample["village_id"],
            "sample_coordinates_recorded": False,
        },
        "checks": checks,
        "authorization_plan": authorization_plan,
        "policy": {
            "lookup_enablement_authorized": False,
            "lookup_exposure_changed": False,
            "redis_configuration_changed": False,
            "tenant_tier_changed": False,
            "database_writes_attempted": False,
            "canonical_changes_attempted": False,
            "runtime_data_changes_attempted": False,
            "project_changes_attempted": False,
            "android_changes_attempted": False,
        },
        "remaining_production_gates": [
            "production Redis secret and TLS configuration",
            "production persistence and HA policy",
            "external log collection and alert routing",
            "production exposure authorization",
        ],
        "elapsed_ms": round(
            (time.perf_counter() - started) * 1000,
            3,
        ),
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, sort_keys=True))
    if not ready:
        print(
            "NWDP ADMIN-ONLY LOOKUP ENABLEMENT "
            "READINESS AUDIT FAILED",
            file=sys.stderr,
        )
        return 1

    print(
        "NWDP ADMIN-ONLY LOOKUP ENABLEMENT READINESS "
        "AUDIT PASSED; ENABLEMENT NOT AUTHORIZED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
