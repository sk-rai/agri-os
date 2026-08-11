# Admin localization and land-intelligence summary plan

Status: Proposed next backend/admin contract

This plan combines two adjacent product capabilities:

1. admin-managed multilingual label/content overrides;
2. a backend-driven Android land-intelligence summary screen.

The goal is to keep Android as a renderer while backend/admin remains the source of truth for labels, regional context, crop suitability, and project/company overrides.

## Product rationale

Agri-OS should support field operations across languages, crops, states, companies, and project types without requiring a new Android APK for every client.

Two related needs are emerging:

- organizations need control over translated labels/copy, especially for crop stages, inputs, form labels, and local terminology;
- field users need a simple, trusted summary of local land/crop context before entering detailed workflows.

## Admin localization surface

### V1 scope

Admin should be able to view backend-owned defaults and add tenant/project-specific overrides for:

- backend-driven form labels;
- option-set labels;
- crop stage names;
- crop stage descriptions;
- input names/categories where locally relevant;
- informational land-intelligence summary copy.

Supported initial languages:

- English: `en`
- Hindi: `hi`
- Kannada: `kn`
- Marathi: `mr`
- Punjabi: `pa`

Future demo-expansion candidates:

- Tamil: `ta`
- Telugu: `te`
- Bengali/Bangla: `bn`

### Admin UX principles

For each translatable item, admin should see:

- stable key/path;
- default English label;
- existing default Hindi label when available;
- current tenant/project override;
- language code;
- review status;
- last updated by/at;
- fallback preview.

Admin should be able to:

- add or edit override text;
- mark override as reviewed;
- hide/deactivate an override;
- fall back to backend default;
- export/import translation backlog for human review.

### Important boundaries

Translation overrides must not change business semantics.

- changing a crop-stage label should not change stage code, lifecycle order, or workflow transition rules;
- changing an input display name should not change input code, compatibility, or traceability;
- missing regional labels must fall back to English;
- Android must not hardcode translations for backend-driven content.

## Land-intelligence summary screen

### V1 scope

Android should render a read-only informational screen from backend payload.

The screen should summarize:

- region/location context;
- season context;
- weather/climate context;
- soil context;
- water/irrigation context;
- suitable main crops;
- suitable alternate crops;
- confidence/caveat text.

The screen is informational only in V1. It should not block farmer onboarding, parcel creation, or crop-cycle creation.

### Example Android sections

- Region
- Current/selected season
- Climate/weather pattern
- Soil suitability
- Water/irrigation context
- Suitable main crops
- Suitable alternate crops
- Notes/caveats

### Backend-driven payload principle

Backend should provide summarized display-ready content, not raw geometry or complex data layers.

Android should render title, summary, cards, caveats, and source/last-updated labels.

Android should not compute suitability locally.

### Company/project override model

Defaults can be prepopulated from platform master data.

Tenant/project admins should later be able to override:

- summary text;
- crop lists;
- confidence labels;
- caveats;
- language-specific copy;
- whether the screen is enabled for a project.

### Suggested V1 endpoint

Existing land-intelligence context can be extended or paired with a summary endpoint:

- `GET /api/v1/profile/land-intelligence-context?pin_code={pin_code}&crop_code={crop_code}&season_code={season_code}`
- `GET /api/v1/profile/land-intelligence-summary?pin_code={pin_code}&season_code={season_code}&project_id={project_id}`

Decision to be made during backend design:

- extend the existing context endpoint; or
- add a separate summary endpoint optimized for Android rendering.

## V1 data model options

Option A: JSON config in project/tenant config.

Good for fastest demo iteration.

Pros:

- low migration cost;
- flexible;
- easy project override.

Cons:

- weaker audit/query/reporting;
- can become messy as content grows.

Option B: dedicated localization/content tables.

Better long-term.

Possible tables:

- `localized_content_keys`
- `localized_content_overrides`
- `land_intelligence_summary_defaults`
- `land_intelligence_summary_overrides`

Pros:

- auditable;
- reviewable;
- import/export friendly;
- supports admin workflow.

Cons:

- more backend/admin work.

Recommended path:

- use a small dedicated table design for translation/content overrides;
- keep land-intelligence summary payload simple and Android-ready;
- avoid raw geometry or live-provider dependency in V1.

## Demo positioning

This feature supports a strong commercial message:

Agri-OS does not just collect farmer data. It lets organizations configure how agricultural intelligence is localized, summarized, and delivered to field teams and farmers across projects and languages.

## Deferred V2 ideas

- clickable detail cards;
- crop-specific detail pages;
- source/evidence links;
- native translations for Tamil, Telugu, Bengali/Bangla;
- admin approval workflow;
- live weather and soil-provider integration;
- irrigation-source plausibility using canal/groundwater datasets;
- district/block/village-level summary overrides;
- role-specific views for farmer, field agent, agronomist, and admin.

## Read-only localization content source audit

Script:

- `backend/scripts/audit_admin_localization_content_sources.py`

Latest audit summary:

- mode: `READ_ONLY_AUDIT`
- DB writes: `false`
- external calls: `false`
- content keys inventoried: `468`
- English fallback complete: `true`
- Hindi labels present: `462 / 468`
- Kannada native labels present: `0 / 468`
- Marathi native labels present: `0 / 468`
- Punjabi native labels present: `0 / 468`
- ready to design override tables: `true`

Content sources currently included:

- backend-driven profile forms;
- backend-driven profile form fields;
- backend-driven profile field options;
- profile option sets;
- profile option set options;
- workflow stage names/descriptions.

Input/product catalog content was intentionally reported as skipped for this first pass because the live column shapes differ from the audit assumptions. This can be added in a later hardening pass after inspecting the input/product catalog schema.

Recommended first implementation tables:

- `localized_content_keys`
- `localized_content_overrides`
- later: `land_intelligence_summary_overrides`

V1 admin localization should start with form/option/workflow-stage overrides because those sources already have complete English fallback and stable backend-owned key paths.

## Localized content override table foundation

Backend migration `053_add_localized_content_overrides.py` adds the first durable admin localization foundation.

Tables:

- `localized_content_keys`
- `localized_content_overrides`
- `land_intelligence_summary_overrides`

Seed script:

- `backend/scripts/seed_admin_localization_content_keys.py`

Verifier:

- `backend/scripts/verify_admin_localization_tables.py`

Latest local verification:

- migration applied: `true`
- seeded content keys: `308`
- missing English fallback labels: `0`
- active localized overrides: `0`
- active land-intelligence summary overrides: `0`
- ready for admin API contract: `true`

Seeded content-key sources:

- profile forms: `15`
- profile form fields: `104`
- profile form field options: `98`
- profile option sets: `11`
- profile option set options: `60`
- workflow stages: `20`

V1 implication:

Admin localization can now start with form, option, and workflow-stage content keys. Overrides should be tenant/project/language scoped and must not change workflow semantics, crop-stage codes, input codes, or traceability identifiers.

## Admin localization API and screen v1 — 2026-08-11

Implemented first admin localization management slice:

- backend admin API at `/api/v1/admin/localization`;
- summary endpoint for seeded content-key/source counts;
- searchable content-key listing with effective label resolution;
- tenant/project/language scoped override upsert;
- override deactivate path;
- admin web screen at `/localization`;
- sidebar entry under Configuration;
- authenticated smoke test covering create, effective override, deactivate, and fallback behavior.

Current scope is management and preview of localization overrides. The next backend step is to wire these effective overrides into Android-facing backend-driven form/option/workflow payloads so Android automatically receives tenant/project-specific labels.

Smoke evidence:

- `backend/scripts/test_admin_localization_api.py` passed;
- `web` lint passed for localization page, API client, and sidebar;
- seeded registry has 308 platform-owned content keys;
- English fallback remains complete;
- Kannada override smoke proved `EN_FALLBACK -> TENANT_OVERRIDE -> EN_FALLBACK` lifecycle.

## Android-facing localization override delivery — 2026-08-11

Published admin localization overrides now flow into Android-facing backend-driven payloads without changing workflow/form semantics.

Runtime delivery scope:

- `/api/v1/forms/{form_id}` overlays published tenant/project label overrides into form label maps;
- `/api/v1/forms/options/{option_set}` overlays published tenant/project option labels;
- `/api/v1/app-config/bootstrap` overlays localized form titles in `forms` and `profile_forms`;
- profile hydration form contracts inherit the same runtime overlay path;
- Android can keep the existing contract: `labels[currentLanguageCode] ?: labels["en"]`.

Smoke evidence:

- `backend/scripts/test_android_localization_override_delivery.py` passed;
- form title override delivered to `/api/v1/forms/farmer_registration`;
- option label override delivered to `/api/v1/forms/options/languages`;
- bootstrap form/profile-form summaries delivered the overridden Kannada label;
- cleanup deactivated smoke overrides after verification;
- admin localization API smoke still passed.
