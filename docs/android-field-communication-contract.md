\# Android Field Communication + Media Contract



This document captures the current backend contract for Android field intelligence, farmer communication, media attachments, and future broadcast/advisory targeting.



\## Implemented foundations



Current backend/admin support includes:



\- shared media asset metadata;

\- media attachments linked to operational entities;

\- field event reporting API;

\- field event sync materialization;

\- query thread direct APIs;

\- query message direct APIs;

\- Query Inbox admin UI;

\- query reply, assign, answer, close actions;

\- query action audit trail;

\- query thread/message sync materialization;

\- dashboard visibility for field events and query workload.



\## Media model



Media is metadata-first for now. Actual binary/object upload can be added behind this stable contract.



Supported media types:



\- PHOTO

\- AUDIO

\- VIDEO

\- DOCUMENT



Common attachment purposes:



\- GENERAL

\- ACTIVITY\_PHOTO

\- FIELD\_EVENT\_PHOTO

\- AUDIO\_NOTE

\- QUERY\_ATTACHMENT

\- EVIDENCE

\- BEFORE\_AFTER



Media attachments can link media assets to:



\- FIELD\_EVENT

\- QUERY\_MESSAGE

\- ACTIVITY\_LOG

\- PARCEL

\- FARMER

\- CROP\_CYCLE\_STAGE



Android should preserve local UUIDs wherever possible.



\## Field event sync



Supported sync entity types:



\- FIELD\_EVENT\_REPORT

\- FIELD\_EVENT



Important fields:



\- id

\- project\_id

\- farmer\_id

\- parcel\_id

\- crop\_cycle\_id

\- stage\_code

\- event\_type

\- severity

\- event\_date

\- reported\_at

\- lat/lng

\- accuracy\_meters

\- description

\- source

\- status

\- metadata

\- media\_attachments



Supported event types currently include:



\- RAIN

\- PEST

\- DISEASE

\- HAILSTORM

\- LOCUST

\- FLOOD

\- DROUGHT\_STRESS

\- THUNDERSTORM\_WIND

\- HEAT\_STRESS

\- COLD\_STRESS

\- IRRIGATION\_FAILURE

\- OTHER



Supported severity values:



\- LOW

\- MEDIUM

\- HIGH

\- CRITICAL



\## Query threads and messages



Supported direct APIs:



\- POST /api/v1/query-threads

\- GET /api/v1/query-threads

\- GET /api/v1/query-threads/{thread\_id}

\- POST /api/v1/query-threads/{thread\_id}/messages

\- PATCH /api/v1/query-threads/{thread\_id}/status



Supported sync entity types:



\- QUERY\_THREAD

\- QUERY\_MESSAGE



Query thread fields:



\- id

\- project\_id

\- farmer\_id

\- parcel\_id

\- crop\_cycle\_id

\- stage\_code

\- subject

\- category

\- priority

\- status

\- metadata



Query message fields:



\- id

\- thread\_id

\- sender\_type

\- sender\_id

\- message\_type

\- body\_text

\- metadata

\- media\_attachments



Supported categories:



\- CROP\_HEALTH

\- INPUT\_USAGE

\- IRRIGATION

\- MARKET

\- INSURANCE

\- TECH\_SUPPORT

\- OTHER



Supported priorities:



\- LOW

\- MEDIUM

\- HIGH

\- URGENT



Supported statuses:



\- OPEN

\- ASSIGNED

\- ANSWERED

\- CLOSED



Supported sender types:



\- FARMER

\- FIELD\_AGENT

\- AGRONOMIST

\- ADMIN

\- SYSTEM



Supported message types:



\- TEXT

\- AUDIO

\- PHOTO

\- DOCUMENT

\- SYSTEM



\## Offline sync guidance



Android should send dependency-ordered events where possible:



1\. Media asset metadata

2\. Query thread or field event

3\. Query message

4\. Media attachments embedded in event/message payload



Rules:



\- QUERY\_MESSAGE must reference an existing QUERY\_THREAD.

\- Android should preserve local UUIDs as backend IDs.

\- Media attachments should reference already-created media\_asset\_id.

\- Agronomist/admin/field-agent replies can move a thread from OPEN to ANSWERED.

\- Field event media attachments may be included in the same sync payload.



\## Admin visibility



Admin currently sees:



\- Field Events page;

\- Query Inbox;

\- query messages;

\- query media attachments;

\- query audit history;

\- dashboard field event counts;

\- dashboard query workload counts.



Query audit includes:



\- thread creation;

\- direct replies;

\- synced messages;

\- status changes;

\- assignment/close reason;

\- before/after snapshots where applicable.

\## Broadcast/advisory Android contract



The broadcast/advisory module supports backend-authored multimedia advisories targeted to farmers through generated delivery rows.



Current Android-facing endpoint:



```text

GET /api/v1/broadcasts/farmers/{farmer\_id}/broadcasts?language\_code=hi\&include\_read=true



\## Future broadcast/advisory targeting



The broadcast/advisory system should support both generic and targeted communication.



Broadcast modes:



\- generic/open-for-all;

\- tenant/company-specific;

\- project-specific;

\- farmer-list-specific;

\- crop-specific;

\- crop-stage-specific;

\- geography-specific;

\- weather/event-specific;

\- input/product-specific;

\- role-specific;

\- language-specific;

\- urgent/emergency alerts.



Examples:



\- Send to all farmers.

\- Send only to farmers in a project.

\- Send only to rice farmers in flowering stage.

\- Send only to farmers in selected villages/districts.

\- Send only to farmers who reported pest events.

\- Send to farmers using or recommended Product X.

\- Send to field agents in Region Y.

\- Send Kannada content to Karnataka farmers and Hindi content to UP farmers.



Future backend concepts:



\- broadcast\_campaign

\- broadcast\_audience\_rule

\- broadcast\_content

\- broadcast\_delivery

\- delivery/read/acknowledgement status

\- offline sync for advisory delivery

\- multimedia attachments

\- deeplinks into crop cycle, recommendation, event, or query screens



This should be designed as a configurable targeting engine, not a hardcoded notification feature.

## Current broadcast/advisory implementation status

Broadcasts are now a backend-driven advisory/in-app communication foundation. Android should treat the backend as the source of truth for campaigns, localized content, delivery status, read state, and acknowledgements.

Implemented backend entities:

- `broadcast_campaigns`
- `broadcast_contents`
- `broadcast_audience_rules`
- `broadcast_deliveries`
- `broadcast_audit_events`

Implemented admin/backend flow:

1. Admin creates a DRAFT broadcast campaign.
2. Admin adds localized content rows and audience rules.
3. Admin can preview estimated audience before sending.
4. Admin publishes the campaign.
5. Admin generates delivery rows.
6. Admin can expire or cancel a campaign while preserving delivery/audit history.
7. Android fetches farmer-specific broadcast feed.
8. Android marks a delivery read when the farmer opens it.
9. Android can acknowledge a delivery when explicit acknowledgement is required.
10. Admin can inspect delivery rows and audit history.

Implemented targeting rules for delivery expansion:

- `ALL`: all active farmers in the tenant.
- `FARMER`: explicit farmer IDs.
- `PROJECT`: active farmers in selected project IDs.
- `CROP`: farmers with ACTIVE crop cycles for selected crop codes.
- `STAGE`: farmers with ACTIVE crop cycles that have ACTIVE stage instances for selected stage codes.
- `LOCATION`: farmers/parcels whose manual village name or village UUID matches the configured values. District/state/climatic-zone expansion is still future work.
- `LANGUAGE`: active farmers whose `language_preference` matches selected language codes.
- `WEATHER`: farmers matched through latest non-expired backend weather snapshots whose `condition_code` or `risk_flags` match the configured values. Initial expansion supports tenant/project/farmer/parcel/village-scoped snapshots.

Current rule-combination behavior is controlled by campaign metadata `audience_match_mode`: `ANY` is the default inclusive/union mode where a farmer matching any supported rule can receive a generated delivery; `ALL` is intersection mode where the farmer must match every supported rule. Android only consumes generated delivery rows and does not need to re-evaluate targeting rules locally.

Accepted but not yet expanded into delivery recipients:

- `ROLE`
- `FIELD_EVENT`
- `INPUT`
- `PRODUCT`

Backend preview reports unsupported rules through `unsupported_rule_count` and per-rule `supported=false` so admin can see what will and will not be delivered before generation.

### Backend weather snapshot foundation

Weather is backend-owned and snapshot-based. Android should not call weather providers directly and should not decide broadcast targeting from local phone sensors. The backend stores provider configuration and normalized weather snapshots, then broadcast targeting can consume those stored snapshots.

Current backend foundation:

- `weather_provider_configs`: tenant/provider configuration, including `refresh_interval_hours` defaulting to 6 hours and customizable per provider.
- `weather_snapshots`: normalized observations/forecasts for a location scope such as `VILLAGE`, `PINCODE`, `PARCEL`, `PROJECT`, `GEOPOINT`, or future weather grid.
- Snapshot freshness is represented by `fetched_at`, `forecast_valid_from`, `forecast_valid_to`, and `expires_at`.
- Risk flags such as `HEAVY_RAIN_NEXT_24H` and normalized fields like rainfall probability, rainfall mm, temperature, humidity, and wind are stored with the raw provider payload for auditability.
- Backend refresh orchestration is provider-driven and cadence-based; see `docs/weather-provider-adapter-contract.md` for provider adapter rules and Open-Meteo sample config:
  - `GET /api/v1/weather/providers/refresh-plan` returns enabled providers, due state, hours until due, and last refresh status/message.
  - `POST /api/v1/weather/providers/run-due?dry_run=true` previews due providers for scheduler/admin operations.
  - `POST /api/v1/weather/providers/run-due` runs due backend adapters and stores normalized snapshots.
  - `POST /api/v1/weather/providers/{provider_id}/refresh` records a refresh attempt and can persist normalized snapshots supplied by a scheduler/provider adapter.
  - Real provider integrations can run every `refresh_interval_hours` (default 6) and write snapshots through the same contract.
  - Android does not participate in refresh scheduling; it only receives resulting broadcasts/feed data.

Android role:

- provide/confirm farmer, parcel, and optional GPS context when permitted;
- display weather-triggered broadcasts delivered by backend;
- allow farmer/agent field evidence reports when actual conditions differ;
- do not re-fetch weather APIs or locally re-evaluate weather broadcast rules.

### Admin broadcast APIs

Admin-side APIs currently available:

```http
POST /api/v1/broadcasts
POST /api/v1/broadcasts/{campaign_id}/contents
POST /api/v1/broadcasts/{campaign_id}/audience-rules
POST /api/v1/broadcasts/{campaign_id}/publish
POST /api/v1/broadcasts/{campaign_id}/expire
POST /api/v1/broadcasts/{campaign_id}/cancel
GET  /api/v1/broadcasts/{campaign_id}/audience-preview
POST /api/v1/broadcasts/{campaign_id}/generate-deliveries
GET  /api/v1/broadcasts/{campaign_id}/deliveries?status=PENDING
GET  /api/v1/broadcasts/{campaign_id}/audit
```

Android should not use the admin creation/edit/publish/generate endpoints. Draft editing endpoints are admin-only and currently allow adding localized content rows and audience rules while the campaign is still DRAFT. Published/expired/cancelled campaigns reject draft edits.

### Android farmer broadcast feed

Android should fetch farmer-visible broadcasts after profile hydration/login and periodically during sync:

```http
GET /api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code=hi&include_read=true&limit=100
```

The backend farmer feed only returns campaigns that are currently visible to the farmer:

- campaign status must be `PUBLISHED`;
- `starts_at` must be null or in the past;
- `expires_at` must be null or in the future;
- `DRAFT`, `EXPIRED`, `CANCELLED`, future-scheduled, and inactive campaigns are excluded from the normal farmer inbox.

Response shape:

```json
{
  "schema_version": "farmer_broadcasts.v1",
  "tenant_id": "default",
  "farmer_id": "...",
  "filters": {
    "language_code": "hi",
    "include_read": true,
    "limit": 100
  },
  "count": 1,
  "broadcasts": [
    {
      "campaign": {
        "id": "...",
        "title": "Weather alert draft",
        "category": "WEATHER",
        "priority": "URGENT",
        "status": "PUBLISHED",
        "starts_at": "2026-07-16T22:21:56+05:30",
        "expires_at": null,
        "metadata": {
          "targeting_mode": "RULE_BASED"
        }
      },
      "content": {
        "id": "...",
        "language_code": "hi",
        "title": "Weather alert Hindi",
        "body_text": "Heavy rainfall expected.",
        "cta_label": null,
        "deeplink_url": null,
        "metadata": {},
        "media_attachments": [
          {
            "id": "...",
            "media_type": "PHOTO",
            "mime_type": "image/jpeg",
            "storage_url": "https://...",
            "thumbnail_url": "https://...",
            "duration_seconds": null,
            "upload_status": "UPLOADED",
            "attachment": {
              "purpose": "ADVISORY_ATTACHMENT",
              "caption": "Rice pest reference image",
              "display_order": 1,
              "is_primary": true
            }
          }
        ]
      },
      "delivery": {
        "id": "...",
        "farmer_id": "...",
        "delivery_status": "PENDING",
        "delivered_at": null,
        "read_at": null,
        "acknowledged_at": null,
        "metadata": {
          "generation_rule": "BASIC_AUDIENCE_RULES"
        }
      }
    }
  ]
}
```

Android rendering guidance:

- Show unread/PENDING broadcasts in a notification/inbox/advisory area.
- Do not show EXPIRED or CANCELLED campaigns in the normal farmer inbox unless a future archival/history view is explicitly added.
- Use `content.language_code` selected by backend fallback: requested language first, then English, then first available content.
- Use `campaign.priority` for visual severity:
  - `URGENT`: prominent alert.
  - `HIGH`: highlighted advisory.
  - `NORMAL`/`LOW`: standard inbox item.
- Use `campaign.category` for grouping: WEATHER, ADVISORY, MARKET, INPUT, EMERGENCY, GENERAL.
- Use `content.deeplink_url` when present to navigate to a crop cycle, recommendation, query, field event, or external detail screen.
- Render `content.media_attachments[]` when present:
  - `PHOTO`: inline image/card using `thumbnail_url` first, then `storage_url`.
  - `AUDIO`: voice-note/audio player using `storage_url`; show `duration_seconds` if present.
  - `DOCUMENT`: open/download action using `storage_url` or future signed URL support.
  - `VIDEO`: future-compatible; show as playable media only when Android supports it.
- Use `attachment.caption`, `display_order`, and `is_primary` for ordering and display emphasis.
- Cache media metadata with the broadcast delivery; binary/offline media caching can be added later behind the same fields.
- Persist `delivery.id` locally so read/ack sync is idempotent.

### Weather-targeted broadcast semantics

Weather-targeted broadcasts use the same farmer broadcast feed and delivery/read/ack endpoints as other campaigns. Android does not need a separate weather inbox.

Admin/backend can add audience rules such as:

```json
{
  "rule_type": "WEATHER",
  "operator": "IN",
  "values": ["HEAVY_RAIN_NEXT_24H", "FUNGAL_DISEASE_RISK"]
}
```

The backend expands `WEATHER` rules from current, non-expired weather snapshots. Snapshot `condition_code` and `risk_flags[]` are matched against the rule values, then recipients are resolved from snapshot scope: `TENANT`, `PROJECT`, `FARMER`, `PARCEL`, or `VILLAGE`. Android should simply render delivered broadcasts; targeting evidence is available to admin preview screens, not required on-device for MVP.

Admin Weather operations can create a DRAFT weather broadcast directly from a snapshot. The draft still follows the normal review flow: preview audience, publish, generate deliveries, then Android receives it through the farmer broadcast feed.

### Android read and acknowledge endpoints

When a farmer opens a broadcast detail, Android should call:

```http
POST /api/v1/broadcasts/deliveries/{delivery_id}/read
```

This sets:

- `delivered_at` if missing
- `read_at` if missing
- `delivery_status=DELIVERED` if previously PENDING

If the broadcast requires explicit acknowledgement, Android should show an acknowledgement button and call:

```http
POST /api/v1/broadcasts/deliveries/{delivery_id}/acknowledge
```

This sets:

- `delivered_at` if missing
- `read_at` if missing
- `acknowledged_at` if missing
- `delivery_status=ACKNOWLEDGED`

For MVP, acknowledgement requirement can be inferred from campaign/content metadata if present, for example:

```json
{
  "requires_acknowledgement": true
}
```

If metadata is absent, Android should treat acknowledgement as optional/not required.

### Broadcast retry semantics

Admin can retry undelivered broadcast rows through:

POST /api/v1/broadcasts/{campaign_id}/retry-undelivered

Current retry policy:

- Retry applies to PENDING and FAILED delivery rows.
- DELIVERED and ACKNOWLEDGED rows are skipped.
- Retry state is stored in delivery metadata:
  - retry_count
  - max_retries
  - last_retry_at
- After 3 retry attempts, the row is marked FAILED with failure_reason=MAX_RETRIES_EXCEEDED.
- Campaign metadata stores the last retry summary:
  - last_delivery_retry_at
  - last_delivery_retry_retried
  - last_delivery_retry_marked_failed
  - last_delivery_retry_skipped_acknowledged

For Android MVP, this is mainly an admin/backend delivery-attempt state. Android should render delivery_status=FAILED as not actionable unless a future UI explicitly allows farmer-side retry or support escalation.

### Offline sync guidance for broadcasts

Initial MVP can call read/ack endpoints directly when online. For offline support, Android should queue local read/ack events and replay them when online.

Recommended local event types:

- `BROADCAST_DELIVERY_READ`
- `BROADCAST_DELIVERY_ACKNOWLEDGED`

Minimum payload:

```json
{
  "delivery_id": "...",
  "campaign_id": "...",
  "farmer_id": "...",
  "read_at": "2026-07-16T16:51:56Z",
  "acknowledged_at": "2026-07-16T16:52:10Z"
}
```

A sync materializer for these event types is not yet implemented; Android can keep this as a future-compatible local queue while using direct endpoints when online.

### Broadcast audit/admin visibility

Admin can inspect:

- audience preview;
- generated delivery rows;
- delivery status by farmer;
- read/ack state;
- audit history.

Audit currently records:

- `CREATE_CAMPAIGN`
- `PUBLISH_CAMPAIGN`
- `GENERATE_DELIVERIES`
- `MARK_DELIVERY_READ`
- `ACKNOWLEDGE_DELIVERY`

This is important for client/company deployments because advisory delivery must be explainable: who sent what, when, to whom, and whether the farmer saw or acknowledged it.

## Backend-owned profile contract endpoint

Android should treat farmer, parcel, and soil profile schemas/options as backend-owned. Before rendering or caching profile forms, Android can fetch:

```http
GET /api/v1/forms/profile-contract?project_id={project_id}
```

The response uses `schema_version=profile_contract.v1` and summarizes:

- profile forms in scope: `farmer_registration`, `parcel_registration`, `soil_profile`;
- required and recommended fields by form;
- canonical backend field mappings plus explicit `payload_mappings`;
- option sets used by the forms, including source/version metadata;
- grouped Android screen hints under `android_handoff.screen_groups`;
- agent-assisted capture and dual farmer/agent mode hints;
- location model hints: normal parcel anchor is `parcel.pin_code`, with `parcel.location_scope` for multi-village/FPO/edge cases;
- offline cache/replay guidance;
- soil enrichment source hints for SoilGrids, SHC/SLUSI, Open-Meteo, and future satellite snapshots;
- `backend_owned_contract.android_should_hardcode_options=false`.

Android should still fetch full form schemas from `/api/v1/forms/{form_id}` and effective options from `/api/v1/forms/options/{option_set}`. This summary is intended as a lightweight bootstrap/readiness contract so Android can avoid hardcoding seasons, land units, ownership types, irrigation sources, soil textures/colors, soil data sources, languages, assistance modes, agent mode behavior, location semantics, or soil enrichment provider assumptions.



## Android post-login mode bootstrap

After OTP or device-key login, Android should call a single backend-owned bootstrap endpoint before choosing the first screen:

```http
GET /api/v1/auth/mode-bootstrap
Authorization: Bearer {access_token}
X-Tenant-ID: {tenant_id}
```

Response `schema_version=auth_mode_bootstrap.v1` returns the authenticated `user`, available `modes.farmer` and `modes.agent`, optional `farmer_profile`, optional `agent_profile`, `project_access`, `primary_project_id`, and endpoint hints.

Use `first_screen_hint` as the navigation decision:

- `FARMER_HOME`: open personal farmer home/profile flow.
- `AGENT_WORKLIST`: open assigned field-agent worklist.
- `MODE_CHOOSER`: user has both farmer and agent capability; show a mode switcher and remember last selected mode locally.

This prevents Android from inferring farmer/agent mode from scattered endpoints. A farmer can be both a personal farmer and an agent/agronomist/dealer when `modes.farmer.available=true` and `modes.agent.available=true`.

## Field-agent assignment and dual farmer/agent mode

A person can be both a normal farmer and an operational agent/agronomist/dealer. Backend represents this with a `User` login, optional `AgentProfile`, and optional linked `Farmer` profile. Android should use the field-agent worklist for assisted capture when operating in agent mode, and use the linked `personal_farmer_id` when the same person switches to personal farmer mode.

Assigned-farmer worklist:

```http
GET /api/v1/field-agent/worklist?project_id={project_id}&assigned_only=true
X-Actor-ID: {agent_user_id}
```

The response includes `agent_profile`, `mode_switch.personal_farmer_mode_available`, `mode_switch.personal_farmer_id`, farmer rows, parcels, soil profiles, active crop cycles/stages, capture actions, and backend endpoint hints for the relevant farmer/parcel/crop entities.

Android can request backend-filtered worklists instead of filtering readiness locally:

```http
GET /api/v1/field-agent/worklist?project_id={project_id}&assigned_only=true&action_code=ADD_SOIL_PROFILE
GET /api/v1/field-agent/worklist?project_id={project_id}&assigned_only=true&missing_field=parcel_location
GET /api/v1/farmers/profile-readiness?project_id={project_id}&section=land&section_status=PARTIAL
```

Supported filter keys are `action_code`, `missing_field`, `section`, and `section_status`; responses echo the active filters.

Backend/admin assignment helper:

```http
POST /api/v1/farmers/{farmer_id}/project-agent-assignment
```

Payload: `project_id`, `agent_user_id`, `action=ASSIGN|UNASSIGN`, and `reason`. The endpoint updates the farmer project enrollment `assigned_user_ids` and records assignment history in enrollment metadata. Android field apps normally consume this assignment through the worklist; admin/back-office tools can call the assignment helper.

## Soil enrichment source provenance

Android should treat soil baseline and soil-water data as backend-owned enrichment snapshots. Android should not call SoilGrids, Open-Meteo, SLUSI/SHC, or future satellite providers directly.

Summary endpoint for Android/admin:

    GET /api/v1/soil-profiles/enrichments/summary?farmer_id={farmer_id}
    GET /api/v1/soil-profiles/enrichments/summary?parcel_id={parcel_id}
    GET /api/v1/soil-profiles/enrichments/summary?farmer_id={farmer_id}&snapshot_type=MOISTURE

Response `schema_version=soil_enrichment_summary.v1` returns `snapshot_count`, `provider_counts`, `snapshot_type_counts`, `status_counts`, `has_baseline`, `has_moisture`, `has_slusi_or_shc`, `latest_by_type`, `latest_baseline`, `latest_moisture`, and `latest_slusi_or_shc`.

Use this endpoint for farmer/parcel profile screens and readiness explanations. Use raw snapshot list endpoints only for debug/drilldown screens.

Profile readiness also exposes source-specific fields: `has_soilgrids_baseline_snapshot`, `soilgrids_baseline_snapshot_count`, `has_shc_slusi_snapshot`, and `shc_slusi_snapshot_count`. Android should use them for labels, not for provider calls.

Backend/admin operational queue for enrichment jobs:

    GET /api/v1/soil-profiles/enrichments/queue?farmer_id={farmer_id}
    GET /api/v1/soil-profiles/enrichments/queue?project_id={project_id}&missing=ANY

Response `schema_version=soil_enrichment_queue.v1` returns location-ready parcels, snapshot counts, missing baseline/moisture flags, reason counts, recommended backend jobs such as `FETCH_SOIL_BASELINE` or `FETCH_SOIL_MOISTURE`, and `latest_audit_by_job` for the most recent attempt status/error per recommended job. Android MVP can treat this as admin/backend-only; future admin or agent screens may surface it as an enrichment work queue.

Backend workers/admin tools can record enrichment attempt status:

    POST /api/v1/soil-profiles/enrichments/jobs/audit
    GET /api/v1/soil-profiles/enrichments/jobs/audit?farmer_id={farmer_id}&status=FAILED

Audit payloads use `schema_version=soil_enrichment_job_audit.v1` for listing and include `job_type`, `provider`, `status`, `attempt_count`, `reason`, `error_code`, and `metadata`. This is backend/admin operational state; Android MVP should not call provider APIs directly.

Admin web exposes a read-only soil enrichment queue plus manual audit actions for recommended jobs. Admins can mark a job `SKIPPED`, `DEFERRED`, or `FAILED`; this writes an audit event and refreshes `latest_audit_by_job` on the queue response.

The backend now exposes the source contract:

```http
GET /api/v1/soil-profiles/enrichments/source-contract
```

Current source families:

- `SOILGRIDS`: automated open-source baseline by lat/lon/grid cell.
- `OPEN_METEO`: backend weather/soil-moisture snapshot source.
- `SHC_SLUSI`: Government Soil Health Card / SLUSI visual-layer baseline. Use as manual/admin capture or future CSV/import source until an official raw API/export is identified. Do not scrape the map UI by default.
- `IN_HOUSE_SATELLITE`: future Agri-OS satellite/model-derived enrichment.

Every stored enrichment snapshot includes provenance metadata such as `provider_family`, `source_granularity`, `automation_mode`, `provider_key`, and `provenance_contract=soil_enrichment_sources.v1`. Android should render these snapshots as informational/backend-provided evidence and should not call external soil/weather providers directly.

For SHC/SLUSI, the public visualisation has been observed returning GeoServer-style WMS `GetFeatureInfo` JSON for clicked/zoomed map features. Example transport metadata is now represented in the backend source contract as `observed_transport=OGC_WMS_GETFEATUREINFO_JSON`. Because the WMS path includes a long tokenized segment and usage/stability still needs confirmation, Android must not call or hardcode that WMS endpoint directly. The backend supports explicit admin/import capture first, with a future controlled adapter possible after endpoint and permission review.

Simple visual-layer/manual parameter capture:

```http
POST /api/v1/soil-profiles/enrichments/shc-slusi/manual-capture
```

Required payload: `parcel_id`, `state`, `district`, and `parameter`. Optional fields include `cycle`, `status_class`, `value_text`, `unit`, `source_url`, `notes`, and `raw_payload`. The backend stores this as `provider=SHC_SLUSI`, `snapshot_type=BASELINE`, `confidence=GOVT_VISUAL_LAYER`, and `metadata.capture_method=ADMIN_VISUAL_CAPTURE`.

Full point-popup capture from observed SHC/SLUSI WMS/visualisation data:

```http
POST /api/v1/soil-profiles/enrichments/shc-slusi/point-capture
```

Important payload fields include `parcel_id`, `state`, `district`, optional `village`, `latitude`, `longitude`, `cycle`, `source_url`, optional observed `wms_url`, nutrient values (`n_kg_ha`, `p_kg_ha`, `k_kg_ha`, `b_ppm`, `fe_ppm`, `zn_ppm`, `cu_ppm`, `s_ppm`, `organic_carbon_percent`, `ph`, `ec_ds_m`, `mn_ppm`), and land-property values (`depth_50k`, `slope_50k`, `erosion_50k`, `texture_50k`, `lcc_50k`, `lic_50k`, `hsg_50k`, `cec_text`, `soil_code`). The backend stores canonical values where fields exist (`nitrogen`, `ph`, `organic_carbon`) and keeps the remaining nutrient/land-property data in `normalized_values.nutrients` and `normalized_values.soil_land_properties`, with `confidence=GOVT_POINT_POPUP` and `metadata.capture_method=ADMIN_POINT_POPUP_CAPTURE`.

### Company discovery CSV

Company discovery candidates can be staged in bulk through CSV: download `GET /api/v1/company-discovery-candidates/template.csv`, validate with `POST /api/v1/company-discovery-candidates/csv/validate`, and import with `POST /api/v1/company-discovery-candidates/csv/import`. Imported rows remain `PENDING_REVIEW`; they do not become live company profiles until reviewed/applied.

## Backend readiness checkpoint - 2026-07-20

Current backend readiness estimate for Android MVP handoff: **about 89%**.

This estimate means the main backend-owned contracts are now in place for farmer communication, profile capture, advisory targeting, enrichment readiness, and company/customer administration. Remaining work is mostly provider automation, final Android consumption, admin polish, and production hardening.

### Completed backend foundations

- Broadcast/advisory foundation:
  - campaign/content/rule/delivery/audit tables;
  - localized content and media attachments;
  - farmer feed, read, and acknowledgement endpoints;
  - admin lifecycle controls for publish, expire, cancel, draft edit, delivery generation, audit history;
  - retry of undelivered rows before failure;
  - targeting support for farmer, project, crop, location, language, crop stage, and backend weather snapshots.
- Backend-only weather foundation:
  - weather provider config and snapshot model;
  - configurable refresh cadence concept, defaulting to 6 hours;
  - weather-targeted broadcasts based on stored backend snapshots;
  - Android explicitly does not call weather providers or use phone sensors for weather targeting.
- Backend-owned profile capture:
  - farmer, parcel, and soil profile forms;
  - backend-owned option sets for seasons, land units, ownership, irrigation, soil, language, and assistance modes;
  - profile readiness, field-agent worklist, and backend-filtered missing-field/section filters;
  - create/update paths for farmer, parcel, and soil profile maintenance.
- Agent/farmer dual-mode:
  - agent profile support;
  - a person can be both a farmer and an agent;
  - Android should switch modes based on backend bootstrap/worklist context.
- Land/parcel readiness:
  - parcels can be single-village or multi-location;
  - parcels carry PIN-code/location anchors;
  - ownership can represent owned, part-owned, leased, shared/sharecrop, family, and deployment-configurable variants.
- Soil enrichment foundation:
  - normalized enrichment snapshots;
  - latest/summary endpoints;
  - readiness source fields for SoilGrids and SHC/SLUSI;
  - enrichment queue and job audit;
  - admin soil-enrichment queue view with manual audit actions;
  - SHC/SLUSI visual data is parked as backend/admin capture or future controlled adapter, not Android direct calls.
- Company/customer profile foundation:
  - backend-only tenant company profile;
  - explicit company types including FPO, seed company, fertilizer company, pesticide company, machinery company, input company, buyer, trader, warehouse, financial institution, processor, insurer, NGO, government, cooperative, agri-tech, enterprise, and other;
  - source, verification status, source references, and audit history;
  - admin company profile UI.
- Company prepopulation workflow:
  - discovery candidate staging table;
  - review queue;
  - apply/merge candidate into live company profile;
  - CSV template, validation, import, admin upload/preview/import flow.

### Remaining before Android handoff

- Implement real provider workers/adapters:
  - scheduled weather refresh;
  - SoilGrids fetch worker;
  - Open-Meteo soil moisture/weather refresh;
  - controlled SHC/SLUSI import/adapter after source permission and stability review.
- Complete Android client consumption:
  - use backend profile forms/options/readiness instead of hardcoded lists where feature flags are enabled;
  - consume broadcast feed/read/ack/media;
  - consume agent/farmer mode bootstrap;
  - display soil enrichment summaries and readiness labels.
- Add final admin polish:
  - guided weather-provider operations;
  - better soil enrichment worker controls;
  - discovery duplicate matching UX.
- Run production-hardening pass:
  - tenant isolation review;
  - permission review;
  - audit coverage review;
  - full regression sweep.
- Produce final Android implementation checklist and sample payload bundle from current backend responses.

### Current recommendation

Do not start Android rewiring blindly. First finish provider-worker stubs and final API regression sweep, then create an Android handoff packet with exact endpoints, payload examples, feature flags, and rollout order.

### Weather operations health

Backend/admin can inspect weather provider health through `GET /api/v1/weather/operations/health`. Response `schema_version=weather_operations_health.v1` summarizes enabled, due, overdue, failed providers and fresh/stale/expired snapshots. Android should not call this endpoint for MVP; it is an operations/scheduler/admin readiness surface.

Weather operations health is now implemented in backend and admin web: `GET /api/v1/weather/operations/health` and admin `/weather` show provider due/overdue/failure status plus fresh/stale/expired snapshot counts.

### Soil enrichment operations health

Backend/admin can inspect enrichment queue and job health through `GET /api/v1/soil-profiles/enrichments/operations/health`. Response `schema_version=soil_enrichment_operations_health.v1` summarizes location-ready parcels, missing baseline/moisture counts, snapshot/provider counts, job audit outcomes, and recommended actions. Android MVP should not call this endpoint; it is an operations/admin readiness surface.

Soil enrichment operations health is admin/backend-only: `GET /api/v1/soil-profiles/enrichments/operations/health` and admin `/soil-enrichment` summarize queue health, provider coverage, job audit status, and recommended backend actions. Android should continue consuming summaries/readiness rather than provider operations endpoints.

See `docs/android-backend-handoff-packet.md` for the living Android/backend handoff packet and backend closeout checklist.

### Farmer home and parcel land location flow

Android should treat farmer home location and parcel land location as separate concepts. During farmer registration, capture home PIN/village and optionally a precise home GPS point. During parcel registration, first ask whether all parcels are in the same PIN code/village as the farmer home. If yes, Android can copy farmer `pin_code`, `village_id`, and `village_name_manual` into parcel defaults while storing the confirmation in `location_scope`. If no, Android should ask parcel PIN code and call `GET /api/v1/master-data/geography/villages/by-pin-code?pin_code={pin_code}` to display candidate villages because one PIN code can map to multiple villages. GPS point/polygon remains optional precision capture and does not replace PIN/village selection.

## Parcel location validation guardrails

Backend validates parcel location semantics without requiring GPS. If a parcel is marked same_as_home_location=true, supplied parcel PIN/village fields must not conflict with the farmer home PIN/village. If same_as_home_location=false, parcel PIN and village are required. GPS point/polygon remains optional precision data and is not used as a replacement for PIN/village selection.
