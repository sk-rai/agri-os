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
- Backend refresh orchestration is provider-driven and cadence-based:
  - `GET /api/v1/weather/providers/refresh-plan` returns enabled providers, due state, hours until due, and last refresh status/message.
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

