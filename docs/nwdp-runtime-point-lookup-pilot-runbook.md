# NWDP Runtime Point Lookup Internal Pilot Runbook

## Scope

This runbook covers the guarded admin-only runtime lookup for:

`GET /api/v1/master-data/geography/nwdp-boundary-runtime/point-lookup`

The lookup is limited to runtime set:

`e5f93e27-a0bd-5c8b-bef3-d97986e14c55`

It currently contains 449,899 active runtime features and 449,899 active
village crosswalks backed by native PostGIS geometry: 110 preserved pilot
rows plus 449,789 rows from the separately authorized national V2 campaign.

The national campaign covers 30 state/UT source batches. It is not complete
36-state/UT coverage.

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

## Deferred controls

Shared gateway or distributed rate limiting is mandatory before customer,
Android, public, multi-worker production, or national-scale exposure. The
national runtime rows are active, but lookup remains disabled until that
control and a separate lookup-enablement authorization are in place. An
in-process counter is not considered sufficient.

## Expansion governance

Adding runtime rows, runtime sets, state/district access, Android behavior or
wider users requires a separate read-only assessment, proposal, explicit
authorization, bounded apply, reconciliation and rollback evidence.
