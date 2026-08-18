# AgriFabric relationship graph visual spec

Status date: 2026-08-17

This spec defines the relationship graph visual for the future landing page, investor/product one-pager, and demo video overlays. It should make the core idea obvious: AgriFabric is not just forms and dashboards; it is a typed field-evidence graph connecting farmers, field agents, companies/FPOs, projects, parcels, crop cycles, activities, media, advisories, sync events, and audit trails.

Source docs:

- `docs/agrifabric-relationship-graph-and-agent-performance.md`
- `docs/landing-page-wireframe.md`
- `docs/landing-page-content-brief.md`
- `docs/demo-asset-inventory.md`
- `docs/agrifabric-insurance-fraud-risk-scoring.md`

## Primary message

Use this as the main caption:

```text
Every field interaction creates typed relationships.
Those relationships power traceability today and future analytics tomorrow.
```

Short version for small overlays:

```text
From field data to an evidence graph.
```

## Claim boundary

The visual can show:

- current graph foundation;
- implemented traceability;
- project/farmer/parcel/crop/advisory/audit relationships;
- future analytics potential.

The visual must not imply that these are already operational modules unless implemented separately:

- field-agent scorecards;
- commercial agent marketplace/matching;
- fraud/waste/abuse scoring;
- insurance claim approval or denial;
- NDVI/EVI satellite analysis.

Recommended boundary label:

```text
Traceability implemented. Advanced scoring and matching are roadmap modules.
```

## Visual style

Tone:

- practical;
- trustworthy;
- operating-system-like;
- not “AI magic”.

Recommended style:

- dark navy or off-white background;
- rounded node pills/cards;
- thin curved edges;
- 2-3 highlighted paths;
- small status chips for “Verified MVP”, “Foundation”, and “Roadmap”.

Avoid:

- chaotic hairball graph;
- too many crossing lines;
- treating roadmap nodes as if they are live dashboards;
- icons without labels.

## Node groups

### Group A — Organizations and people

Nodes:

- Company / FPO
- Project
- Field agent
- Farmer

Purpose:

Show who is connected operationally.

Implemented foundation:

- company/FPO project context;
- project enrollment;
- field-agent assisted workflows;
- assignment/reassignment foundation;
- farmer identity independent from project participation.

### Group B — Field evidence

Nodes:

- Parcel
- GPS / DigiPin
- Crop cycle
- Stage / activity
- Media asset
- Field event

Purpose:

Show how the system turns field work into structured evidence.

Implemented foundation:

- parcel/profile hydration;
- GPS/DigiPin materialization;
- crop-cycle and activity logging;
- field-event report and media reuse;
- offline sync materialization.

### Group C — Communication and governance

Nodes:

- Advisory / broadcast
- Audience rule
- Delivery / read / ack
- Sync event
- Conflict / audit trail

Purpose:

Show backend-owned communication, lifecycle, and accountability.

Implemented foundation:

- broadcast targeting;
- read/ack lifecycle;
- admin delivery analytics;
- terminal lifecycle;
- sync/conflict audit.

### Group D — Roadmap analytics

Nodes:

- Agent performance
- Assignment planning
- Risk review
- Claim evidence bundle

Purpose:

Show future analytical/commercial implications of the graph.

Status:

Roadmap on implemented graph foundation.

## Core edges

Use typed edge labels where space permits.

| Edge | Label | Status |
| --- | --- | --- |
| Company/FPO → Project | runs | Verified MVP |
| Project → Farmer | enrolls | Verified MVP |
| Project → Field agent | assigns | Foundation |
| Field agent → Farmer | assists | Verified MVP |
| Farmer → Parcel | operates | Verified MVP |
| Parcel → GPS / DigiPin | locates | Verified MVP |
| Parcel → Crop cycle | grows | Verified MVP |
| Crop cycle → Stage / activity | records | Verified MVP |
| Field agent/Farmer → Field event | reports | Verified MVP |
| Field event → Media asset | attaches | Verified MVP |
| Field event → Advisory / broadcast | triggers | Verified MVP |
| Advisory / broadcast → Audience rule | targets | Verified MVP |
| Audience rule → Farmer | selects cohort | Verified MVP |
| Advisory / broadcast → Delivery / read / ack | tracks lifecycle | Verified MVP |
| Stage / activity → Sync event | syncs | Verified MVP |
| Sync event → Conflict / audit trail | records | Verified MVP |
| Graph → Agent performance | future analytics | Roadmap |
| Graph → Assignment planning | future analytics | Roadmap |
| Graph → Risk review | future analytics | Roadmap |
| Graph → Claim evidence bundle | future analytics | Roadmap |

## Recommended landing-page layout

Use a three-zone graph:

```text
┌──────────────────────────────────────────────────────────────┐
│                    Company / FPO                             │
│                          ↓ runs                              │
│                       Project                                │
│                     ↙        ↘                               │
│              Field agent    Farmer                           │
│                    ↓ assists   ↓ operates                    │
│                              Parcel                          │
│                          ↙      ↘                            │
│                  GPS/DigiPin   Crop cycle                    │
│                                  ↓ records                   │
│                            Stage / activity                  │
│                                  ↓ syncs                     │
│                              Sync/audit                      │
│                                                              │
│ Field event → Media asset → Advisory → Delivery/read/ack      │
│                                                              │
│ Roadmap layer: Agent performance | Risk review | Claims       │
└──────────────────────────────────────────────────────────────┘
```

Recommended desktop placement:

- Left: short copy block and boundary chip.
- Right: graph visual.
- Below graph: 3 highlighted path chips.

Recommended mobile placement:

- Show graph as stacked relationship paths rather than a dense node-link diagram.
- Use accordion cards:
  - Project graph.
  - Parcel/crop graph.
  - Advisory/audit graph.
  - Roadmap analytics.

## Highlighted paths

### Path 1 — Project operating graph

```text
Company/FPO → Project → Farmer cohort
              ↓
           Field agents
```

Caption:

```text
Coordinate project cohorts across farmers, villages, crops, and field teams.
```

Status:

Verified MVP / foundation.

### Path 2 — Crop evidence graph

```text
Farmer → Parcel → Crop cycle → Stage/activity → Sync/audit
```

Caption:

```text
Turn field work into a structured crop-season evidence trail.
```

Status:

Verified MVP.

### Path 3 — Advisory action graph

```text
Field event → Media asset → Targeted advisory → Delivery/read/ack audit
```

Caption:

```text
Convert field observations into targeted, auditable farmer communication.
```

Status:

Verified MVP.

### Path 4 — Future intelligence layer

```text
Evidence graph → Agent performance | Assignment planning | Risk review | Claim evidence bundle
```

Caption:

```text
Use the connected evidence trail for future analytics and review-assistive modules.
```

Status:

Roadmap on implemented foundation.

## Color and badge system

Recommended colors:

```text
Implemented / Verified MVP: green or teal
Foundation: blue
Roadmap: amber or purple
Audit / control: slate
Risk boundary: amber outline
```

Badge labels:

- Verified MVP
- Foundation
- Roadmap
- Backend-owned
- Audit trail

Roadmap nodes must use an outline/dashed style rather than the same filled style as implemented nodes.

## SVG-ready coordinate sketch

Use this as the first static SVG layout guide. Coordinates assume a 1200 × 720 viewBox.

| Node | x | y | Group |
| --- | ---: | ---: | --- |
| Company / FPO | 170 | 80 | People/org |
| Project | 350 | 150 | People/org |
| Field agent | 170 | 250 | People/org |
| Farmer | 520 | 250 | People/org |
| Parcel | 520 | 370 | Field evidence |
| GPS / DigiPin | 350 | 490 | Field evidence |
| Crop cycle | 690 | 490 | Field evidence |
| Stage / activity | 860 | 370 | Field evidence |
| Field event | 860 | 250 | Field evidence |
| Media asset | 1010 | 250 | Field evidence |
| Advisory / broadcast | 1010 | 370 | Communication |
| Audience rule | 860 | 490 | Communication |
| Delivery / read / ack | 1010 | 520 | Communication |
| Sync event | 690 | 610 | Audit |
| Conflict / audit trail | 860 | 610 | Audit |
| Roadmap analytics | 350 | 610 | Roadmap |

Suggested edges:

```text
Company/FPO -> Project
Project -> Field agent
Project -> Farmer
Field agent -> Farmer
Farmer -> Parcel
Parcel -> GPS/DigiPin
Parcel -> Crop cycle
Crop cycle -> Stage/activity
Stage/activity -> Sync event
Sync event -> Conflict/audit trail
Farmer -> Field event
Field event -> Media asset
Field event -> Advisory/broadcast
Advisory/broadcast -> Audience rule
Audience rule -> Farmer
Advisory/broadcast -> Delivery/read/ack
Conflict/audit trail -> Roadmap analytics
Parcel -> Roadmap analytics
Delivery/read/ack -> Roadmap analytics
```

## Copy blocks for the graph section

### Option A — concise

```text
AgriFabric models agriculture operations as a relationship graph. Farmers, agents, companies, projects, parcels, crop cycles, activities, media, advisories, and audit trails are connected through typed relationships. That graph powers traceability today and creates the foundation for future analytics.
```

### Option B — more commercial

```text
The commercial value is in the connections. A project is linked to farmers, agents, crops, parcels, advisories, field events, and audit history. That structure helps operators coordinate work today and can later support agent benchmarking, assignment planning, and risk-review workflows.
```

### Option C — more evidence-focused

```text
Every farmer record, parcel, crop activity, photo, advisory, acknowledgement, and sync event becomes part of an evidence graph. Instead of isolated records, AgriFabric creates a connected trail that can be searched, audited, and extended into future review workflows.
```

## Demo overlay labels

Use these labels in short videos:

```text
Farmer identity
Project enrollment
Field-agent assignment
Parcel evidence
Crop cycle
Activity log
Field event photo
Targeted advisory
Read/ack audit
Sync/conflict audit
Roadmap: risk review
Roadmap: agent performance
```

## Accessibility requirements

- Do not rely only on color to distinguish roadmap vs implemented nodes.
- Use text badges or dashed outlines.
- Ensure graph labels remain legible on mobile.
- Provide alt text:

```text
Relationship graph showing Company/FPO, Project, Field agent, Farmer, Parcel, Crop cycle, Field event, Media, Advisory, Delivery, Sync event, and Audit trail nodes connected as an agriculture evidence graph, with roadmap analytics separated from implemented traceability.
```

## Acceptance checklist

Before using the graph visual publicly:

- Roadmap analytics nodes are visually distinct.
- Fraud/risk/claim wording is bounded as future review-assistive capability.
- The visual includes both field capture and admin/advisory/audit paths.
- The graph is readable at desktop and mobile sizes.
- It does not imply automated claim decisions or live scoring.
- It connects to the demo asset inventory and landing page proof map.

