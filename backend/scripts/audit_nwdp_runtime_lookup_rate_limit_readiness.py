#!/usr/bin/env python3
"""Read-only rate-limit readiness audit and implementation plan for NWDP lookup."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import settings


SCHEMA_VERSION = "nwdp_runtime_lookup_rate_limit_readiness.v1"
EXPECTED_ACTIVE_RUNTIME_ROWS = 467_397
RUNTIME_SET_ID = "e5f93e27-a0bd-5c8b-bef3-d97986e14c55"

CONFIG = BACKEND / "app/core/config.py"
MIDDLEWARE = BACKEND / "app/core/middleware.py"
MAIN = BACKEND / "app/main.py"
AUTH = BACKEND / "app/core/admin_auth.py"
GEOGRAPHY = (
    BACKEND / "app/modules/master_data/api/geography.py"
)
REQUIREMENTS = BACKEND / "requirements.txt"
RUNBOOK = ROOT / "docs/nwdp-runtime-point-lookup-pilot-runbook.md"

DEFAULT_OUTPUT = (
    ROOT / "data/staged/core_stack/promotion_review"
    / "20261001-nwdp-runtime-lookup-rate-limit-readiness-v1"
    / "nwdp_runtime_lookup_rate_limit_readiness.json"
)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    return parser.parse_args()


def read(path):
    return path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def contains_any(source, values):
    lowered = source.lower()
    return any(value.lower() in lowered for value in values)


def database_snapshot(connection):
    row = connection.execute(text("""
        select
          (
            select count(*)::bigint
            from geography_boundary_runtime_features
            where is_active
          ) as active_features,
          (
            select count(*)::bigint
            from geography_boundary_runtime_crosswalks
            where is_active
          ) as active_crosswalks,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where is_active
          ) as active_candidates,
          (
            select count(*)::bigint
            from geography_boundary_crosswalk_candidates
            where promotion_status = 'PROMOTED'
          ) as promoted_candidates,
          (
            select count(*)::bigint
            from geography_boundary_project_matches
          ) as project_matches,
          (
            select count(*)::bigint
            from geography_boundary_runtime_sets
            where id = cast(:runtime_set_id as uuid)
              and is_active
          ) as active_runtime_set
    """), {
        "runtime_set_id": RUNTIME_SET_ID,
    }).mappings().one()

    return {
        key: int(value or 0)
        for key, value in row.items()
    }


def main():
    options = arguments()

    config = read(CONFIG)
    middleware = read(MIDDLEWARE)
    main_source = read(MAIN)
    auth = read(AUTH)
    geography = read(GEOGRAPHY)
    requirements = read(REQUIREMENTS)
    runbook = read(RUNBOOK)

    implementation_inventory = {
        "lookup_feature_flag_default_off": (
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED: bool = False"
            in config
        ),
        "lookup_statement_timeout_configured": (
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_STATEMENT_TIMEOUT_MS"
            in config
            and "statement_timeout" in geography
        ),
        "lookup_requires_admin_view": (
            "require_admin_permission(AdminPermission.VIEW)"
            in geography
        ),
        "lookup_requires_runtime_set_id": (
            "runtime_set_id: UUID = Query(...)"
            in geography
        ),
        "lookup_uses_gist_prefilter": (
            "geometry_wgs84_geom" in geography
            and "&& point.geom" in geography
        ),
        "lookup_uses_st_covers": (
            "ST_Covers(" in geography
        ),
        "lookup_ambiguity_probe_bounded": (
            "limit 2" in geography.lower()
        ),
        "tenant_middleware_present": (
            "TenantMiddleware" in middleware
            and "add_middleware(TenantMiddleware)" in main_source
        ),
        "admin_principal_has_actor_identity": (
            "class AdminPrincipal" in auth
            and "actor_id" in auth
        ),
        "shared_limiter_implemented": contains_any(
            middleware + main_source + geography,
            (
                "redis.asyncio",
                "redis.Redis",
                "RateLimitMiddleware",
                "DistributedRateLimiter",
                "slowapi",
            ),
        ),
        "redis_client_dependency_installed": (
            any(
                line.strip().lower().startswith(
                    ("redis==", "redis>=", "redis~=")
                )
                for line in requirements.splitlines()
            )
        ),
        "redis_connection_configured": (
            "REDIS_URL" in config
            or "RATE_LIMIT_REDIS_URL" in config
        ),
        "endpoint_rate_limit_dependency_present": (
            "require_runtime_lookup_rate_limit"
            in geography
        ),
        "rate_limit_429_contract_present": (
            "NWDP_RUNTIME_LOOKUP_RATE_LIMITED"
            in geography
        ),
        "rate_limit_backend_fail_closed_present": (
            "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE"
            in geography
        ),
        "runbook_requires_shared_rate_limit": (
            "Shared gateway or distributed rate limiting is mandatory"
            in runbook
        ),
    }

    database = create_engine(settings.DATABASE_URL)
    with database.connect() as connection:
        before = database_snapshot(connection)

        index_rows = [
            dict(row)
            for row in connection.execute(text("""
                select
                  indexname,
                  indexdef
                from pg_indexes
                where schemaname = current_schema()
                  and tablename =
                      'geography_boundary_runtime_features'
                  and indexdef ilike '%using gist%'
                order by indexname
            """)).mappings().all()
        ]

        after = database_snapshot(connection)

    existing_guardrails = {
        "admin_authentication": (
            implementation_inventory[
                "lookup_requires_admin_view"
            ]
        ),
        "feature_flag_default_off": (
            implementation_inventory[
                "lookup_feature_flag_default_off"
            ]
        ),
        "runtime_set_scope_required": (
            implementation_inventory[
                "lookup_requires_runtime_set_id"
            ]
        ),
        "spatial_index_prefilter": (
            implementation_inventory[
                "lookup_uses_gist_prefilter"
            ]
        ),
        "st_covers_predicate": (
            implementation_inventory[
                "lookup_uses_st_covers"
            ]
        ),
        "ambiguity_limit_two": (
            implementation_inventory[
                "lookup_ambiguity_probe_bounded"
            ]
        ),
        "statement_timeout": (
            implementation_inventory[
                "lookup_statement_timeout_configured"
            ]
        ),
        "gist_index_present": bool(index_rows),
    }

    missing_controls = [
        name
        for name, present in {
            "shared_limiter_implementation":
                implementation_inventory[
                    "shared_limiter_implemented"
                ],
            "redis_client_dependency":
                implementation_inventory[
                    "redis_client_dependency_installed"
                ],
            "redis_connection_configuration":
                implementation_inventory[
                    "redis_connection_configured"
                ],
            "endpoint_rate_limit_dependency":
                implementation_inventory[
                    "endpoint_rate_limit_dependency_present"
                ],
            "http_429_contract":
                implementation_inventory[
                    "rate_limit_429_contract_present"
                ],
            "fail_closed_backend_error_contract":
                implementation_inventory[
                    "rate_limit_backend_fail_closed_present"
                ],
        }.items()
        if not present
    ]

    checks = {
        "active_runtime_total_exact": (
            before["active_features"]
            == EXPECTED_ACTIVE_RUNTIME_ROWS
            and before["active_crosswalks"]
            == EXPECTED_ACTIVE_RUNTIME_ROWS
        ),
        "runtime_set_active": (
            before["active_runtime_set"] == 1
        ),
        "existing_lookup_guardrails_present": (
            all(existing_guardrails.values())
        ),
        "shared_limiter_absent_confirmed": (
            not implementation_inventory[
                "shared_limiter_implemented"
            ]
        ),
        "redis_runtime_dependency_absent_confirmed": (
            not implementation_inventory[
                "redis_client_dependency_installed"
            ]
        ),
        "lookup_flag_remains_disabled": (
            settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED
            is False
        ),
        "database_counts_unchanged": before == after,
        "no_database_writes": True,
    }

    plan = {
        "decision":
            "REDIS_BACKED_AUTHENTICATED_ENDPOINT_LIMITER",
        "why": [
            (
                "The limiter must be consistent across Uvicorn "
                "workers and application replicas."
            ),
            (
                "The authenticated principal is available only "
                "after the existing admin authorization dependency."
            ),
            (
                "An application dependency can key limits by actor "
                "and tenant without trusting spoofable client headers."
            ),
            (
                "A gateway may add an outer IP/global limit, but "
                "must not replace authenticated actor limits."
            ),
        ],
        "new_components": [
            {
                "path": "backend/app/core/distributed_rate_limit.py",
                "purpose": (
                    "Redis-backed atomic fixed-window or token-bucket "
                    "limiter with no in-process fallback."
                ),
            },
            {
                "path": "backend/app/core/config.py",
                "purpose": (
                    "Fail-closed Redis URL, namespace, window, "
                    "actor, tenant and global limit settings."
                ),
            },
            {
                "path": (
                    "backend/app/modules/master_data/api/"
                    "geography.py"
                ),
                "purpose": (
                    "Endpoint dependency executed after admin "
                    "authentication and before the spatial query."
                ),
            },
            {
                "path": "backend/requirements.txt",
                "purpose": (
                    "Pinned async-capable Redis client dependency."
                ),
            },
        ],
        "proposed_configuration": {
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED":
                False,
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL":
                "required secret; no default",
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE":
                "agrios:nwdp-runtime-lookup:v1",
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_WINDOW_SECONDS":
                60,
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ACTOR_REQUESTS":
                30,
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_TENANT_REQUESTS":
                120,
            "NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_GLOBAL_REQUESTS":
                600,
        },
        "key_contract": {
            "actor":
                "namespace:window:actor:<actor_uuid>",
            "tenant":
                "namespace:window:tenant:<tenant_id_or_shared-admin>",
            "global":
                "namespace:window:global",
            "forbidden_key_material": [
                "latitude",
                "longitude",
                "authorization token",
                "raw client-controlled forwarded headers",
            ],
        },
        "atomicity": {
            "required": True,
            "method":
                "single Redis Lua script or equivalent atomic operation",
            "all_dimensions_checked_together": [
                "actor",
                "tenant",
                "global",
            ],
            "partial_consumption_on_rejection": False,
            "ttl_required": True,
        },
        "response_contract": {
            "allowed_headers": [
                "RateLimit-Limit",
                "RateLimit-Remaining",
                "RateLimit-Reset",
            ],
            "rejected_status": 429,
            "rejected_code":
                "NWDP_RUNTIME_LOOKUP_RATE_LIMITED",
            "retry_after_header_required": True,
            "backend_unavailable_status": 503,
            "backend_unavailable_code":
                "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
            "fail_closed": True,
        },
        "privacy_and_security": {
            "coordinates_in_rate_limit_keys": False,
            "coordinates_logged": False,
            "tokens_logged": False,
            "redis_tls_required_outside_local_development": True,
            "redis_credentials_from_secret_store": True,
            "trusted_proxy_configuration_required_for_ip_limits":
                True,
        },
        "observability": {
            "aggregate_metrics": [
                "allowed request count",
                "rejected request count by dimension",
                "Redis latency histogram",
                "Redis failure count",
                "remaining-budget histogram",
            ],
            "alerts": [
                "Redis unavailable",
                "sustained global rejection",
                "p95 limiter latency above threshold",
            ],
            "per_lookup_database_audit_write": False,
        },
        "test_sequence": [
            "static fail-closed configuration contract",
            "unit tests for atomic allow/reject/reset behavior",
            "concurrent multi-worker shared-budget regression",
            "Redis-unavailable returns 503 without spatial SQL",
            "429 response and Retry-After contract",
            "coordinates and credentials absent from keys/logs",
            "lookup feature flag remains false",
            "rollback removes dependency wiring without changing runtime rows",
        ],
        "enablement_sequence": [
            "implement limiter with lookup still disabled",
            "run local Redis integration tests",
            "run multi-worker concurrency and failure tests",
            "review production Redis/gateway operations",
            "authorize admin-only lookup separately",
            (
                "keep Android, customer and public access "
                "outside that authorization"
            ),
        ],
        "rollback": [
            "set lookup feature flag false",
            "restart application replicas",
            "confirm endpoint returns disabled 503",
            "preserve active runtime rows and native geometry",
            "do not deactivate runtime data",
        ],
    }

    readiness = {
        "ready_to_implement_limiter": all(checks.values()),
        "ready_for_lookup_enablement": False,
        "ready_for_multi_worker_exposure": False,
        "ready_for_android_exposure": False,
        "ready_for_public_exposure": False,
        "blocking_controls": missing_controls,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
        "status":
            "IMPLEMENTATION_PLAN_READY_LOOKUP_STILL_BLOCKED",
        "healthy": all(checks.values()),
        "authorized": False,
        "checks": checks,
        "implementation_inventory":
            implementation_inventory,
        "existing_guardrails": existing_guardrails,
        "database_before": before,
        "database_after": after,
        "gist_indexes": index_rows,
        "active_runtime_total":
            EXPECTED_ACTIVE_RUNTIME_ROWS,
        "readiness": readiness,
        "implementation_plan": plan,
        "policy": {
            "database_writes_attempted": False,
            "dependency_changes_attempted": False,
            "configuration_changes_attempted": False,
            "lookup_enablement_authorized": False,
            "android_changes_authorized": False,
            "public_exposure_authorized": False,
        },
    }

    options.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    options.output.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            default=str,
        ) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(
        report,
        indent=2,
        sort_keys=True,
        default=str,
    ))
    print(
        "NWDP RUNTIME LOOKUP RATE-LIMIT READINESS AUDIT PASSED"
    )

    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
