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

