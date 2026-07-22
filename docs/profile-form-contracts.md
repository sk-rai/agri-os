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

- Seasons, crop choices, land units, ownership modes, irrigation sources, soil types, soil textures/colors, soil data sources, and validation ranges must remain backend-owned contract values.
- Android may cache these values for offline use, but should refresh from bootstrap/forms/master-data and should not treat local hardcoded lists as authoritative once backend-driven forms are enabled.
- Tenant/project-specific overrides should be introduced through form/config versioning rather than Android releases.

Backend-owned option registry:

- `GET /api/v1/forms/options` lists available option sets for offline cache hydration.
- `GET /api/v1/forms/options/{option_set}` returns one option set.
- Fields may advertise sources such as `profile_options.land_units`, `profile_options.irrigation_sources`, `profile_options.soil_types`, `profile_options.soil_textures`, or `profile_options.seasons` while still embedding `options[]` for backward-compatible/offline rendering.
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

`profile_completion.enrichment_readiness` exposes backend-owned advisory/enrichment gates: land location, soil profile, current weather snapshot availability, weather-advisory readiness, soil-moisture-enrichment readiness, and future satellite-enrichment readiness. Android/admin should render these flags as guidance and should not duplicate eligibility rules locally.

For soil/land enrichment detail, use `GET /api/v1/soil-profiles/enrichments/summary?farmer_id={farmer_id}` or `?parcel_id={parcel_id}`. The summary groups latest SoilGrids-style baseline snapshots, Open-Meteo/soil-moisture snapshots, and SLUSI/SHC point captures so Android does not need to group raw provider records locally.

Readiness now distinguishes provider families for Android labels: `has_soilgrids_baseline_snapshot`, `soilgrids_baseline_snapshot_count`, `has_shc_slusi_snapshot`, and `shc_slusi_snapshot_count`. Use these to display source-specific messages such as SoilGrids baseline available, government SHC/SLUSI sample available, or soil moisture snapshot pending.

Backend/admin enrichment jobs can use `GET /api/v1/soil-profiles/enrichments/queue?project_id={project_id}&missing=ANY` to list location-ready parcels missing baseline or moisture snapshots. The queue is provider-neutral and returns `recommended_jobs[]` plus `latest_audit_by_job` for future SoilGrids, Open-Meteo, SLUSI/SHC, or in-house satellite workers.

Workers/admin tools can record queue attempt outcomes through `POST /api/v1/soil-profiles/enrichments/jobs/audit` and inspect history through `GET /api/v1/soil-profiles/enrichments/jobs/audit`. Status values are `QUEUED`, `FETCHED`, `FAILED`, `SKIPPED`, and `DEFERRED`.

Admin web now surfaces the soil enrichment queue and allows manual `SKIPPED`, `DEFERRED`, or `FAILED` audit markers for each recommended job. This keeps the operational loop usable before automated provider workers are connected.

Admin/agent summary screens can use `GET /api/v1/farmers/profile-readiness?project_id={project_id}` to list farmers with the same backend-owned readiness payload and aggregate counts for missing parcel, missing soil profile, parcel location capture, home readiness, personalized-advisory readiness, weather-advisory readiness, soil-moisture-enrichment readiness, and satellite-enrichment readiness.

Server-side filters keep Android/admin from duplicating readiness logic locally:

- `action_code=ADD_PARCEL|CAPTURE_PARCEL_LOCATION|ADD_SOIL_PROFILE` filters by backend `next_actions[].code`.
- `missing_field=parcel|parcel_location|soil_profile` filters across required and recommended missing fields.
- `section=land|soil|farmer|project_enrollment&section_status=MISSING|PARTIAL|COMPLETE` filters by backend section readiness.


## Agent profile identity model

Backend distinguishes identity/capability from farmer identity:

- `users` remains the login/account record and can hold tenant role capabilities.
- `agent_profiles` stores operational agent metadata such as role type, skills, languages, territory scope, availability, certification, and status.
- `farmers` remains the farmer/farm profile.
- One person can have both an `agent_profiles.farmer_id` link and a farmer profile, so Android should allow switching between personal farmer mode and assigned-agent mode without creating duplicate people.
- `GET /api/v1/field-agent/worklist` returns `agent_profile` and `mode_switch` when actor context resolves to an active agent profile; Android should use this to show “My Farm” and “Assigned Farmers” modes.
- Project assignment still comes from `project_roles` and farmer assignment still comes from `farmer_project_enrollments.assigned_user_ids`.

Admin APIs:

```http
GET /api/v1/admin/agent-profiles
POST /api/v1/admin/agent-profiles
GET /api/v1/admin/agent-profiles/{profile_id}
PATCH /api/v1/admin/agent-profiles/{profile_id}
```

Admin web now exposes `/agent-profiles` as the read-first management view for agent identity, linked farmer mode, skills/languages, territory scope, and project access.

## Field-agent assisted profile worklist

Backend now exposes an assisted-capture worklist for field agents, agronomists, dealers, and admins who collect farmer/land/soil data on behalf of enrolled farmers.

```http
GET /api/v1/field-agent/worklist?project_id={project_id}&assigned_only=true
X-Tenant-ID: {tenant_id}
X-Actor-ID: {agent_user_id}
```

Response schema: `field_agent_worklist.v1`.

Key behavior:

- `assigned_only=true` filters through `farmer_project_enrollments.assigned_user_ids`; without it, project admins can view the full project worklist.
- Each row includes `farmer`, `project_enrollments`, `parcel_count`, `soil_profile_count`, `active_crop_cycle_count`, `active_stage_count`, backend `profile_completion`, and prioritized `capture_actions`.
- Rows include `active_crop_cycles[]` with crop/season/status, current stage, stage counts, and capture/drilldown endpoints so Android agent mode can render “farmer summary → crop/stage detail → capture evidence/activity/event”.
- Rows also include first-page editable `parcels[]` and `soil_profiles[]` references so Android agent mode/admin can create missing records or patch existing records through the backend profile endpoints without a separate lookup.
- Agent/admin profile edit controls should hydrate `profile_options.*` from `/api/v1/forms/options/{option_set}` for languages, land units, soil types, textures, and colors instead of using hardcoded client lists.
- `capture_actions[]` is the Android/admin checklist for assisted capture, including profile completion, parcel creation/location capture, soil profile capture, field-event reporting, crop-stage evidence, and farmer query/follow-up recording.
- Optional filters `action_code`, `missing_field`, `section`, and `section_status` are supported here too, for example `action_code=ADD_SOIL_PROFILE` to show only assigned farmers needing soil capture.
- `endpoints` gives Android stable next-hop URLs for hydration, trace, parcels, field events, and query threads so an agent-mode summary screen can drill into the correct backend entities.
- An agent can also be a farmer. Android should keep individual farmer mode separate from assigned-agent worklist mode and select the mode from authenticated role/context rather than duplicating profiles locally.

Android should treat this endpoint as the backend-owned source of truth for assisted profile-capture priorities. Seasons, land units, soil types/textures/colors, and other profile choices remain backend-configurable through profile form contracts and option sources.


## Profile maintenance/update endpoints

Backend-driven profile forms now support both create and maintenance flows. Android agent mode and self-service profile screens should use these tenant-scoped endpoints when editing existing records:

```http
PATCH /api/v1/farmers/{farmer_id}
PATCH /api/v1/parcels/{parcel_id}
PATCH /api/v1/soil-profiles/{profile_id}
```

Update semantics:

- Requests are partial patches; omitted fields are preserved.
- Farmer updates validate backend-owned `land_units`, `languages`, and `assistance_modes` when those fields are supplied.
- Parcel updates validate backend-owned `land_units`, `ownership_types`, `irrigation_sources`, and `soil_types`; geometry remains on `/api/v1/parcels/{parcel_id}/geometry`.
- Parcel `current_crop_code` and `crops_by_season` are backend-owned too: crop codes must exist in the crop catalog, and `crops_by_season` keys must come from `profile_options.seasons`.
- Soil profile updates validate backend-owned `soil_types`, `soil_textures`, `soil_colors`, and `soil_data_sources`.
- Invalid/stale Android enum values return `INVALID_PROFILE_OPTION_VALUE` with the allowed backend option values.
- Cross-tenant updates return 404 so Android/admin cannot infer records outside the active tenant.

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
- `option_sets` with effective backend-owned options such as seasons, land units, ownership types, irrigation sources, soil types, soil textures/colors, soil data sources, languages, and assistance modes

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

## Agent profile admin management

Admin web now exposes `/agent-profiles` as a create/update management surface for operational users such as field agents, agronomists, dealers, managers, and enumerators.

Current admin capabilities:

- create or upsert an agent profile for an existing backend user;
- link an agent profile to an optional farmer profile, allowing the same person to operate in farmer and agent capacity;
- configure role type, status, display name, mobile number, skills, languages, territory scope, availability, certification, and metadata;
- preserve audit discipline by requiring a reason for create/update actions.

This keeps Android profile behavior backend-driven: Android should consume the assigned agent profile/worklist and only switch to farmer mode when `farmer_id`/`can_also_act_as_farmer` are present in backend responses.

## Parcel location and ownership backend contract

Land parcels are now backend-owned for both the common and edge cases:

- The normal case is one farmer with one or more parcels in a single village; each parcel can carry its own `pin_code` for weather, advisory, and targeting joins.
- Farmers may own multiple parcels, and those parcels may sit in different villages or pincodes.
- Cross-village or FPO-style edge cases should use `location_scope` as the explicit override bag, for example `primary_village`, `secondary_villages`, `pin_codes`, `village_ids`, `cluster_code`, or `scope_reason`.
- Ownership remains backend-configurable through `profile_options.ownership_types`; deployments can include values such as `OWNED`, `PART_OWNER`, `LEASED`, `SHARED`, `SHARECROP`, and `FAMILY` without hardcoding Android.
- Android should send the simplest parcel location fields first (`village_id`/`village_name_manual` + `pin_code`) and only populate `location_scope` when a plot spans multiple administrative locations or an FPO/tenant has custom grouping rules.

## Soil enrichment provider snapshots

Soil profile data now has two layers:

- `soil_profiles`: farmer/agent/manual/lab/SHC soil health records that represent the farmer's known soil profile.
- `soil_enrichment_snapshots`: provider-derived enrichment records for baseline or dynamic soil intelligence.

Provider snapshots are backend-only ingestion targets. Android should not call SoilGrids, Open-Meteo, satellite APIs, or future in-house models directly. Backend jobs/providers should write normalized snapshots and Android should consume the resulting backend contract.

Initial provider contract supports:

- `SOILGRIDS` baseline fields such as pH, organic carbon, nitrogen, clay/silt/sand percentages, bulk density, CEC, provider dataset, depth layer, and 250m resolution metadata.
- `OPEN_METEO` or future weather providers for dynamic moisture fields such as surface soil moisture, root-zone soil moisture, soil temperature, evapotranspiration, and expiry timestamps.
- Future in-house satellite/model-derived providers through the same `provider`, `snapshot_type`, `normalized_values`, `raw_payload`, and `metadata` fields.

Use parcel centroid/polygon first for provider lookup. Use parcel `pin_code`/`location_scope` only as fallback or grouping metadata where exact field geometry is not yet available.

## SoilGrids adapter handoff

Backend now has a SoilGrids adapter boundary for parcel-level baseline enrichment:

- `POST /api/v1/soil-profiles/enrichments/soilgrids/fetch` resolves parcel coordinates from centroid/GPS geometry/location-scope centroid and writes a normalized `SOILGRIDS` baseline snapshot.
- The endpoint accepts `provider_payload` for offline-safe scheduled jobs, tests, or future workers that fetch SoilGrids through WCS/WebDAV/GEE.
- `use_live_provider=true` enables the direct REST call path, but this should be treated as best-effort only because the SoilGrids REST API is beta/fair-use and may be unavailable.
- Android should never call SoilGrids directly; Android should read backend enrichment snapshots and display the latest baseline/moisture values supplied by backend.

Production provider strategy should prefer stable bulk/geospatial access paths where needed: WCS, WebDAV VRT/GeoTIFF, Google Earth Engine, or an internal cached tile/vector job. The normalized backend snapshot contract remains unchanged across those provider choices.

### Company/customer profile

Agri-OS now keeps a backend-only tenant-scoped company profile for the organization using the product, separate from farmer, agent, project, and Android profile data. This profile stores legal/display names, organization type, registration identifiers, support contacts, head-office details, operating geography, crop focus, service model, and backend configuration. Use `GET /api/v1/tenants/{tenant_id}/company-profile` and `PUT /api/v1/tenants/{tenant_id}/company-profile`; Android MVP does not need to render or mutate it.

Admin web exposes `/company-profile` for tenant admins to maintain this backend-only company profile without involving Android clients.

### Company profile prepopulation

Company profiles are now ready for future metadata seeding from public directories, government registries, partner lists, or bulk imports. Seeded records should use `profile_source`, `verification_status`, and `source_references[]`; when a company later enrolls, admins can claim/edit the existing profile and every change is recorded in `GET /api/v1/tenants/{tenant_id}/company-profile/audit`.

Company Profile admin also exposes source, verification status, source references, reason-for-change, and audit history so future prepopulated records can be claimed or corrected safely.

### Company discovery candidates

Future company prepopulation should land first in `company_discovery_candidates`, not directly in live tenant/company profiles. Use `POST /api/v1/company-discovery-candidates` for public-web, government-registry, partner-directory, or bulk-import discoveries; `GET /api/v1/company-discovery-candidates` for review queues; and `PATCH /api/v1/company-discovery-candidates/{candidate_id}/review` to mark records approved, rejected, duplicate, merged, stale, or linked to an existing tenant/profile.

Admin web exposes `/company-discovery` for reviewing staged company discovery candidates before they become live tenant/company profile data.

Specific company type values now include seed, fertilizer, pesticide, machinery, buyer, trader, warehouse, and financial-institution categories in addition to FPO, input company, processor, insurer, NGO, government, cooperative, agri-tech, enterprise, and other.

Approved discovery candidates can be applied into the live tenant company profile through `POST /api/v1/company-discovery-candidates/{candidate_id}/apply`; the action marks the candidate `MERGED`, updates the profile source/verification fields, and writes a company profile audit event.

### Company discovery CSV

Company discovery candidates can be staged in bulk through CSV: download `GET /api/v1/company-discovery-candidates/template.csv`, validate with `POST /api/v1/company-discovery-candidates/csv/validate`, and import with `POST /api/v1/company-discovery-candidates/csv/import`. Imported rows remain `PENDING_REVIEW`; they do not become live company profiles until reviewed/applied.

The `/company-discovery` admin page now exposes CSV template download, validation preview, and import actions so bulk company prepopulation can be staged without direct database access.

## Backend readiness checkpoint - 2026-07-20

Backend-driven profile readiness is now approximately **96% ready** for Android MVP handoff. Farmer, land/parcel, soil profile, agent mode, soil enrichment readiness, company profile, and company discovery/prepopulation contracts are backend-owned and documented.

Remaining work is mainly provider automation, Android UI consumption of these contracts, admin polish, production permission/audit review, and final regression/handoff packaging.

Weather operations health is now implemented in backend and admin web: `GET /api/v1/weather/operations/health` and admin `/weather` show provider due/overdue/failure status plus fresh/stale/expired snapshot counts.

### Soil enrichment operations health

Backend/admin can inspect enrichment queue and job health through `GET /api/v1/soil-profiles/enrichments/operations/health`. Response `schema_version=soil_enrichment_operations_health.v1` summarizes location-ready parcels, missing baseline/moisture counts, snapshot/provider counts, job audit outcomes, and recommended actions. Android MVP should not call this endpoint; it is an operations/admin readiness surface.

Admin `/soil-enrichment` also renders `soil_enrichment_operations_health.v1`, giving operators a single view of location-ready parcels, missing baseline/moisture counts, failed/deferred/skipped job audits, provider counts, and recommended backend actions.

See `docs/android-backend-handoff-packet.md` for the living Android/backend handoff packet and backend closeout checklist.

Backend/admin can preview or queue provider-neutral soil enrichment jobs through `POST /api/v1/soil-profiles/enrichments/worker/run-queue?dry_run=true|false`. The current worker creates `QUEUED` job audit rows and leaves real SoilGrids/Open-Meteo/SHC provider fetches to follow-up adapters.

Soil provider adapter normalization is isolated in `app/modules/farmer/soil_enrichment_adapters.py`. SoilGrids-style baseline payloads and Open-Meteo soil-moisture payloads are mapped into the internal `SoilEnrichmentSnapshot` field shape without network calls.

For no-network validation, backend/admin tools can call `POST /api/v1/soil-profiles/enrichments/worker/run-queue?dry_run=false` with body `demo_payloads.soilgrids` and/or `demo_payloads.open_meteo_soil`. The soil enrichment worker can normalize these demo payloads into saved snapshots while recording fetched job audit events.

Worker demo persistence can be forced with `demo_target.farmer_id`, `demo_target.parcel_id`, and optional `demo_target.project_id`; this creates saved snapshots from demo payloads even when the normal queue has no pending rows.

## Farmer enrollment location policy

Farmer enrollment should separate farmer residence location from land/parcel location.

For farmer residence/home:

- capture state, district, block/tehsil, and village where available;
- capture precise home GPS coordinates because many Indian village homes do not have reliable street addresses;
- keep manual village text as fallback when master geography is incomplete;
- do not use farmer home location as a substitute for land parcel location.

For land/parcel enrollment:

- ask for the PIN code where the land parcel is located;
- backend should return candidate villages for that PIN code;
- Android should display all villages mapped to that PIN code for user confirmation because one PIN code can cover multiple villages;
- selected village should be saved on the parcel;
- parcel GPS centroid or polygon should be captured when available;
- support override fields for the minority case where plots span multiple villages or PIN codes.

Backend ownership rule:

- Android should not maintain its own PIN-to-village mapping;
- PIN code, village, season, land unit, ownership, soil, and related options should remain backend-configurable;
- Android should request backend options/search results and persist selected IDs/codes.

### Farmer home and parcel land location flow

Android should treat farmer home location and parcel land location as separate concepts. During farmer registration, capture home PIN/village and optionally a precise home GPS point. During parcel registration, first ask whether all parcels are in the same PIN code/village as the farmer home. If yes, Android can copy farmer `pin_code`, `village_id`, and `village_name_manual` into parcel defaults while storing the confirmation in `location_scope`. If no, Android should ask parcel PIN code and call `GET /api/v1/master-data/geography/villages/by-pin-code?pin_code={pin_code}` to display candidate villages because one PIN code can map to multiple villages. GPS point/polygon remains optional precision capture and does not replace PIN/village selection.

## Parcel location validation guardrails

Backend validates parcel location semantics without requiring GPS. If a parcel is marked same_as_home_location=true, supplied parcel PIN/village fields must not conflict with the farmer home PIN/village. If same_as_home_location=false, parcel PIN and village are required. GPS point/polygon remains optional precision data and is not used as a replacement for PIN/village selection.

## Provider retry/error policy

Weather and soil provider adapters normalize HTTP failures into retryable and non-retryable classes. Retryable statuses are 408, 425, 429, 500, 502, 503, and 504. Non-retryable statuses are 400, 401, 403, 404, and 422. Workers should record retryable failures as audit/job events suitable for later retry, while non-retryable failures should be surfaced for configuration or source-data review.

## Provider runtime policy

Provider workers now have a shared runtime policy contract covering timeout_seconds, max_retries, backoff_seconds, rate_limit_window_seconds, max_requests_per_window, and demo_mode. Runtime policy is serialized into provider failure metadata so retries and production incidents can be audited without guessing which operational limits were active.

## Provider runtime policy in worker output

Weather and soil enrichment worker outputs now expose the runtime policy used for provider processing. This makes dry-run and execution responses auditable: operators can see timeout, retry, backoff, rate-limit, and demo-mode settings alongside worker results.

## Provider live execution safety policy

Live external provider execution is blocked by default. Provider config must explicitly set `live_execution_enabled=true` before live HTTP calls are allowed. Worker output exposes `live_execution.live_execution_status` so operators can distinguish demo/stub runs from approved live-provider runs.

## Provider HTTP client boundary

External provider HTTP calls must go through `app.modules.media.provider_http_client`. The boundary blocks live execution unless provider config explicitly enables it, and it is the future insertion point for timeout, retry, rate-limit, and response/error normalization. Raw HTTP calls should not be scattered across weather or soil modules.

Season and land-unit Android exposure checkpoint
The profile forms/options API now exposes backend-configured season and land-unit registry metadata. Android can keep displaying familiar values such as BIGHA/BISWA/KATHA/GUNTHA, while backend metadata marks variable local units as requiring geography-scoped conversion before normalized acre/hectare calculations and P&L summaries.

## Season and land-unit metadata endpoint

`GET /api/v1/forms/metadata/season-land-units` exposes Kharif/Rabi/Zaid/Perennial season metadata and land-unit conversion guidance. Android should use this endpoint when rendering area-unit warnings and should not hardcode local-unit conversion values.

Perennial and long-duration crop onboarding checkpoint
Added a backend policy contract for annual crops, perennial orchards, plantation crops, perennial spices, and agroforestry/timber systems. Android should allow existing orchards/plantations/agroforestry parcels to start at their current stage, while showing backend-configured warnings for missing establishment year, unusual stage, season/calendar mismatch, or geography mismatch.

Workflow BBCH and crop-system customization checkpoint
Added `docs/workflow-crop-system-bbch-customization.md`. BBCH remains the baseline crop-stage classification spine, while client/project workflow customizations layer labels, stage durations, decision nodes, recommendations, costs, and crop-system onboarding metadata on top through workflow templates/versions/overrides.
