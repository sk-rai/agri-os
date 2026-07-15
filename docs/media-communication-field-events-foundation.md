# Media, communication, and field-event foundation

Status: architecture/API contract checkpoint; no runtime implementation yet  
Primary consumers: Android offline queue, admin web, future agronomist/dealer workflows

## Why this module family matters

Agri-OS is becoming a field measurement and decision-support system, not only a crop activity logger. The next major data layer should capture evidence, farmer questions, advisories, and ground-level events in a reusable way.

The design should support:

- crop-stage photos and evidence;
- farmer text/audio/photo queries;
- company/FPO/advisor broadcast advisories;
- two-way farmer-agronomist communication;
- field event reporting such as rainfall, pest, hailstorm, locust, flood, wind, drought stress;
- offline capture first, backend materialization later;
- future external weather/IoT/API ingestion without redesign.

## Guiding principle

Create generic primitives first, then attach them to business flows.

Do not build separate photo/audio/document mechanisms for activity logs, farmer queries, advisories, field events, and crop-stage evidence. Use one media asset + attachment model, then link that model to the relevant entity.

## Proposed phase 1: shared media asset and attachment primitive

Candidate records:

- `MediaAsset`
- `MediaAttachment`

Candidate `MediaAsset` fields:

- `id`
- `tenant_id`
- `project_id` nullable
- `farmer_id` nullable
- `uploaded_by` / `actor_id`
- `media_type`: `PHOTO`, `AUDIO`, `VIDEO`, `DOCUMENT`
- `mime_type`
- `storage_url` / `storage_key`
- `thumbnail_url` nullable
- `sha256_hash`
- `size_bytes`
- `duration_seconds` for audio/video
- `width` / `height` for images/video
- `capture_lat` / `capture_lng` / `capture_accuracy_meters`
- `captured_at`
- `upload_status`: `PENDING`, `UPLOADED`, `FAILED`, `QUARANTINED`
- `metadata` JSONB

Candidate `MediaAttachment` fields:

- `id`
- `tenant_id`
- `media_asset_id`
- `entity_type`: `FARMER`, `PARCEL`, `SOIL_PROFILE`, `CROP_CYCLE`, `CROP_STAGE`, `CROP_ACTIVITY`, `FIELD_EVENT`, `ADVISORY`, `QUERY_THREAD`, `QUERY_MESSAGE`
- `entity_id`
- `purpose`: `STAGE_EVIDENCE`, `ACTIVITY_EVIDENCE`, `DISEASE_PHOTO`, `SOIL_CARD`, `PARCEL_BOUNDARY`, `QUERY_ATTACHMENT`, `ADVISORY_ATTACHMENT`, `AUDIO_NOTE`
- `caption`
- `display_order`
- `is_primary`
- `created_at`

Candidate first API shape:

- `POST /api/v1/media/assets` - create metadata record / upload intent
- `POST /api/v1/media/assets/{asset_id}/complete` - mark upload complete after storage write
- `POST /api/v1/media/attachments` - attach existing asset to entity
- `GET /api/v1/media/attachments?entity_type=...&entity_id=...` - read attachments for UI

For MVP, if direct binary upload is too much, Android can sync media metadata first and upload binary later. The database model should not depend on the final object-storage choice.

## Proposed phase 2: field event reports

Candidate records:

- `FieldEventType`
- `FieldEventReport`

Candidate event types:

- `RAIN`
- `PEST`
- `DISEASE`
- `HAILSTORM`
- `LOCUST`
- `FLOOD`
- `DROUGHT_STRESS`
- `THUNDERSTORM_WIND`
- `HEAT_STRESS`
- `COLD_STRESS`
- `IRRIGATION_FAILURE`
- `OTHER`

Candidate `FieldEventReport` fields:

- `id`
- `tenant_id`
- `project_id` nullable
- `farmer_id`
- `parcel_id` nullable
- `crop_cycle_id` nullable
- `stage_code` nullable
- `event_type`
- `severity`: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- `event_date` / `reported_at`
- `lat` / `lng` / `accuracy_meters`
- `description`
- `estimated_area_affected`
- `estimated_loss_percent`
- `source`: `FARMER_ANDROID`, `FIELD_AGENT_ANDROID`, `ADMIN_WEB`, `EXTERNAL_API`, `IOT_DEVICE`
- `external_source` / `external_event_id` nullable
- `status`: `REPORTED`, `UNDER_REVIEW`, `ADVISORY_SENT`, `RESOLVED`, `DISMISSED`
- `metadata` JSONB

Candidate APIs:

- `POST /api/v1/field-events`
- `GET /api/v1/field-events?project_id=&farmer_id=&parcel_id=&event_type=&severity=&status=`
- `GET /api/v1/field-events/{event_id}`
- `PATCH /api/v1/field-events/{event_id}/status`
- attach media through shared `MediaAttachment` APIs

## Proposed phase 3: advisory/broadcast campaigns

Candidate records:

- `AdvisoryCampaign`
- `AdvisoryMessage`
- `AdvisoryAudienceRule`
- `AdvisoryDelivery`

Audience dimensions:

- tenant/project
- farmer IDs
- parcel IDs
- crop code
- crop stage
- geography/territory
- organization unit/dealer/agronomist assignment
- language preference
- event-triggered audience such as high-severity pest reports

Candidate APIs:

- `POST /api/v1/advisories/campaigns`
- `GET /api/v1/advisories/campaigns`
- `POST /api/v1/advisories/campaigns/{campaign_id}/publish`
- `GET /api/v1/farmers/{farmer_id}/advisories`
- `POST /api/v1/advisories/{delivery_id}/ack`

For MVP, start with read/list/ack before adding rich campaign builders.

## Proposed phase 4: farmer query and conversation threads

Candidate records:

- `QueryThread`
- `QueryMessage`
- `QueryAssignment`
- `QueryStatusHistory`

Candidate thread fields:

- `id`
- `tenant_id`
- `project_id` nullable
- `farmer_id`
- `parcel_id` nullable
- `crop_cycle_id` nullable
- `stage_code` nullable
- `subject`
- `category`: `CROP_HEALTH`, `INPUT_USAGE`, `IRRIGATION`, `MARKET`, `INSURANCE`, `TECH_SUPPORT`, `OTHER`
- `priority`: `LOW`, `MEDIUM`, `HIGH`, `URGENT`
- `status`: `OPEN`, `ASSIGNED`, `ANSWERED`, `CLOSED`
- `assigned_to` nullable
- `last_message_at`

Candidate message fields:

- `id`
- `thread_id`
- `sender_type`: `FARMER`, `FIELD_AGENT`, `AGRONOMIST`, `ADMIN`, `SYSTEM`
- `sender_id`
- `message_type`: `TEXT`, `AUDIO`, `PHOTO`, `DOCUMENT`, `SYSTEM`
- `body_text` nullable
- `created_at`
- media attached through shared `MediaAttachment`

Candidate APIs:

- `POST /api/v1/query-threads`
- `GET /api/v1/query-threads?farmer_id=&project_id=&status=&assigned_to=`
- `GET /api/v1/query-threads/{thread_id}`
- `POST /api/v1/query-threads/{thread_id}/messages`
- `PATCH /api/v1/query-threads/{thread_id}/status`
- `PATCH /api/v1/query-threads/{thread_id}/assignment`

## Android offline behavior

Android should eventually queue these as sync events:

- `MEDIA_ASSET`
- `MEDIA_ATTACHMENT`
- `FIELD_EVENT_REPORT`
- `QUERY_THREAD`
- `QUERY_MESSAGE`
- `ADVISORY_ACK`

Required offline metadata:

- local UUID
- backend UUID when known
- tenant/project/farmer context
- entity type and entity ID
- capture timestamp
- GPS/accuracy where available
- media hash and upload status
- retry count and last error

## Admin/read-only expectations

Admin should first get read-only screens before mutation-heavy tools:

1. media attachment trace panel on farmer/parcel/cycle/activity views;
2. field event list/detail;
3. query inbox/detail;
4. advisory delivery list/detail;
5. campaign builder later.

View-only project users should be able to inspect assigned data but not publish advisories, answer farmer queries, or change event status.

## Recommended implementation order

1. Shared media DB model + read-only admin trace placeholders.
2. Field event report DB/API with tests.
3. Android/backend sync materialization for `FIELD_EVENT_REPORT`.
4. Query thread/message DB/API with text-only support.
5. Attach media/audio to query messages.
6. Advisory list/delivery/ack APIs.
7. Admin inbox and advisory campaign authoring.

## Regression strategy

Each module should ship with focused regression scripts before UI work:

- media asset/attachment contract test
- field event create/list/status test
- field event sync materialization test
- query thread/message test
- advisory delivery/ack test
- permission test for viewer vs editor
