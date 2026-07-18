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

### Android-aligned profile capture coverage

The current static schemas now mirror the Android enrollment/profile fields so Android can progressively switch from native hardcoded forms to backend-rendered forms without changing the captured business payload.

- `farmer_registration` includes mobile number (`phone` input), village ID with manual fallback, manual village name, PIN code, display/father name, age, gender, Aadhaar, language preference, assistance mode, total land summary, primary crop, and optional enrollment GPS.
- `parcel_registration` includes farmer/village linkage, reported area/unit, ownership, leased/shared/sharecrop conditional fields, irrigation source, current crop, Kharif/Rabi/Zaid crop sets, soil texture/color hints, GPS capture mode, GPS point, and GPS polygon.
- `soil_profile` includes manual/inferred/SHC/lab source flows, inferred soil hint fields, texture/color, pH/EC/organic carbon, macro/micronutrients, SHC card number, test date, and notes.
- Android payload name `boron_b` is preserved in the form schema and maps to backend canonical field `soil_profile.boron_bo` until the API/model alias is fully normalized.
- Seasonal crop fields use `android_hint.payload_container = crops_by_season` so Android can submit the existing `{ "KHARIF": [], "RABI": [], "ZAID": [] }` structure.

Backend ownership/configurability rule:

- Seasons, crop choices, land units, ownership modes, irrigation sources, soil textures/colors, soil data sources, and validation ranges must remain backend-owned contract values.
- Android may cache these values for offline use, but should refresh from bootstrap/forms/master-data and should not treat local hardcoded lists as authoritative once backend-driven forms are enabled.
- Tenant/project-specific overrides should be introduced through form/config versioning rather than Android releases.

Backend-owned option registry:

- `GET /api/v1/forms/options` lists available option sets for offline cache hydration.
- `GET /api/v1/forms/options/{option_set}` returns one option set.
- Fields may advertise sources such as `profile_options.land_units`, `profile_options.irrigation_sources`, `profile_options.soil_textures`, or `profile_options.seasons` while still embedding `options[]` for backward-compatible/offline rendering.
- Android should prefer the backend option source when available and use embedded field options as the local fallback.

Tenant/project overrides can be supplied through runtime app config under:

```json
{
  "profile_options": {
    "overrides": {
      "land_units": {
        "version": "project-land-units-v1",
        "title": { "en": "Project Land Units" },
        "options": [
          { "value": "ACRE", "label": { "en": "Acre" } },
          { "value": "HECTARE", "label": { "en": "Hectare" } }
        ],
        "metadata": { "configured_for": "project" }
      }
    }
  }
}
```

Android should pass `project_id` when hydrating option sets for a project-scoped enrollment/profile flow. The backend resolves defaults first, then tenant overrides, then project overrides.

Override validation is enforced during project app-config patches:

- option set keys must already exist in the backend registry;
- each override must include at least one option;
- option values must be non-empty and unique within the set;
- each option label must include an English fallback under `label.en`.

Invalid override patches return `400` with `detail.error = INVALID_PROFILE_OPTION_OVERRIDES` and per-field error codes.


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

## Profile completion/readiness summary

Profile hydration responses include backend-owned readiness guidance under `profile_completion` (`schema_version = profile_completion.v1`). Android should use this payload to decide profile completion prompts instead of hardcoding farmer, land, or soil readiness rules locally.

Current semantics:

- `is_complete_for_home` remains the safe launch gate. It requires basic farmer identity/location plus at least one land parcel.
- `missing_fields` contains only required gaps that block normal home launch.
- `recommended_missing_fields` contains non-blocking gaps such as soil profile, parcel location, language preference, or optional project enrollment.
- `sections.farmer`, `sections.land`, `sections.soil`, and `sections.project_enrollment` expose section-level `COMPLETE`, `PARTIAL`, or `MISSING` status.
- `next_actions[]` gives Android/admin a backend-prioritized checklist such as `ADD_PARCEL`, `CAPTURE_PARCEL_LOCATION`, or `ADD_SOIL_PROFILE`.

Soil profile remains recommended, not mandatory, for home launch. It becomes important for personalized advisories, weather/soil enrichment, and future trusted-corpus advisory generation.

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

## Android profile/project lifecycle context

After mobile login, Android should hydrate the farmer profile before deciding whether to show registration, home, project picker, or self-service mode. The current lifecycle-aware endpoints are:

- `GET /api/v1/farmers/by-mobile/{mobile}`
- `GET /api/v1/farmers/me/profile`
- `GET /api/v1/farmers/{farmer_id}/launch-context`

These responses include `project_enrollments`, `farmer_context`, and `enrollment_lifecycle`.

Android can request the backend-owned farmer/parcel/soil editing contract in the same hydration call:

```http
GET /api/v1/farmers/by-mobile/{mobile}?include_form_contract=true
GET /api/v1/farmers/me/profile?include_form_contract=true
GET /api/v1/farmers/me/profile?include_form_contract=true&project_id={project_id}
```

When requested, the response includes `form_contract`:

- `schema_version = profile_form_contract_bundle.v1`
- `forms.farmer_registration`
- `forms.parcel_registration`
- `forms.soil_profile`
- `option_sets` with effective backend-owned options such as seasons, land units, ownership types, irrigation sources, soil textures/colors, soil data sources, languages, and assistance modes

Default hydration omits this heavier bundle so older Android clients keep the same payload shape. New Android clients should use `include_form_contract=true` during login/profile hydration when they need to render or cache backend-driven profile screens. If `project_id` is supplied, tenant/project option overrides are applied; otherwise the backend uses the single active project context when unambiguous.

`farmer_context` is the high-level launch decision helper:

| Field | Meaning |
| --- | --- |
| `mode` | `PROJECT`, `PROJECT_PICKER`, or `SELF_SERVICE` |
| `reason` | Machine-readable explanation such as `ACTIVE_PROJECT_ENROLLMENT`, `MULTIPLE_ACTIVE_PROJECTS`, `NO_ACTIVE_PROJECT_AFTER_COMPLETED_PROJECT`, or `NO_PROJECT_ENROLLMENT` |
| `can_continue_independently` | True when Android can keep the farmer in self-service mode instead of returning to registration |
| `active_project_count` | Number of active project memberships |
| `completed_project_count` | Number of completed project memberships |
| `project_selection_required` | True when Android should ask the user to choose an active project context |
| `active_project_candidate` | The single active project enrollment when one unambiguous project context exists |

`enrollment_lifecycle` is the lower-level status summary Android can use for edge cases and future UI:

| Field | Meaning |
| --- | --- |
| `status_counts` | Counts by enrollment status |
| `active_count` / `pending_count` | Open project memberships |
| `completed_count` / `cancelled_count` | Closed project memberships |
| `active_pending_count` | `active_count + pending_count` |
| `has_open_enrollments` | True if the farmer is still attached to a live/pending project |
| `can_continue_independently` | True if there are no active/pending project memberships |
| `latest_event` / `events` | Recent lifecycle audit events when available |

Expected Android behavior:

1. If no profile exists, continue farmer enrollment.
2. If profile exists and `project_selection_required=true`, show project picker.
3. If one active project exists, use the project bootstrap context.
4. If all project enrollments are completed/cancelled/archived, keep the farmer in self-service mode. Do not force re-registration.
5. If an independent farmer later joins a company project, preserve the same `farmer_id` and add/update project enrollment locally after hydration/sync.

This supports both important lifecycle transitions:

- project farmer becomes unaffiliated after project completion and continues independently;
- independent farmer later becomes enrolled in a company/FPO/insurance/input-company project.

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

## Regression commands

Run after changing bootstrap/profile form contracts or Android renderer discovery metadata:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/run_platform_config_regressions.py
```
