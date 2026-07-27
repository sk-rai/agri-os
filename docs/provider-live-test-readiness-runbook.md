# Provider Live Test Readiness Runbook

Status date: 2026-07-27

This runbook defines when backend provider live calls may be enabled for testing.

Android must not call live providers directly. Android consumes saved backend snapshots and readiness summaries.

## Current local audit result

Read-only audit script:

    backend/scripts/audit_provider_live_readiness.py

Latest local result:

- weather credentials present: no;
- soil credentials present: no;
- geocoding credentials present: no;
- weather provider config table exists: yes;
- weather provider config rows: 31;
- live-enabled provider rows: 0;
- safe for demo live weather test: no;
- safe for demo live soil test: no;
- safe for bulk geocoding: no;
- external calls made by audit: no;
- secrets printed by audit: no.

## Live test gate

Do not enable live provider execution until all gates below are satisfied.

### Gate 1: Provider selected

Choose exactly one provider and one test flow.

Allowed first candidates:

- weather snapshot refresh for one test parcel;
- soil moisture/baseline refresh for one test parcel if provider credentials and terms are clear.

Do not enable all providers globally.

### Gate 2: Credentials configured safely

Credentials must be provided via environment or secret manager.

Do not:

- commit credentials;
- paste secrets into docs;
- print secrets in script output;
- store unrestricted provider keys in demo seed files.

### Gate 3: Test tenant/provider scoped

Live execution must be scoped to:

- one test tenant;
- one provider;
- one farmer/parcel or very small parcel set.

Avoid enabling live calls for `default` tenant unless explicitly intended.

### Gate 4: Runtime policy explicit

Use conservative defaults for test mode:

- timeout: 10-20 seconds;
- max retries: 0-1 initially;
- rate-limit window: 60 seconds;
- max requests per window: low single digits for first test;
- no uncontrolled batch jobs.

### Gate 5: Terms and caching reviewed

Before bulk use, review:

- provider terms of service;
- rate limits;
- storage/caching rights;
- attribution requirements;
- paid billing limits;
- data retention policy.

Bulk village geocoding remains blocked until this review is complete.

## First live smoke-test shape

Preferred first weather smoke test:

1. Pick one test tenant.
2. Pick one parcel with known centroid GPS.
3. Enable one provider config for that tenant.
4. Run one backend worker/adaptor command manually.
5. Confirm one saved weather snapshot row.
6. Confirm Android still reads only the saved snapshot endpoint.

Preferred first soil smoke test:

1. Pick one test tenant.
2. Pick one parcel with known centroid GPS.
3. Enable one backend soil provider config or explicit adapter gate.
4. Run one backend worker/adaptor command manually.
5. Confirm one saved soil enrichment snapshot row.
6. Confirm Android still reads only soil enrichment latest/summary endpoints.

## Android rule

Android should render:

- weather snapshot cards;
- soil enrichment snapshot cards;
- readiness/warning messages;
- provider-unavailable or pending states.

Android should not:

- call external weather providers;
- call external soil providers;
- call geocoding providers;
- infer provider readiness locally;
- retry provider jobs locally.

## Current status

Provider live calls remain deferred.

The backend is prepared for safe testing only after credentials, scoped provider config, and rate policy are explicitly approved.
