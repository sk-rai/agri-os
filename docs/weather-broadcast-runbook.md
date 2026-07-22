# Weather Broadcast Runbook

This runbook explains the backend-first flow for weather-triggered broadcasts. Android does not call weather APIs or evaluate weather rules locally; it only receives generated broadcast deliveries.

## 1. Configure a weather provider

Use admin `/weather` or `POST /api/v1/weather/providers`.

Minimum Open-Meteo live config:

```json
{
  "adapter": "open_meteo",
  "live_fetch_enabled": true,
  "base_url": "https://api.open-meteo.com/v1/forecast",
  "timezone": "Asia/Kolkata",
  "forecast_days": 2,
  "locations": [
    {
      "location_scope": "VILLAGE",
      "location_key": "Broadcast Village",
      "lat": "12.9716",
      "lng": "77.5946"
    }
  ],
  "risk_thresholds": {
    "heavy_rain_mm": 20,
    "heavy_rain_probability_percent": 80,
    "fungal_humidity_percent": 80,
    "fungal_rain_probability_percent": 60,
    "heat_stress_temperature_max_c": 38,
    "high_wind_kmph": 40
  }
}
```

Use `refresh_interval_hours` on the provider to control cadence. The default operating model is a backend scheduler every 6 hours, customizable per provider.

## 2. Refresh weather snapshots

For manual/admin operation:

```http
POST /api/v1/weather/providers/{provider_id}/run-adapter
```

For scheduler operation:

```http
GET /api/v1/weather/providers/refresh-plan?enabled=true
POST /api/v1/weather/providers/run-due?dry_run=true
POST /api/v1/weather/providers/run-due
POST /api/v1/weather/providers/{provider_id}/run-adapter
```

The due-run endpoint is the backend scheduler hook: cron/worker code can call it every few minutes, and each provider still controls its cadence through `refresh_interval_hours` and `next_refresh_at`. Admin `/weather` exposes the same flow with **Preview due** and **Run due providers** controls, so operations can test scheduler behavior without Android involvement.

The adapter writes normalized `weather_snapshots`. Downstream features should use these fields, not raw provider-specific payloads:

- `location_scope`
- `location_key`
- `condition_code`
- `risk_flags`
- `fetched_at`
- `expires_at`
- rainfall/temperature/humidity/wind values where available

## 3. Inspect snapshots

Use admin `/weather` or:

```http
GET /api/v1/weather/snapshots?location_scope=VILLAGE&location_key=Broadcast%20Village
GET /api/v1/weather/snapshots/latest?location_scope=VILLAGE&location_key=Broadcast%20Village
```

Only non-expired snapshots are used for normal weather broadcast targeting.

## 4. Create a weather broadcast

Create a normal broadcast campaign with category `WEATHER` and a `WEATHER` audience rule:

```json
{
  "title": "Heavy rainfall alert",
  "category": "WEATHER",
  "priority": "URGENT",
  "contents": [
    {
      "language_code": "en",
      "title": "Heavy rainfall expected",
      "body_text": "Heavy rainfall is likely in your area. Avoid spraying and ensure field drainage."
    }
  ],
  "audience_rules": [
    {
      "rule_type": "WEATHER",
      "operator": "IN",
      "values": ["HEAVY_RAIN_NEXT_24H"]
    }
  ]
}
```

A weather rule matches snapshots whose `condition_code` or `risk_flags` contain any configured value.

## 5. Combine criteria

The same broadcast can combine weather with project, crop, stage, language, farmer, or location criteria.

Default `audience_match_mode` is `ANY`, meaning a farmer matching any supported rule is eligible.

Use campaign metadata for intersection mode:

```json
{
  "metadata": {
    "audience_match_mode": "ALL"
  }
}
```

In `ALL` mode, the farmer must match every supported rule. This is useful for precise broadcasts like: farmers in a project, growing rice, at flowering stage, in a village with heavy-rain risk.

## 6. Preview before delivery

```http
GET /api/v1/broadcasts/{campaign_id}/audience-preview
```

Preview returns:

- estimated farmer count;
- matched rules per sample farmer;
- weather snapshot evidence for `WEATHER` rules, including snapshot scope, location, matched risk terms, and risk flags;
- unsupported rule count.

Admins should preview before publishing/generating deliveries, especially when combining multiple criteria.

## 7. Publish and generate deliveries

```http
POST /api/v1/broadcasts/{campaign_id}/publish
POST /api/v1/broadcasts/{campaign_id}/generate-deliveries
```

Delivery generation is idempotent. Existing deliveries are skipped and summarized in campaign metadata.

## 8. Retry undelivered broadcasts

```http
POST /api/v1/broadcasts/{campaign_id}/retry-undelivered
```

Retry applies to `PENDING` and `FAILED` delivery rows. `DELIVERED` and `ACKNOWLEDGED` rows are skipped. After 3 retry attempts, delivery is marked `FAILED` with `failure_reason=MAX_RETRIES_EXCEEDED`.

## 9. Android behavior

Android receives weather broadcasts through the normal farmer broadcast feed:

```http
GET /api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code=hi&include_read=true
```

Android should:

- render `category=WEATHER` prominently;
- respect campaign priority such as `URGENT`;
- show content/media/deeplink as delivered;
- mark read/ack through existing delivery endpoints;
- not call weather APIs;
- not locally re-evaluate weather targeting.

## Current limitations

- Initial weather location expansion supports tenant, project, farmer, parcel, and manual village-name snapshots.
- Pincode, district/state, climatic-zone, and geospatial weather-grid expansion remain future work.
- Live Open-Meteo fetch is available, but production deployment should add scheduler supervision, provider rate-limit handling, and alerting for stale snapshots.

### Weather operations health

Backend/admin can inspect weather provider health through `GET /api/v1/weather/operations/health`. Response `schema_version=weather_operations_health.v1` summarizes enabled, due, overdue, failed providers and fresh/stale/expired snapshots. Android should not call this endpoint for MVP; it is an operations/scheduler/admin readiness surface.

Admin `/weather` now renders `weather_operations_health.v1`, including provider due/overdue/failure state and fresh/stale/expired snapshot counts.


Backend workers can preview or execute due provider refresh work through `POST /api/v1/weather/refresh-worker/run-due?dry_run=true|false`. The current implementation is a backend-only worker stub: it identifies due providers and advances provider refresh metadata when executed, while real external provider fetch adapters remain a follow-up.


Open-Meteo adapter normalization is now isolated in `app/modules/media/weather_provider_adapters.py`. The helper maps provider JSON into the internal WeatherSnapshot field shape and derives condition/risk flags without making network calls.


For no-network validation, a weather provider config can include `demo_payload`, `demo_location_scope`, and `demo_location_key`. Running `POST /api/v1/weather/refresh-worker/run-due?dry_run=false` will normalize the demo payload through the Open-Meteo adapter and persist a WeatherSnapshot.

Manual provider worker invocation is available through `backend/scripts/run_due_provider_workers.py --tenant-id {tenant_id} --dry-run`. This runs weather and soil enrichment worker stubs from one ops command before scheduler wiring.

## Provider retry/error policy

Weather and soil provider adapters normalize HTTP failures into retryable and non-retryable classes. Retryable statuses are 408, 425, 429, 500, 502, 503, and 504. Non-retryable statuses are 400, 401, 403, 404, and 422. Workers should record retryable failures as audit/job events suitable for later retry, while non-retryable failures should be surfaced for configuration or source-data review.

## Provider runtime policy

Provider workers now have a shared runtime policy contract covering timeout_seconds, max_retries, backoff_seconds, rate_limit_window_seconds, max_requests_per_window, and demo_mode. Runtime policy is serialized into provider failure metadata so retries and production incidents can be audited without guessing which operational limits were active.

## Provider runtime policy in worker output

Weather and soil enrichment worker outputs now expose the runtime policy used for provider processing. This makes dry-run and execution responses auditable: operators can see timeout, retry, backoff, rate-limit, and demo-mode settings alongside worker results.

## Provider worker scheduler runbook

See `docs/provider-worker-scheduler-runbook.md` for dry-run-first provider worker scheduling guidance, cron/systemd examples, execution-mode gates, failure review, and recovery links.

## Provider live execution safety policy

Live external provider execution is blocked by default. Provider config must explicitly set `live_execution_enabled=true` before live HTTP calls are allowed. Worker output exposes `live_execution.live_execution_status` so operators can distinguish demo/stub runs from approved live-provider runs.

## Provider HTTP client boundary

External provider HTTP calls must go through `app.modules.media.provider_http_client`. The boundary blocks live execution unless provider config explicitly enables it, and it is the future insertion point for timeout, retry, rate-limit, and response/error normalization. Raw HTTP calls should not be scattered across weather or soil modules.
