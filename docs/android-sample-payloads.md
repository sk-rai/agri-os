# Android Sample Payload Bundle

Status date: 2026-07-20

This is a compact Android handoff payload map. It is intentionally representative rather than exhaustive. Android should treat backend schemas, feature flags, and response fields as source-of-truth.

## Integration order

1. Bootstrap and feature flags.
2. Backend-driven forms/options.
3. Farmer, parcel, and soil profile create/update.
4. Profile readiness and field-agent worklist.
5. Broadcast feed/detail/read/ack/media.
6. Weather and soil enrichment read-only cards.
7. Agent/farmer dual-mode polish.
8. Offline replay and conflict handling.

## 1. Mode bootstrap

Endpoint:

```http
GET /api/v1/auth/mode-bootstrap
X-Tenant-ID: {tenant_id}
```

Representative shape:

```json
{
  "schema_version": "app_bootstrap.v1",
  "tenant": { "id": "default", "exists": true, "type": "ENTERPRISE" },
  "feature_flags": {
    "backend_driven_profile_forms": true,
    "soil_enrichment_snapshots": true,
    "broadcasts": true
  },
  "profile_forms": {
    "farmer_registration": { "endpoint": "/api/v1/forms/farmer_registration" },
    "parcel_registration": { "endpoint": "/api/v1/forms/parcel_registration" },
    "soil_profile": { "endpoint": "/api/v1/forms/soil_profile" }
  }
}
```

Android rule: use this to decide enabled backend-driven flows. Do not hardcode feature availability.

## 2. Backend-driven forms/options

Endpoints:

```http
GET /api/v1/forms/{form_id}
GET /api/v1/forms/options
GET /api/v1/forms/options/{option_set}?project_id={project_id}
```

Representative field:

```json
{
  "id": "ownership_type",
  "type": "single_select",
  "source": "profile_options.ownership_types",
  "canonical_field": "parcel.ownership_type"
}
```

Android rule: render server-provided options for seasons, land units, ownership, irrigation, soil, languages, and assistance modes.

## 3. Farmer create/update

Endpoint:

```http
POST /api/v1/farmers
PATCH /api/v1/farmers/{farmer_id}
```

Representative request:

```json
{
  "mobile_number": "+919800000000",
  "display_name": "Sample Farmer",
  "pin_code": "560001",
  "village_name_manual": "Sample Village",
  "preferred_language": "hi",
  "assistance_mode": "FIELD_AGENT_ASSISTED"
}
```

Important alias: Android `assistance_mode` is normalized to backend enrollment/assistance fields where applicable.

## 4. Parcel create/update

Endpoint:

```http
POST /api/v1/parcels
PATCH /api/v1/parcels/{parcel_id}
```

Representative request:

```json
{
  "farmer_id": "{farmer_id}",
  "area": 1.25,
  "area_unit": "ACRE",
  "ownership_type": "OWNED",
  "pin_code": "560001",
  "village_name_manual": "Sample Village",
  "location_scope": "SINGLE_VILLAGE",
  "geometry_source": "PIN_DROP",
  "centroid_lat": 25.82,
  "centroid_lng": 82.97
}
```

Android rule: support simple single-village parcels first, but keep multi-location/custom scope fields round-trippable.

## 5. Soil profile create/update

Endpoint:

```http
POST /api/v1/soil-profiles
PATCH /api/v1/soil-profiles/{profile_id}
```

Representative request:

```json
{
  "farmer_id": "{farmer_id}",
  "parcel_id": "{parcel_id}",
  "data_source": "LAB_REPORT",
  "test_date": "2026-07-20",
  "lab_name": "Sample Lab",
  "ph": 7.2,
  "organic_carbon_oc": 0.55,
  "nitrogen_n": 163,
  "phosphorus_p": 9,
  "potassium_k": 213,
  "boron_b": 0.35
}
```

Important alias: Android may send `boron_b`; backend stores canonical `boron_bo`.

## 6. Profile readiness

Endpoint:

```http
GET /api/v1/farmers/profile-readiness?project_id={project_id}
```

Representative readiness fragment:

```json
{
  "profile_completion": {
    "is_complete_for_home": true,
    "missing_fields": [],
    "recommended_missing_fields": ["soil_profile"],
    "enrichment_readiness": {
      "has_weather_snapshot": true,
      "ready_for_weather_advisory": true,
      "has_soil_baseline_snapshot": true,
      "has_soilgrids_baseline_snapshot": true,
      "has_shc_slusi_snapshot": false,
      "ready_for_soil_moisture_enrichment": true
    }
  }
}
```

Android rule: display backend readiness; do not duplicate readiness logic locally.

## 7. Field-agent worklist

Endpoint:

```http
GET /api/v1/field-agent/worklist?actor_id={agent_user_id}&project_id={project_id}
```

Android rule: a farmer may also be an agent. Use bootstrap/worklist context to switch modes.

## 8. Broadcast feed/detail/read/ack

Endpoints:

```http
GET /api/v1/broadcasts/feed?farmer_id={farmer_id}
GET /api/v1/broadcasts/{campaign_id}
POST /api/v1/broadcasts/{campaign_id}/read
POST /api/v1/broadcasts/{campaign_id}/acknowledge
```

Representative feed item:

```json
{
  "id": "{campaign_id}",
  "title": "Rain advisory",
  "category": "WEATHER",
  "priority": "HIGH",
  "content": { "language_code": "hi", "title": "Rain advisory", "body_text": "..." },
  "media_attachments": [],
  "delivery_status": "PENDING"
}
```

Android rule: all targeting is backend-owned. Android only consumes assigned feed rows.

## 9. Weather read-only card

Endpoint:

```http
GET /api/v1/weather/snapshots/latest?farmer_id={farmer_id}
```

Representative shape:

```json
{
  "condition_code": "RAIN",
  "rainfall_probability_percent": 75,
  "rainfall_mm": 18.2,
  "temperature_min_c": 24.5,
  "temperature_max_c": 33.8,
  "risk_flags": ["RAIN_LIKELY", "FUNGAL_RISK"],
  "expires_at": "2026-07-20T18:00:00Z"
}
```

Android rule: weather is backend-only and snapshot-based. Do not call phone sensors or weather providers for advisory targeting.

## 10. Soil enrichment summary

Endpoint:

```http
GET /api/v1/soil-profiles/enrichments/summary?farmer_id={farmer_id}
GET /api/v1/soil-profiles/enrichments/summary?parcel_id={parcel_id}
```

Representative shape:

```json
{
  "schema_version": "soil_enrichment_summary.v1",
  "has_baseline": true,
  "has_moisture": true,
  "provider_counts": { "SOILGRIDS": 1, "OPEN_METEO": 1 },
  "latest_baseline": { "provider": "SOILGRIDS", "snapshot_type": "BASELINE" },
  "latest_moisture": { "provider": "OPEN_METEO", "snapshot_type": "MOISTURE" }
}
```

Android rule: consume grouped summary. Do not group raw provider rows locally.

## 11. Backend/admin-only endpoints Android should not call

- Weather provider configuration.
- Weather refresh workers.
- Weather operations health.
- Soil enrichment queue.
- Soil enrichment worker.
- Soil enrichment job audit.
- Soil enrichment operations health.
- Company profile administration.
- Company discovery/prepopulation.

## 12. Error payload patterns

Representative auth error:

```json
{
  "detail": {
    "error": "ADMIN_AUTHENTICATION_REQUIRED",
    "message": "Bearer token is required for admin mutations."
  }
}
```

Representative not-found error:

```json
{
  "detail": "Broadcast campaign not found"
}
```

Representative validation error:

```json
{
  "detail": [
    { "type": "string_pattern_mismatch", "loc": ["body", "job_type"], "msg": "String should match pattern ..." }
  ]
}
```

## Final note

Before Android rewiring begins, run:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/pre_android_handoff_check.py

cd ~/projects/farmint/web
npm run build
```

Then capture real sample responses from a known tenant/project/farmer fixture and update this document with concrete IDs redacted.

Captured redacted sample JSON files can be regenerated with `backend/scripts/capture_android_sample_payloads.py` and are stored under `docs/samples/android/`.

## PIN-code village candidate sample

The generated sample bundle now includes docs/samples/android/01-pin-code-villages.json.

Captured from: GET /api/v1/master-data/geography/villages/by-pin-code?pin_code=560001

Android should use this endpoint after a parcel PIN code is entered when the parcel is not in the same village/PIN as the farmer home. If the farmer confirms all parcels are in the same village/PIN as home, Android can copy farmer pin_code, village_id, and village_name_manual into parcel defaults and store location_scope.type=SAME_AS_HOME.
