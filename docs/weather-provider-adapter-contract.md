# Weather Provider Adapter Contract

This contract defines how backend weather integrations should normalize external or internal weather data into Agri-OS weather snapshots. It keeps provider-specific payloads out of broadcast targeting, Android, and farmer-facing advisory logic.

## Principles

- Weather is backend-owned and snapshot-based.
- Android never calls weather providers directly.
- Broadcast targeting reads only normalized `weather_snapshots`.
- Provider adapters may use free APIs, paid APIs, government/IMD feeds, satellite-derived services, IoT stations, or future internal models.
- Raw provider payloads are retained in `source_payload` for audit/debug, but downstream features must not depend on provider-specific structures.
- Refresh cadence is configured per provider through `weather_provider_configs.refresh_interval_hours`, defaulting to 6 hours.

## Current backend surfaces

Provider configuration:

```http
POST /api/v1/weather/providers
GET  /api/v1/weather/providers?enabled=true
GET  /api/v1/weather/providers/refresh-plan
POST /api/v1/weather/providers/{provider_id}/refresh
```

Snapshot access:

```http
POST /api/v1/weather/snapshots
GET  /api/v1/weather/snapshots?location_scope=VILLAGE&location_key=...
GET  /api/v1/weather/snapshots/latest?location_scope=VILLAGE&location_key=...
```

Admin UI:

- `/weather` shows providers, refresh plan, manual snapshots, and snapshot filters.
- Dashboard attention queues surface due providers and missing fresh snapshots.

## Adapter responsibility

A provider adapter is responsible for:

1. Reading due providers from `/api/v1/weather/providers/refresh-plan` or equivalent internal service call.
2. Fetching provider data for configured geography/project/parcel/weather-grid locations.
3. Converting provider response into normalized snapshot rows.
4. Calling `/api/v1/weather/providers/{provider_id}/refresh` with `status`, message, metadata, and snapshots.
5. Recording failures as refresh attempts with `status=FAILED` so admin readiness can show stale providers.

The adapter should not create broadcasts directly. Broadcast campaigns consume normalized snapshots via `WEATHER` audience rules.

## Normalized snapshot fields

Required or strongly recommended:

- `provider_id`: the configured provider.
- `location_scope`: one of `TENANT`, `PROJECT`, `FARMER`, `PARCEL`, `GEOPOINT`, `PINCODE`, `VILLAGE`, `DISTRICT`, `STATE`, `WEATHER_GRID`.
- `location_key`: stable provider/platform key for the location, where applicable.
- `fetched_at`: when data was fetched.
- `forecast_valid_from` / `forecast_valid_to`: validity window when forecast data is used.
- `expires_at`: when Agri-OS should stop using the snapshot for targeting.
- `condition_code`: normalized condition such as `HEAVY_RAIN`, `DROUGHT_STRESS`, `HEAT_STRESS`, `COLD_STRESS`, `THUNDERSTORM_WIND`, `CLEAR`, `RAIN`.
- `risk_flags`: normalized targeting signals such as `HEAVY_RAIN_NEXT_24H`, `FUNGAL_RISK`, `HEAT_STRESS_NEXT_48H`, `LOW_SOIL_MOISTURE`, `HIGH_WIND_ALERT`.
- `summary`: short human-readable explanation.
- `source_payload`: raw provider response or relevant excerpt.
- `metadata`: adapter-specific processing notes.

Optional agronomic/weather fields:

- `rainfall_probability_percent`
- `rainfall_mm`
- `temperature_min_c`
- `temperature_max_c`
- `humidity_percent`
- `wind_speed_kmph`
- `lat`
- `lng`

## Refresh semantics

- Default refresh interval is 6 hours, configurable per provider from 1 to 168 hours.
- The refresh endpoint updates `last_refresh_at` and `next_refresh_at` for the provider.
- Successful refreshes may create zero or more snapshots.
- Failed refreshes should still be recorded with `status=FAILED` and a clear message.
- Admin dashboard should treat due providers and missing fresh snapshots as operational attention signals.

## Broadcast targeting semantics

Broadcast audience rules can use:

```json
{
  "rule_type": "WEATHER",
  "operator": "IN",
  "values": ["HEAVY_RAIN_NEXT_24H", "FUNGAL_RISK"]
}
```

Matching currently checks non-expired snapshot `condition_code` and `risk_flags`.

Current location expansion supports:

- tenant-wide snapshot -> all active farmers in tenant
- project snapshot -> active farmers in that project
- farmer snapshot -> that active farmer
- parcel snapshot -> the parcel's active farmer
- village snapshot -> farmers/parcels whose manual village name matches `location_key`

Future expansion should add pincode, district/state, climatic zones, weather grids, and geospatial matching.

## Provider examples

### Open-Meteo style adapter

- Provider type: `EXTERNAL_API`
- Config may contain base URL, model choice, timezone, and location batch policy.
- Best initial use: rainfall probability, rainfall mm, temperature, humidity, wind, weather code.

### IMD/government feed adapter

- Provider type: `EXTERNAL_API` or `MANUAL`, depending on source maturity.
- Best initial use: district/state/pincode advisories and severe weather warnings.
- Store source bulletin identifiers in `source_payload` or `metadata`.

### Satellite/soil moisture adapter

- Provider type: `SATELLITE` or `INTERNAL_MODEL`.
- Best long-term use: parcel/grid-level moisture or drought stress enrichment.
- Normalize to risk flags such as `LOW_SOIL_MOISTURE` or `DROUGHT_STRESS`.

### Offline/trusted-corpus advisory engine

- Provider type may remain separate from weather providers, but it can consume `weather_snapshots` as structured context.
- It should generate draft advisory/broadcast content only from trusted corpus + structured platform context.
- Human/admin approval should remain the default before publishing automated advisories unless a tenant explicitly enables auto-publish policy.

## Do not do

- Do not expose provider API keys to Android.
- Do not let Android decide weather broadcast targeting.
- Do not let broadcasts parse raw provider payloads directly.
- Do not use expired snapshots for farmer targeting.
- Do not couple one provider's weather codes to core business logic without normalization.

## Next implementation steps

1. Add adapter module/service interface in backend code.
2. Add a first provider implementation, likely Open-Meteo/free API for development.
3. Add scheduler/worker invocation that uses refresh-plan due providers.
4. Add location expansion strategy for pincode/district/weather-grid.
5. Add configurable risk-flag thresholds per tenant/project/crop.
