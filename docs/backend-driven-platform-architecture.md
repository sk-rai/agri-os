# Backend-driven platform architecture checkpoint

Status: Phase 0B architecture checkpoint  
Scope: planning document only; no runtime behavior change  
Date: 2026-07-14

## Why this checkpoint exists

Agri-OS started with Android-led farmer onboarding and crop-cycle execution, then evolved into a backend-driven crop workflow and admin configuration platform. The workflow side is now substantially more modular: crop taxonomy, workflow template versions, draft editing, CSV import/export, project assignments, permissions, audit, readiness checks, and catalog governance are all moving in the right direction.

The next platform step is to bring farmer profile, land parcel, soil profile, media capture, communication, and operating hierarchy into the same backend-driven model. This document records the intended architecture before implementation starts, so future changes remain additive and do not break tested Android crop-cycle flows.

See also: [Backend-driven profile form contracts](profile-form-contracts.md) for the current farmer/parcel/soil form rendering contract and rollout semantics.
See also: [Runtime app configuration and white-labelling contract](runtime-app-config-and-whitelabel.md) for bootstrap, branding, locale, unit, module, and feature-flag semantics.
See also: [Media, communication, and field-event foundation](media-communication-field-events-foundation.md) for the next evidence/advisory/query/event module family.

## Current backend foundation

The backend already has useful primitives:

- `Tenant` and `Project` for multi-tenant/project scoping.
- `ProjectRole` for project-level user access.
- `Farmer`, `Parcel`, and `SoilProfile` operational records.
- Profile hydration endpoints for Android after login:
  - `GET /api/v1/farmers/by-mobile/{mobile}`
  - `GET /api/v1/farmers/me/profile`
- Mobile sync materialization for:
  - `FARMER`
  - `PARCEL`
  - `PARCEL_GEOMETRY`
- Parcel geometry update endpoint:
  - `PATCH /api/v1/parcels/{parcel_id}/geometry`
- Dynamic form API:
  - `GET /api/v1/forms/{form_id}`
- Crop workflow platform:
  - versioned templates
  - draft/edit/publish/rollback
  - project assignment
  - override/audit/history
  - CSV lifecycle
  - readiness dashboard
- Master data/admin platform:
  - crop taxonomy/catalog imports
  - propagation imports
  - input/product catalog governance
  - permissions and viewer/read-only safeguards

This is enough to evolve safely without throwing away current Android work.

## Strategic product modes

The platform must support two enrollment paths.

### 1. Project-led enrollment

Used by FPOs, input companies, insurance companies, NGOs, processors, and enterprise programs.

Typical flow:

1. Tenant/client is provisioned.
2. Admin creates project.
3. Admin configures enabled crops, workflows, forms, inputs, products, and geographies.
4. Farmers are bulk enrolled through web/import or assisted enrollment by field agents.
5. Farmers, dealers, field agents, and agronomists use Android.
6. Managers and admins use web.

### 2. Direct farmer self-registration

Used by farmers installing the Android app directly from Play Store.

Typical flow:

1. Farmer verifies mobile number.
2. Android hydrates existing profile if present.
3. If no profile exists, farmer self-registers.
4. Farmer starts with a default/free/self-service tenant/project context.
5. Farmer may later be attached to a project, dealer, FPO, input company, or advisory program.

The data model must not assume every farmer belongs to exactly one project from day one.

## Core architectural principles

1. Backend is source of truth for structure.
   Android and web should render configured forms/workflows rather than owning business structure.

2. Runtime configuration, not app rebuilds.
   White-labelling, modules, language, units, crops, and project behavior should be configurable without producing a different Android APK for every client.

3. Additive migrations.
   Existing tested crop-cycle and hydration contracts should keep working while new contracts are introduced.

4. Generic primitives before feature-specific tables.
   Media, forms, assignments, audit, localization, and communication should be reusable across modules.

5. India-first, global-ready.
   India-specific fields are allowed as configured modules, not as permanent platform assumptions.

6. Offline-first compatible.
   Android must be able to capture forms, media references, field events, and messages offline, then sync later.

7. Read-only/viewer mode matters.
   Web users may have view-only access to project data, workflow configuration, farmer data, analytics, or audit views.

## Key gaps in current architecture

### Farmer/project relationship

Current farmer records contain a single `project_id`. Long term, this is too restrictive.

Needed:

- farmer identity/profile independent of project membership
- farmer-to-project enrollment records
- status per project enrollment
- enrollment source and method
- assigned dealer/field agent/agronomist

### Country and localization assumptions

Current implementation contains India-specific assumptions:

- `+91` mobile normalization
- Aadhaar field
- INR default currency
- land units like `BIGHA`, `BISWA`, `KATHA`, `GUNTHA`
- Soil Health Card terminology
- UP soil inference defaults
- Hindi labels in some forms

These should become country/tenant/project configuration, not removed immediately.

### Backend-driven forms

Dynamic forms exist but are currently limited and static. Farmer/parcel/soil forms are not yet fully backend-driven.

Needed form families:

- farmer registration
- farmer profile update
- parcel registration
- parcel geometry capture
- soil profile
- crop-cycle create
- activity log
- crop-stage evidence
- field event report
- farmer query
- yield/harvest/economics capture

### White-labelling

No complete runtime branding contract exists yet.

Needed:

- tenant/project logo
- app display name or project name
- color palette
- language defaults
- module enablement
- support links/contact
- project-specific landing/home behavior

### Organization hierarchy

Current `ProjectRole` is useful but flat.

Needed:

- head office
- regional office
- branch/dealer
- agronomist
- field agent
- farmer
- territory/geography/project scopes
- multiple reporting structures where required

### Media and evidence

No shared media attachment primitive exists yet.

Needed:

- photo
- audio
- video
- document
- stage evidence
- activity evidence
- soil report attachment
- parcel/geometry proof
- advisory attachment
- farmer query attachment

### Communication

Broadcast and two-way farmer communication are not yet modeled.

Needed:

- advisory/broadcast campaigns
- target audience rules
- delivery/read status
- two-way query threads
- text, photo, audio, document messages
- assignment/escalation to agronomist/company representative

### Field event reporting

Ground-level event reporting is not yet modeled.

Needed events include:

- rainfall
- pest
- disease
- hailstorm
- locust
- flood
- drought stress
- thunderstorm/wind
- crop damage

Each report should support severity, crop stage, parcel, GPS, media, notes, source, and external API linkage.

### Economics and analytics

Costs are captured through activities, but there is not yet a full economics layer.

Needed:

- stage-wise cost summary
- crop-cycle cost summary
- yield and revenue capture
- gross margin/profit/loss
- parcel comparison
- yield difference analysis
- project/client analytics

## Proposed target modules

### 1. App configuration and white-label module

Purpose: tell Android/web what tenant/project experience to render.

Candidate endpoint:

`GET /api/v1/app-config/bootstrap`

Candidate response areas:

- tenant
- project context
- branding
- enabled modules
- country/locale
- supported languages
- units/currency
- form versions
- workflow catalog versions
- feature flags
- support/contact links

This should be read-only first and can initially read from existing `Tenant.config` and `Project.config`.

### 2. Enrollment and membership module

Purpose: decouple farmer identity from project participation.

Candidate records:

- `FarmerIdentity` or keep current `Farmer` as identity/profile
- `FarmerProjectEnrollment`
- `FarmerAssignment`
- `EnrollmentBatch`
- `EnrollmentSource`

Candidate enrollment methods:

- `SELF`
- `ASSISTED`
- `BULK_IMPORT`
- `WEB_ADMIN`
- `PROJECT_INVITE`
- `SYNC_MATERIALIZED`

### 3. Organization hierarchy module

Purpose: model client operating structure.

Candidate records:

- `OrganizationUnit`
- `OrganizationUnitAssignment`
- `UserOrgAssignment`
- `FarmerOrgAssignment`

Candidate unit types:

- `HEAD_OFFICE`
- `REGION`
- `BRANCH`
- `DEALER`
- `FPO`
- `FIELD_TEAM`
- `CUSTOM`

### 4. Versioned form template module

Purpose: make farmer/parcel/soil/profile/event/query forms backend-driven.

Candidate records:

- `FormTemplate`
- `FormTemplateVersion`
- `FormField`
- `FormAssignment`
- `FormSubmission`

Initial implementation can remain static JSON/Python schemas, then migrate to DB-backed templates later.

### 5. Localization and country configuration module

Purpose: support India now and other countries later.

Candidate records:

- `CountryConfig`
- `LanguageConfig`
- `UnitCatalog`
- `CurrencyConfig`
- `TranslationBundle`
- `GeoLevelConfig`

This should not block current India-first behavior.

### 6. Media asset module

Purpose: one upload/attachment system for all modules.

Candidate records:

- `MediaAsset`
- `MediaAttachment`

Candidate attachment targets:

- farmer profile
- parcel
- soil profile
- crop cycle
- crop stage
- activity log
- field event
- advisory
- query thread/message

### 7. Broadcast/advisory module

Purpose: push advisory content to farmers/field users.

Candidate records:

- `AdvisoryCampaign`
- `AdvisoryAudienceRule`
- `AdvisoryMessage`
- `AdvisoryDelivery`

Targeting dimensions:

- tenant/project
- farmer
- parcel
- crop
- crop stage
- geography
- organization unit
- language

### 8. Farmer query and conversation module

Purpose: two-way farmer/company/agronomist communication.

Candidate records:

- `QueryThread`
- `QueryMessage`
- `QueryAssignment`
- `QueryStatusHistory`

Message types:

- text
- photo
- audio
- document
- system update

### 9. Field event reporting module

Purpose: capture ground-level events from Android and external APIs.

Candidate records:

- `FieldEventType`
- `FieldEventReport`
- `FieldEventAttachment`

Sources:

- farmer
- field agent
- agronomist
- external weather API
- IoT device later

### 10. Economics and analytics module

Purpose: convert activity data into useful financial and operational insights.

Candidate first endpoints:

- crop-cycle cost summary
- stage-wise cost summary
- parcel economics summary
- farmer season summary

Later:

- yield analysis
- input ROI
- project-level performance
- statistical comparison across parcels/cohorts

## Safe implementation roadmap

### Phase 1: Bootstrap app configuration

Add read-only app/project config endpoint.

Tests:

- default tenant config returns stable schema
- project override merges safely
- anonymous/self-service context behaves predictably
- missing project handled clearly

Android impact:

- call bootstrap after login
- use feature flags/branding if present
- fallback to current defaults if absent

### Phase 2: Enrollment membership foundation

Add project enrollment records without removing current `Farmer.project_id`.

Tests:

- direct farmer can exist without project
- project enrollment can be created
- hydration returns memberships
- existing farmer hydration remains unchanged

Android impact:

- store memberships if present
- choose active project context when needed

### Phase 3: Backend-driven farmer/parcel/soil forms

Expose schemas for farmer, parcel, and soil forms.

Tests:

- each schema returns stable version
- fields include labels, type, required, validation, dependencies
- Android-compatible field names
- country/tenant defaults are included

Android impact:

- render these schemas behind feature flag
- keep existing native screens as fallback

### Phase 4: Shared media foundation

Add generic media asset/attachment APIs.

Tests:

- create upload intent or local asset record
- attach media to supported targets
- hydration includes media references where needed
- permission checks by tenant/project

Android impact:

- generic offline media queue
- photos/audio use same attachment flow

### Phase 5: Communication and advisories

Add read-first broadcast and query primitives.

Tests:

- advisory list filtered by project/farmer/crop/stage
- query thread create/message add
- media attachments supported
- read-only users cannot mutate

Android impact:

- inbox/advisory screen
- query creation
- audio/photo attachments

### Phase 6: Field events

Add event reporting schema and sync.

Tests:

- event types configurable
- severity validation
- crop-cycle/stage/parcel linkage
- offline sync materialization

Android impact:

- generic event report form
- severity selector
- optional media/GPS/audio

### Phase 7: Economics summaries

Add computed summaries first, not complex analytics.

Tests:

- stage cost summary from activity logs
- crop-cycle cost summary
- harvest revenue/profit calculation
- zero/missing data behavior

Android impact:

- display stage/cycle cost cards
- avoid local calculations except temporary display fallback

## Android guidance during transition

Android should continue using the tested flows, but avoid adding more hardcoded business structure.

Recommended now:

- Keep existing farmer/parcel/soil screens stable.
- Keep current crop-cycle/activity flows stable.
- Prepare DynamicFormRenderer for farmer/parcel/soil/event/query forms.
- Treat backend schema as optional until feature flag is enabled.
- Preserve backend IDs and local IDs carefully.
- Keep GPS widgets generic.
- Add no client-specific branding assumptions.
- Prepare for generic media attachments, including audio.
- Prepare for project context/membership in local Room.

## Web/admin guidance during transition

Admin UI should remain conservative:

- read-only preview before edit
- audit every configuration change
- block unsafe project edits after enrollment/crop cycles
- keep viewer mode stable
- prefer CSV/import lifecycles before complex visual editors
- add visual builders after contracts are stable

## Near-term priority order

1. App bootstrap/white-label read-only endpoint.
2. Enrollment membership model.
3. Backend-driven farmer/parcel/soil form schemas.
4. Android feature-flagged schema rendering for enrollment/profile.
5. Shared media asset/attachment foundation.
6. Stage evidence photos.
7. Farmer query/audio/photo messaging.
8. Advisory/broadcast module.
9. Field event reporting.
10. Economics summaries.

## Non-goals for the immediate next phase

These are important, but should not be implemented first:

- full visual form builder
- full visual org-chart editor
- external web crawling/product-price automation
- IoT control layer
- advanced statistical analytics
- replacing all existing India-specific fields
- breaking current Android profile/crop-cycle flows

## Decision summary

The platform should move toward a backend-configured operating system for agriculture, not a collection of hardcoded app screens. The correct next technical move is not a large rewrite. It is a set of additive contracts:

1. bootstrap configuration
2. enrollment memberships
3. backend-driven profile/parcel/soil forms
4. shared media
5. communication/event/economics modules

This keeps the tested crop-cycle MVP safe while opening the path for multi-tenant, white-labelled, international, analytics-ready Agri-OS deployments.

## Future scope: trusted-corpus advisory generation

The broadcast/advisory system should remain compatible with a future offline or low-cost LLM advisory generator for independently enrolled farmers who are not receiving company/FPO/agronomist advisories. This is future scope only and does not change current runtime behavior.

Design intent:

- Treat the model as an advisory author/source, not as an unbounded chatbot.
- Restrict generation to a trusted, curated agronomy corpus plus structured platform context such as crop, stage, parcel, soil, weather, field events, geography, and input history.
- Prefer offline/on-premise or cheap-to-run models where the client explicitly agrees to invest in fine-tuning, GPU/CPU hosting, monitoring, and content governance.
- Store generated advisories as draft or reviewable broadcast/advisory campaigns before farmer delivery, unless a future tenant explicitly enables automatic publishing.
- Preserve auditability: model version, corpus version, prompt/template version, source facts, confidence/risk flags, and human approval status should be recorded.
- Keep it tenant/project configurable: enterprise clients may disable it, require human approval, or limit it to direct/self-service farmers.
- Make safety explicit: never silently replace regulated agronomist advice, pesticide dosage rules, insurance decisions, or emergency alerts without a configured approval policy.

This future capability should plug into the existing broadcast primitives: campaign, localized content, media attachments, audience rules, delivery rows, read/ack state, and audit history.

### Company/customer profile

Agri-OS now keeps a backend-only tenant-scoped company profile for the organization using the product, separate from farmer, agent, project, and Android profile data. This profile stores legal/display names, organization type, registration identifiers, support contacts, head-office details, operating geography, crop focus, service model, and backend configuration. Use `GET /api/v1/tenants/{tenant_id}/company-profile` and `PUT /api/v1/tenants/{tenant_id}/company-profile`; Android MVP does not need to render or mutate it.

### Company profile prepopulation

Company profiles are now ready for future metadata seeding from public directories, government registries, partner lists, or bulk imports. Seeded records should use `profile_source`, `verification_status`, and `source_references[]`; when a company later enrolls, admins can claim/edit the existing profile and every change is recorded in `GET /api/v1/tenants/{tenant_id}/company-profile/audit`.

### Company discovery candidates

Future company prepopulation should land first in `company_discovery_candidates`, not directly in live tenant/company profiles. Use `POST /api/v1/company-discovery-candidates` for public-web, government-registry, partner-directory, or bulk-import discoveries; `GET /api/v1/company-discovery-candidates` for review queues; and `PATCH /api/v1/company-discovery-candidates/{candidate_id}/review` to mark records approved, rejected, duplicate, merged, stale, or linked to an existing tenant/profile.

## Platform readiness checkpoint - 2026-07-20

Agri-OS now has backend-owned foundations for farmer/agent profiles, land/parcel profiles, soil profiles, weather/broadcast advisories, soil enrichment snapshots/queues, company/customer profiles, and company discovery/prepopulation staging.

Current backend readiness for Android MVP handoff is estimated at **about 94%**. The strongest remaining gaps are automated provider workers, final Android consumption, production permission/audit hardening, and final handoff payload examples.

Weather operations health is now implemented in backend and admin web: `GET /api/v1/weather/operations/health` and admin `/weather` show provider due/overdue/failure status plus fresh/stale/expired snapshot counts.

Soil enrichment operations health is now surfaced through backend and admin web, raising Android MVP backend readiness to approximately **94%**. Remaining gaps are primarily automated provider workers, final Android integration, production permission/audit review, and final payload handoff packaging.

See `docs/android-backend-handoff-packet.md` for the living Android/backend handoff packet and backend closeout checklist.

Operational recovery guidance is maintained in `docs/backend-recovery-playbook.md`, including Git rollback, migration backup/rollback, provider worker recovery, permission hardening checks, and Android handoff checkpointing.

## Backend metadata readiness roadmap

See `docs/backend-metadata-readiness-roadmap.md` for the pre-Android metadata and scenario-readiness plan covering all-India geography, crop scenario packs, configurable seasons/local units, input/provider prepopulation, branching crop workflows, perennial/orchard onboarding, stage cost/P&L summaries, advisory seed content, multimedia broadcasts, and web UI screenshot testing.

Metadata readiness current-state checkpoint
The repository now includes `docs/backend-metadata-readiness-current-state.md`, summarizing the first metadata audit baseline: crops/workflows are already rich enough for Android MVP testing, while all-India geography expansion and agricultural product seeding remain the next backend metadata priorities.

## Metadata governance rule

All metadata mutations must be admin/backoffice controlled and audit logged. This applies to geography aliases/imports, crop taxonomy, crop seasons, local unit conversions, input/product catalog rows, workflow templates, advisory seed content, and broadcast templates. The preferred mutation model is append/update/expire rather than physical delete: rows should keep `created_at`, `updated_at`, actor metadata, reason, and where relevant `effective_from`, `expires_at`, `status`, or `is_active`. Runtime consumers should decide visibility/validity from status plus effective/expiry windows. Physical deletion should be reserved for failed imports, temporary staging rows, or explicit maintenance tasks with audit trail.

## Geography canonical-data guardrail

Geography records sourced from Local Government Directory, Census, or other government reference datasets must be treated as canonical reference data. Admin UI/API edits must not allow changing LGD codes, government names, hierarchy parentage, or other canonical fields in a way that contradicts the source dataset. Allowed admin actions should be limited to adding local aliases, display labels, translations, PIN-code associations, operational grouping, temporary deactivation/expiry, or import-batch corrections with source evidence. Corrections to canonical geography should flow through a verified import/versioning process with source URL/file, import batch ID, actor, timestamp, and reason. Runtime Android search should use canonical records plus approved aliases, while preserving the government-backed identifiers for audit and interoperability.
