# AgriFabric demo capture checklist

Status date: 2026-08-17

This checklist converts `docs/demo-script-pack.md` into a practical video capture plan. It chooses the natural capture mode for each story: Android-only, web-only, mixed Android + web, or concept/narrated visual.

The rule of thumb:

- use Android-only when the story is field capture or farmer experience;
- use web-only when the story is admin/operator analytics;
- use mixed capture when the value is the handoff between field app and backend/admin;
- use concept/narrated visuals when the capability is roadmap or strategic framing.

## Global capture setup

### Shared visual conventions

- Use short videos: 60 to 120 seconds each.
- Use calm narration with one clear claim per video.
- Add small labels for “Android”, “Admin web”, “Backend-owned”, “Verified MVP”, and “Roadmap” where needed.
- Show deterministic demo data, not private or production data.
- Avoid raw logs unless the video is aimed at technical viewers.
- Do not claim live providers, operational risk scoring, NDVI analysis, or verified product labels.

### Preferred screen formats

- Android clips: portrait phone frame.
- Web admin clips: 16:9 desktop crop.
- Mixed clips: split screen or sequence cut:
  - Android first for field action;
  - web/admin second for backend evidence;
  - optional overlay for evidence claim.

### Suggested video naming

```text
01-farmer-onboarding-android.mp4
02-fpo-project-ops-web-android.mp4
03-crop-activity-ledger-android.mp4
04-offline-sync-resilience-android.mp4
05-advisory-lifecycle-web-android.mp4
06-field-event-to-advisory-mixed.mp4
07-localization-land-intelligence-mixed.mp4
08-geography-digipin-android-concept.mp4
09-relationship-graph-agent-performance-concept.mp4
10-insurance-integrity-roadmap-concept.mp4
```

## Capture mode matrix

| # | Story | Natural mode | Why |
| --- | --- | --- | --- |
| 1 | Farmer onboarding | Android-only with light backend claim overlays | The viewer should feel the field capture experience. |
| 2 | FPO/project operations | Mixed, web-first | Admin search/trace is operator value; Android confirms farmer/project hydration. |
| 3 | Crop activity ledger | Android-only, optional web trace outro | Activity logging is a field workflow. |
| 4 | Offline sync resilience | Android-only for product demo; optional technical overlay | Sync resilience is best understood through phone state and conflict cards. |
| 5 | Broadcast/advisory lifecycle | Mixed, web-first then Android then web | Admin creates/inspects; Android receives/acks; admin sees analytics. |
| 6 | Field event to advisory loop | Mixed, Android-first then web then Android | The loop is the handoff: field event → admin/backend advisory → farmer feed. |
| 7 | Localization and land intelligence | Mixed | Admin override/land intelligence is configured in backend/web; Android proves rendering. |
| 8 | Geography and DigiPin | Android-only plus concept overlay | Capture is Android; explanation needs a simple layer diagram. |
| 9 | Relationship graph and agent performance | Concept/narrated visual with web evidence snippets | Formal analytics are roadmap; show graph foundation and safe future. |
| 10 | Insurance/subsidy integrity | Concept/narrated visual with implemented evidence snippets | Risk scoring is roadmap; avoid implying current operational scoring. |

## Video 1: Farmer onboarding and backend-owned profile capture

Mode: Android-only.

Length: 60-90 seconds.

Primary claim:

Backend-owned farmer onboarding works in the field without hardcoded local form logic.

Capture sequence:

1. Open Android app.
2. Show user mode/profile context.
3. Open profile or registration form.
4. Show backend-driven labels/options.
5. Show PIN/village or location guardrail field.
6. Show parcel/location capture.
7. Show backend-returned readiness or DigiPin/GPS-related result if available.

Narration beats:

- “The app is a field surface; the backend owns the form contract.”
- “A farmer can be independent or project-associated.”
- “Location evidence is separated into postal/admin context and precise GPS/DigiPin.”

Evidence overlay:

- backend-owned forms;
- no hardcoded labels;
- GPS/DigiPin evidence;
- project/independent context.

Avoid:

- claiming global geography is complete;
- claiming Android computes DigiPin.

## Video 2: FPO project operations across villages and crops

Mode: mixed, web-first.

Length: 90 seconds.

Primary claim:

One FPO/project can coordinate many affiliated farmers across villages, crops, workflow stages, and project lifecycle states.

Capture sequence:

1. Web admin: open project enrollments.
2. Show FPO project and farmer count.
3. Search/filter by village.
4. Search/filter by crop.
5. Drill into selected Maize farmer.
6. Web admin or trace screen: show project trace/crop/status distribution.
7. Android: show selected farmer hydrates with project context and crop cycle.
8. Optional: Android closure notice/continuation snippet if this is the “project lifecycle” version.

Narration beats:

- “This is not one farmer at a time; it is a project graph.”
- “Operators can search by village, crop, mobile, and drill down.”
- “Farmers keep their identity and data even when project participation changes.”

Evidence overlay:

- 12 FPO farmers;
- 4 villages;
- 4 crops;
- project trace;
- Android project context.

Avoid:

- claiming this is a thousand-farmer load test.

## Video 3: Crop cycle, stage, activity, and cost trail

Mode: Android-only, optional web trace outro.

Length: 60-90 seconds.

Primary claim:

Farm activity becomes a structured crop-season ledger.

Capture sequence:

1. Android: open farmer crop cycle.
2. Show crop, season, parcel, and stage timeline.
3. Log activity such as fertilizer, spray, irrigation, labor, or machinery.
4. Show saved/synced activity.
5. Show cost or summary card if available.
6. Optional web/admin outro: show trace/detail sees the same crop/activity context.

Narration beats:

- “Each activity is connected to farmer, parcel, crop cycle, stage, and cost context.”
- “This becomes an operational record, not just a note.”

Evidence overlay:

- crop cycle;
- stage;
- activity;
- backend cost/trace.

Avoid:

- claiming full harvest P&L is implemented if not shown.

## Video 4: Offline sync resilience

Mode: Android-only for public demo; optional technical variant with backend verifier evidence.

Length: 90-120 seconds.

Primary claim:

The app survives weak connectivity, restart, partial replay, and conflicts without duplicating backend records.

Public capture sequence:

1. Android: show offline or pending sync state.
2. Create activity while offline/unavailable.
3. Show pending queue/state.
4. Restart app or reconnect.
5. Show sync success.
6. Show conflict card variant if using VERSION_MISMATCH or WORKFLOW_INVALID demo.
7. Resolve by accepting server guidance.

Technical variant sequence:

1. Android queue state.
2. Backend/log overlay: accepted/conflict/failed row distinction.
3. Android conflict drawer.
4. Backend evidence: exact-once materialization/no duplicate.

Narration beats:

- “Offline-first is not just storing data locally.”
- “The hard part is replaying safely when the world changed.”
- “Accepted work continues; conflicts are isolated and explainable.”

Evidence overlay:

- queue persisted;
- replayed once;
- conflict card;
- no duplicate activity;
- server authority/manual review.

Avoid:

- showing raw backend logs in a general marketing video.

## Video 5: Broadcast/advisory lifecycle

Mode: mixed, web-first then Android then web.

Length: 90 seconds.

Primary claim:

Admins can send targeted advisories and see delivery/read/ack analytics.

Capture sequence:

1. Web admin: open Broadcasts.
2. Show campaign/content/audience rule.
3. Show delivery count or generate deliveries.
4. Android: open farmer broadcast feed.
5. Show advisory card, media/text fallback if relevant.
6. Android: mark read/acknowledge.
7. Web admin: show read/ack delivery analytics and audit history.

Narration beats:

- “Targeting is backend-owned.”
- “Android receives only assigned farmer-visible content.”
- “Admin can see lifecycle and audit.”

Evidence overlay:

- targeted campaign;
- delivery count;
- read;
- acknowledged;
- audit events.

Avoid:

- implying on-device audience selection.

## Video 6: Field event to targeted advisory

Mode: mixed, Android-first then web/admin then Android.

Length: 75-105 seconds.

Primary claim:

A field observation becomes targeted action without losing media evidence.

Capture sequence:

1. Android: capture/report pest field event with photo.
2. Web/admin: show field event detail and media.
3. Web/admin: show advisory campaign generated/sent.
4. Web/admin: show source media reused in advisory.
5. Android: target Maize farmer receives advisory.
6. Optional: show non-target Rice farmer does not receive it.

Narration beats:

- “The field event is not a dead-end report.”
- “The same media asset travels into a targeted advisory.”
- “Crop targeting prevents overdelivery.”

Evidence overlay:

- field event;
- media reused;
- advisory sent;
- Maize targeted;
- Rice excluded.

Avoid:

- claiming automated pest diagnosis.

## Video 7: Localization and land intelligence

Mode: mixed.

Length: 90 seconds.

Primary claim:

Backend-admin changes can shape Android-visible labels and land guidance without shipping a new app.

Capture sequence:

1. Web admin: localization override screen or documented override output.
2. Android: show overridden label or safe fallback label.
3. Android: switch or demonstrate Hindi/Kannada/Marathi/Punjabi fallback behavior.
4. Web/admin or Android: show land-intelligence summary for PIN/crop/season/project.
5. Android: show informational-only/do-not-block cards.

Narration beats:

- “Labels are backend-provided maps.”
- “Android falls back safely when native labels are not reviewed.”
- “Land intelligence informs; it does not block onboarding.”

Evidence overlay:

- backend label map;
- no raw JSON;
- no blank label;
- project land-intelligence override;
- informational only.

Avoid:

- claiming native translation completeness.

## Video 8: Geography, DigiPin, and plot resolution

Mode: Android-only plus concept overlay.

Length: 75-90 seconds.

Primary claim:

AgriFabric separates administrative, postal, and precise location layers.

Capture sequence:

1. Android: enter/select PIN/village context.
2. Android: show GPS/parcel capture.
3. Android: show backend-returned DigiPin where coordinates exist.
4. Overlay simple layer diagram:
   - LGD = administrative identity;
   - PIN = postal/reference;
   - GPS/parcel = physical evidence;
   - DigiPin = coordinate-derived precision;
   - land intelligence = backend guidance.

Narration beats:

- “PIN is not a parcel.”
- “Village is not a coordinate.”
- “DigiPin is generated from GPS by backend.”
- “This matters for traceability and later risk review.”

Evidence overlay:

- PIN guardrail;
- GPS;
- DigiPin;
- parcel/plot evidence.

Avoid:

- claiming live village geocoding or global rollout.

## Video 9: Relationship graph and field-agent performance

Mode: concept/narrated visual with web/admin snippets.

Length: 90-120 seconds.

Primary claim:

AgriFabric structures agriculture operations as a connected graph that can support future field-agent performance intelligence.

Capture sequence:

1. Show graph visual:
   - Company/FPO -> project -> farmer cohort;
   - field agent -> assigned farmers;
   - farmer -> parcel -> crop cycle -> activity;
   - field event -> media -> advisory;
   - sync/audit trail.
2. Insert web/admin snippets:
   - field-agent worklist or assignment;
   - project enrollment/search;
   - advisory analytics;
   - field event/media evidence.
3. Narrate future metrics:
   - coverage;
   - timeliness;
   - completeness;
   - evidence quality;
   - advisory follow-up;
   - anomaly review.

Narration beats:

- “The graph is the product moat.”
- “Freelance agents can build portable reputation.”
- “Companies can benchmark employees/agronomists fairly.”
- “Performance analytics must be explainable and context-adjusted.”

Evidence overlay:

- implemented foundation;
- roadmap: scorecards/dashboard;
- not punitive black-box ranking.

Avoid:

- claiming formal agent scorecards exist today.

## Video 10: Insurance and subsidy integrity roadmap

Mode: concept/narrated visual with implemented evidence snippets.

Length: 90-120 seconds.

Primary claim:

The captured field evidence graph can support future review-assistive insurance, subsidy, credit, and risk workflows.

Capture sequence:

1. Show implemented evidence snippets:
   - farmer/project identity;
   - parcel/GPS/DigiPin;
   - crop cycle/activity trail;
   - field event/media;
   - advisory/read/ack audit;
   - sync audit.
2. Show concept overlay of future risk flags:
   - same parcel claimed by multiple farmers;
   - crop declaration mismatch;
   - duplicate damage photos;
   - geo/time plausibility;
   - sparse cultivation trail;
   - agent anomaly;
   - NDVI/EVI time-series evidence.
3. End with human-review boundary.

Narration beats:

- “We are not replacing statutory systems.”
- “We are building the field evidence layer they can use.”
- “Risk flags should assist review, not automatically deny genuine farmers.”

Evidence overlay:

- implemented evidence foundation;
- roadmap risk scoring;
- human review;
- NDVI future.

Avoid:

- saying “detects fraud today”;
- saying “approves or rejects claims automatically.”

## Capture dependencies by video

| Video | Android required | Web admin required | Backend fixture likely needed | Concept overlay needed |
| --- | --- | --- | --- | --- |
| 1 | Yes | No | Dynamic/persona profile fixture | Light |
| 2 | Yes | Yes | FPO multi-village fixture | No |
| 3 | Yes | Optional | Crop-cycle/activity fixture | No |
| 4 | Yes | Optional | Sync/offline fixture | Optional |
| 5 | Yes | Yes | Broadcast/FPO fixture | No |
| 6 | Yes | Yes | Field-event advisory fixture | No |
| 7 | Yes | Yes | Localization/land-intelligence fixture | Light |
| 8 | Yes | Optional | DigiPin/geography fixture | Yes |
| 9 | Optional snippets | Yes snippets | Existing graph foundation only | Yes |
| 10 | Optional snippets | Optional snippets | Existing evidence snippets only | Yes |

## Recommended production order

1. Capture Video 2 first: FPO/project operations. It shows commercial value quickly.
2. Capture Video 5 next: broadcast/advisory lifecycle. It shows admin + Android handoff.
3. Capture Video 4 next: offline sync resilience. It proves technical depth.
4. Capture Video 6: field event to advisory loop. It is a strong “field evidence to action” story.
5. Capture Video 1 and 3: onboarding and crop ledger.
6. Capture Video 7 and 8: localization and geography intelligence.
7. Create concept visuals for Video 9 and 10 after the implemented clips exist.

## Landing-page usage

Landing page should feature:

- hero composite from Videos 1, 2, 4, and 5;
- proof strip clips from Videos 2, 4, 5, and 6;
- use-case grid thumbnails from all implemented videos;
- roadmap section using Videos 9 and 10 with clear roadmap badges.

