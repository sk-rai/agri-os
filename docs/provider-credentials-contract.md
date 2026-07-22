# Provider Credentials Contract

This document defines the production credential and safety contract for external weather and soil enrichment providers.

No real credentials should be committed to this repository.

## Backend environment variables

- `WEATHER_PROVIDER_API_KEY`
- `WEATHER_PROVIDER_API_SECRET`
- `WEATHER_PROVIDER_LIVE_EXECUTION_ENABLED`
- `SOIL_PROVIDER_API_KEY`
- `SOIL_PROVIDER_API_SECRET`
- `SOIL_PROVIDER_LIVE_EXECUTION_ENABLED`

Live execution flags default to false in backend settings. Production deployment must explicitly enable live execution only after provider source permissions, rate-limit budgets, monitoring, and recovery procedures are approved.

## Provider config fields

Provider rows may also carry non-secret operational config:

- `base_url`
- `timeout_seconds`
- `max_retries`
- `backoff_seconds`
- `rate_limit_window_seconds`
- `max_requests_per_window`
- `live_execution_enabled`
- `demo_payload` for no-network validation

Secrets belong in environment/secret manager only, not in provider config JSON.

## Live execution gate

Provider HTTP calls must go through `app.modules.media.provider_http_client`. That boundary blocks live execution unless live execution is explicitly enabled. Workers expose runtime policy and live execution status in output for auditability.

## Android boundary

Android must not receive provider secrets and must not call external provider APIs directly. Android consumes backend-owned snapshots, readiness labels, and advisory/profile contracts only.
