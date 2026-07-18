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
POST /api/v1/weather/providers/run-due?dry_run=false
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
   - `POST /api/v1/weather/providers/run-due?dry_run=true` previews due providers.
   - `POST /api/v1/weather/providers/run-due` runs registered adapters for due enabled providers and records status/snapshots.
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
- Current backend status: offline-safe adapter skeleton exists. It normalizes `config.sample_payload` / `config.mock_payload`; it does not perform live network calls yet.
- Best initial use: rainfall probability, rainfall mm, temperature, humidity, wind, weather code.

Minimal provider config for admin testing:

```json
{
  "adapter": "open_meteo",
  "risk_thresholds": {
    "heavy_rain_mm": 20,
    "heavy_rain_probability_percent": 80,
    "fungal_humidity_percent": 80,
    "fungal_rain_probability_percent": 60,
    "heat_stress_temperature_max_c": 38,
    "high_wind_kmph": 40
  },
  "locations": [
    {
      "location_scope": "VILLAGE",
      "location_key": "Broadcast Village",
      "lat": "12.9716",
      "lng": "77.5946"
    }
  ],
  "sample_payload": {
    "fetched_at": "2026-07-17T12:00:00+00:00",
    "current": {
      "time": "2026-07-17T12:00:00+00:00",
      "temperature_2m": 29.4,
      "relative_humidity_2m": 88,
      "rain": 22.5,
      "weather_code": 63,
      "wind_speed_10m": 18
    },
    "hourly": {
      "precipitation_probability": [86],
      "rain": [22.5]
    }
  }
}
```

`risk_thresholds` is optional. If omitted, the adapter uses backend defaults. Clients can tune these thresholds per provider/project/crop deployment by storing overrides in provider `config.risk_thresholds` or `config.thresholds`.

Current Open-Meteo threshold keys:

- `heavy_rain_mm`: rainfall amount that upgrades `RAIN` to `HEAVY_RAIN`.
- `heavy_rain_probability_percent`: rainfall probability that can trigger `HEAVY_RAIN_NEXT_24H`.
- `fungal_humidity_percent`: humidity threshold for fungal-risk detection.
- `fungal_rain_probability_percent`: rainfall probability threshold for fungal-risk detection.
- `heat_stress_temperature_max_c`: maximum temperature threshold for heat-stress detection.
- `high_wind_kmph`: wind speed threshold for high-wind alerts.

When `Run adapter` is clicked from `/weather`, this config produces a normalized snapshot similar to:

```json
{
  "location_scope": "VILLAGE",
  "location_key": "Broadcast Village",
  "condition_code": "HEAVY_RAIN",
  "rainfall_probability_percent": 86,
  "rainfall_mm": "22.5",
  "humidity_percent": 88,
  "risk_flags": ["HEAVY_RAIN_NEXT_24H", "FUNGAL_RISK"],
  "metadata": {
    "adapter": "open_meteo",
    "risk_thresholds": {
      "heavy_rain_mm": 20,
      "heavy_rain_probability_percent": 80,
      "fungal_humidity_percent": 80,
      "fungal_rain_probability_percent": 60,
      "heat_stress_temperature_max_c": 38,
      "high_wind_kmph": 40
    }
  }
}
```

Live-fetch config can add:

```json
{
  "adapter": "open_meteo",
  "live_fetch_enabled": true,
  "base_url": "https://api.open-meteo.com/v1/forecast",
  "timezone": "Asia/Kolkata",
  "forecast_days": 2,
  "timeout_seconds": 10,
  "locations": [
    {
      "location_scope": "VILLAGE",
      "location_key": "Broadcast Village",
      "lat": "12.9716",
      "lng": "77.5946"
    }
  ]
}
```

Live-fetch mode is explicit: the adapter only calls Open-Meteo when `live_fetch_enabled=true` or `mode=live`. If a provider has neither `sample_payload` nor live mode enabled, refresh is safely marked `SKIPPED`. Live mode still normalizes into the same snapshot fields and stores the raw provider response in `source_payload`.

Supported live-fetch config fields:

- `base_url`: defaults to `https://api.open-meteo.com/v1/forecast`.
- `timezone`: defaults to `auto`; use `Asia/Kolkata` for India-focused runs.
- `forecast_days`: defaults to `2`.
- `timeout_seconds`: defaults to `10`.
- `current_fields`, `hourly_fields`, `daily_fields`: optional Open-Meteo field lists.
- `locations[]`: each location needs `lat`/`lng`; `location_scope` and `location_key` control how broadcasts later target farmers.

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

1. Add live Open-Meteo fetch mode behind the existing adapter skeleton.
2. Add scheduler/worker invocation that uses refresh-plan due providers.
3. Add location expansion strategy for pincode/district/weather-grid.
4. Add configurable risk-flag thresholds per tenant/project/crop.
5. Add IMD/government advisory adapter once source format and licensing are confirmed.
