# NWDP Runtime Point Lookup Internal Pilot Runbook

## Scope

This runbook covers the guarded admin-only runtime lookup for:

`GET /api/v1/master-data/geography/nwdp-boundary-runtime/point-lookup`

The lookup is limited to runtime set:

`e5f93e27-a0bd-5c8b-bef3-d97986e14c55`

It currently contains `467,397` active runtime features and `467,397`
active village crosswalks backed by native PostGIS geometry. This includes the
independently audited `17,498`-row post-LGD deterministic cohort activated
across eight state transactions.

Another `65,005` deterministic rehabilitation rows remain inactive and
`14,773` unresolved rows remain held for review.

This runbook does not authorize Android, public, customer, project-scoped,
or additional runtime-set access. National runtime rows being active does
not itself authorize enabling the lookup endpoint.

## Request contract

Required query parameters:

- `latitude`: -90 through 90
- `longitude`: -180 through 180
- `runtime_set_id`: exact authorized runtime-set UUID

Authentication requires an admin principal with `AdminPermission.VIEW`.

Possible responses:

- `200 MATCHED`: exactly one active village polygon covers the point
- `200 UNMATCHED`: no active polygon covers the point
- `401` or `403`: authentication or authorization failed
- `409`: multiple active polygons cover the point; no automatic choice
- `422`: coordinates or runtime-set scope are invalid or missing
- `503`: lookup feature flag is disabled

## Enablement

The server-side setting is:

`NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED`

The local project reads it from:

`/home/lynksavvy/projects/farmint/.env`

The current post-campaign value is:

`NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED=false`

Restart the backend after changing the value.

## Resource guardrails

- `runtime_set_id` is mandatory.
- Lookup is restricted to active sets, features and village crosswalks.
- Source geometry must remain validated and runtime eligible.
- Native geometry must be non-null.
- The query uses a GiST bounding-box prefilter followed by `ST_Covers`.
- Ambiguity probing is capped at two rows.
- PostgreSQL `statement_timeout` is transaction-local and set to 2,000 ms.
- Geometry payloads are not returned.
- The endpoint performs no runtime, candidate, project-match or source writes.

## Health verification

A healthy matched response must include:

- schema `nwdp_boundary_runtime_point_lookup.v1`
- status `MATCHED`
- match count `1`
- exact runtime set, feature and crosswalk identities
- village UUID and LGD code
- runtime scope `village`
- geometry lineage hash

An outside point should return `UNMATCHED` with match count `0`.

## Disable and rollback

1. Set the root `.env` value to:

   `NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED=false`

2. Restart the backend process.
3. Confirm an authenticated request returns HTTP `503` with code
   `NWDP_RUNTIME_LOOKUP_DISABLED`.
4. Do not deactivate or delete runtime rows as part of the lookup rollback.
5. Preserve native geometry and authorization/reconciliation artifacts.

## Distributed rate-limit implementation — 2026-10-01

Commit `f0b5e13` added a Redis-backed distributed limiter at the authenticated
lookup boundary.

Implemented controls:

- atomic actor, tenant, and global budgets;
- server-owned tenant tiers: `FREE`, `STANDARD`, `PRO`, and `ENTERPRISE`;
- tier resolution from persisted `tenants.config`, never from a request header;
- configurable per-tier actor and tenant quotas;
- a configurable global quota and fixed window;
- `429` responses with stable code, limit headers, and `Retry-After`;
- fail-closed `503` behavior when Redis is missing, unavailable, or malformed;
- no coordinates, bearer tokens, or untrusted forwarding headers in Redis keys;
- the lookup feature flag is checked before Redis, so a disabled endpoint has
  no Redis dependency;
- Redis executes before spatial SQL when lookup is enabled;
- existing lookup, ambiguity, authorization, and database-write regressions
  remain green.

Current default posture:

- `NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED=false`;
- `NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED=false`;
- Redis URL unset;
- Android, customer, and public exposure unauthorized.

The implementation has passed static, behavioral fake-Redis, existing lookup,
and endpoint-boundary regressions. Commit `bd07091` also validated the limiter
against the system-wide local Redis service at `127.0.0.1:6379`: atomic budgets
were exact across threads and four independent worker processes, actor/tenant/
global exhaustion remained distinguishable, all four customer tiers received
their configured quotas, TTL reset and namespace isolation passed, and all test
keys were removed. Both application feature flags and the application Redis URL
remained unset during this evidence run.

## Deferred controls

The distributed limiter is implemented and locally integration-tested but is
not operationally enabled for Farmint. Production deployment secret/TLS
configuration, monitoring, multi-replica failure testing, and a separate
lookup-enablement authorization remain mandatory before customer, Android,
public, production multi-worker, or national-scale exposure. The local Redis
service is loopback-only with protected mode enabled; that is suitable for
local development, not evidence of production Redis readiness. An in-process
counter is not an acceptable fallback.

## Expansion governance

Adding runtime rows, runtime sets, state/district access, Android behavior or
wider users requires a separate read-only assessment, proposal, explicit
authorization, bounded apply, reconciliation and rollback evidence.
