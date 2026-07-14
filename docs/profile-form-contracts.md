# Backend-driven profile form contracts

Status: implemented as read-only contracts and admin inspection  
Scope: farmer, parcel, and soil profile form rendering  
Primary consumers: Android renderer, admin configuration/readiness screens

## Purpose

Agri-OS is moving farmer onboarding and profile maintenance toward the same backend-driven model already used for crop workflows. Android should not permanently own the structure of farmer, parcel, and soil forms. Instead, Android should render the active backend contract for the tenant/project context, while backend/admin own validation, versioning, feature flags, and future configuration.

This document defines the current contract and the intended safe rollout path.

## Current form family

The backend currently exposes these profile-related form schemas through `GET /api/v1/forms/{form_id}`:

| Form ID | Purpose | Current submit endpoint | Notes |
| --- | --- | --- | --- |
| `farmer_registration` | Create/update farmer identity and basic profile | `/api/v1/farmers` | Includes mobile, village, crop preference, language, and optional enrollment GPS point |
| `parcel_registration` | Register land parcel metadata | `/api/v1/parcels` | Includes area, ownership, irrigation, crop/soil hints, GPS point, and GPS polygon widgets |
| `soil_profile` | Capture observed or lab-tested soil details | `/api/v1/soil-profiles` | Supports manual, inferred, Soil Health Card, and lab-report style data |

These are currently static backend schemas, not yet admin-editable drafts.

## Discovery contract

Android/web should discover profile form availability through bootstrap/config endpoints:

- `GET /api/v1/app-config/bootstrap`
- `GET /api/v1/app-config/bootstrap?project_id={project_id}`
- `GET /api/v1/app-config/projects/{project_id}/effective-app-config` for admin inspection

The bootstrap response includes:

```json
{
  "profile_forms": {
    "farmer_registration": {
      "form_id": "farmer_registration",
      "version": "1.0.0",
      "endpoint": "/api/v1/forms/farmer_registration",
      "enabled": false,
      "feature_flag": "backend_driven_farmer_forms",
      "title": { "en": "Farmer Registration" }
    }
  }
}
```

The `enabled` flag is controlled by runtime feature flags:

| Feature flag | Form family |
| --- | --- |
| `backend_driven_farmer_forms` | farmer registration/profile |
| `backend_driven_parcel_forms` | parcel registration/profile/geometry |
| `backend_driven_soil_forms` | soil profile |

For MVP, Android may keep existing native screens while these flags are off. Once enabled for a tenant/project, Android should prefer backend-rendered forms for that family.

## Form schema contract

Each form schema includes:

- `form_id`
- `version`
- `title`
- `description`
- `fields[]`
- `submit_endpoint`
- `submit_method`
- `submit_label`

Each field can include:

- `id`
- `type`
- `label`
- `required`
- `source`
- `options`
- `depends_on`
- `depends_on_value`
- `default_value`
- `placeholder`
- `validation`
- `hint`
- `canonical_field`
- `android_hint`
- GPS/media-specific metadata such as `capture_modes`, `output_format`, `min_points`, `accuracy_required_meters`, and `allow_offline_capture`

Android should treat unknown optional metadata as forward-compatible hints, not fatal errors.

## Field dependency semantics

The dynamic renderer should apply the same conditional visibility semantics already used by crop/activity forms:

- if `depends_on` is absent/null: show field
- if `depends_on` exists and the dependency value is blank: hide field
- if `depends_on_value` exists: show only when dependency value equals `depends_on_value`
- if `depends_on` exists but `depends_on_value` is absent: show when dependency has any value

The backend serializes snake_case keys such as `depends_on` and `depends_on_value`; Android maps them to Kotlin/camelCase fields as needed.

## GPS geometry expectations

The profile forms use two GPS widget types:

| Widget | Typical usage | Expected output |
| --- | --- | --- |
| `GPS_POINT` | enrollment location, parcel pin | centroid latitude/longitude payload |
| `GPS_POLYGON` | parcel boundary walk/draw | GeoJSON Polygon with `[lng, lat]` coordinates |

Current backend geometry behavior:

- `PIN_DROP` stores `geometry_source=PIN_DROP` and centroid fields.
- `GPS_WALK` should store polygon GeoJSON/PostGIS geometry, centroid, and computed area where available.
- Hydration/profile responses should expose `geometry_source`, `centroid_lat`, `centroid_lng`, `computed_area_hectares` if available, and GeoJSON when the backend stores polygon geometry.

## Project-led vs self-service registration

The same form contracts must support both platform modes.

### Project-led enrollment

Used by FPOs, companies, insurers, NGOs, dealers, processors, and agronomy programs.

- Admin creates tenant/project configuration.
- Admin or field team bulk-enrolls farmers through web/CSV/sync.
- Android login hydrates farmer profile and project memberships.
- If backend-driven profile forms are enabled, Android renders project-effective forms for missing or editable profile sections.

### Direct self-service farmer registration

Used by farmers installing from Play Store without a company/project relationship.

- Android calls bootstrap without project context.
- Farmer verifies mobile number.
- Android hydrates existing profile if present.
- If no profile exists, Android renders tenant/default farmer registration flow.
- Farmer may later be attached to one or more projects.

The data model should not assume every farmer belongs to exactly one project.

## Admin visibility now available

Admin can inspect current contracts at:

- `/profile-forms`

The screen shows:

- effective tenant/default or project config
- profile form enabled flags
- form versions
- field counts and required counts
- GPS widget counts
- canonical field bindings
- dependency metadata
- source/options hints
- validation metadata

System Readiness includes `PROFILE_FORMS` and links to `/profile-forms`.

## Future edit lifecycle

Profile forms should follow the same safe pattern used for workflow configuration:

1. Read-only visibility
2. Draft version creation
3. Stage/section/field editing
4. Validation report
5. Publish/activate
6. Android consumes active published contract
7. Existing offline drafts remain compatible through version pinning or migration rules

Recommended future validations:

- required canonical fields exist for submit endpoint
- dependency references point to real fields
- `depends_on_value` is valid for option-backed dependencies
- GPS fields have compatible output formats
- option sources are known and reachable
- country/tenant-specific fields are gated by config
- removing a required field is blocked when active projects/farmers depend on it

## Android rollout guidance

For now, Android should continue using existing tested screens unless a relevant backend-driven feature flag is enabled.

When enabled, Android should:

1. Call bootstrap after login/project selection.
2. Read `profile_forms`.
3. Fetch enabled form schemas from their `endpoint`.
4. Render fields using the dynamic renderer.
5. Preserve backend IDs and local IDs for sync/hydration.
6. Store offline drafts with `form_id` and `version`.
7. Submit to each form's `submit_endpoint` or sync equivalent.

A consolidated Android implementation note should be produced after backend contracts stabilize further.
