# AgriFabric relationship graph and field-agent performance intelligence

Status date: 2026-08-17

This note captures a product and analytics framing for AgriFabric as a relationship graph connecting farmers, field agents, companies, FPOs, projects, parcels, crop cycles, activities, advisories, media, and audit events.

It also defines a future field-agent performance analysis module. The goal is to show how the same graph can support commercial matching, operational benchmarking, assignment quality, and fraud/waste/abuse review without turning the system into an opaque punitive scorekeeper.

## Why the graph framing matters

AgriFabric is not only a collection of forms and screens. It is an agriculture relationship graph.

Each field interaction creates nodes and edges:

- farmer belongs to project;
- farmer is assisted by field agent;
- field agent works for or with company/FPO;
- company runs project;
- project scopes crops, geographies, inputs, advisories, and workflows;
- parcel belongs to farmer and project context;
- crop cycle belongs to parcel/farmer/project;
- activity belongs to crop cycle and stage;
- field event belongs to farmer/parcel/crop context;
- media belongs to field event/advisory/activity;
- broadcast targets farmer cohorts through project, crop, stage, language, location, or farmer rules;
- sync event/audit trail records who changed what, when, from which device/context.

The value is not just the individual record. The value is the connected structure.

## Core graph nodes

### People and organizations

- farmers;
- field agents;
- company employees such as agronomists;
- freelance agents;
- companies;
- FPOs/cooperatives;
- program administrators;
- future insurers/lenders/subsidy administrators.

### Field entities

- parcels;
- DigiPin/GPS coordinates;
- crop cycles;
- crop stages;
- activity logs;
- soil profiles;
- field events;
- media assets.

### Program entities

- projects;
- project enrollments;
- workflows;
- project inputs/products;
- advisories and broadcasts;
- audience rules;
- delivery/read/ack rows;
- localization and land-intelligence overrides.

### Control and audit entities

- sync events;
- sync conflicts;
- processed-event audit;
- assignment/reassignment metadata;
- lifecycle transitions;
- admin audit events.

## Core graph edges

| Edge | Meaning | Current implemented foundation |
| --- | --- | --- |
| farmer -> project | Farmer participates in a project/FPO/company program. | Project enrollments, launch context, project picker, project closure continuation. |
| farmer -> parcel | Farmer operates or reports land parcel. | Parcel/profile hydration, GPS/DigiPin materialization. |
| parcel -> crop cycle | Crop is grown on a parcel for a season. | Crop-cycle fixture, stage/activity workflows. |
| crop cycle -> activity | Field activity occurred in a crop/stage context. | Activity logging, offline sync, cost summaries. |
| farmer -> field event -> media | Farmer/agent reports field condition with photo/media. | Field-event advisory loop and media reuse. |
| field event -> advisory | Backend turns field observation into targeted communication. | Field event to advisory loop. |
| project/crop/stage/location -> broadcast audience | Campaign targets a cohort. | Broadcast audience targeting. |
| agent -> assigned farmer/project | Field agent is responsible for farmer/project work. | Field-agent worklist and reassignment lifecycle. |
| user/device -> sync event | Offline record is submitted, replayed, or conflicts. | Sync/conflict/offline flows. |
| company/FPO -> project -> farmer cohort | Organization manages project population. | FPO multi-village workflow and search/drill-down. |

## Analytical implications

The graph enables analysis that flat tables cannot express cleanly:

- Which field agents are connected to the most active, complete, or responsive farmers?
- Which FPO projects have weak parcel/crop/activity evidence?
- Which advisories reached the intended crop/stage/location cohort?
- Which farmers have sparse cultivation trails despite high-value project/claim exposure?
- Which parcels appear under multiple farmers, projects, or claims in overlapping windows?
- Which agents submit unusually many reports, reports from far-apart locations, or repeated media?
- Which companies/projects produce better completion, acknowledgement, or crop-stage progression?
- Which geography/crop/project combinations show strong field evidence and which need intervention?

This makes AgriFabric commercially valuable as an operating graph:

- FPOs can manage farmer cohorts and project health.
- Enterprises can monitor field execution and adoption.
- Field-agent networks can prove performance.
- Freelance agents can build portable reputation.
- Insurers/lenders/programs can request evidence bundles and review risk flags.

## Commercial implications

### For companies and FPOs

The graph helps identify:

- reliable agents for a project geography;
- agents with strong farmer follow-up;
- weak assignment zones;
- farmers with missing parcel/crop evidence;
- advisories that produce high or low acknowledgement;
- projects that need additional field support.

### For freelance field agents

If field agents operate as freelancers, the graph can become a reputation and income engine.

More verified work across more companies/projects can create:

- a portable work history;
- evidence of farmer coverage;
- completion and quality metrics;
- specialization by crop/geography/project type;
- better eligibility for future assignments;
- higher trust with companies/FPOs/insurers.

Important boundary: freelance reputation should be consented, transparent, and scoped. Agents should know what is measured and how it is used.

### For company-employed agronomists

For employees, the graph can support holistic performance review:

- assigned farmer coverage;
- timeliness of visits and follow-ups;
- advisory acknowledgement and farmer response;
- field-event closure;
- crop-cycle completeness;
- work quality and evidence completeness;
- geography/crop complexity handled;
- benchmark against similar roles, not unfair raw totals.

Important boundary: employee evaluation should avoid simplistic league tables. Context matters: geography, farmer density, crop complexity, connectivity, travel distance, season stage, and project workload.

## Field-agent performance module concept

### Performance dimensions

1. Coverage

- assigned farmers;
- active farmers contacted;
- parcels/crop cycles covered;
- villages/PINs covered;
- repeat visits where required.

2. Timeliness

- time to first profile completion;
- time from field event to review/advisory;
- overdue assigned farmers;
- stale worklist items;
- response time to project tasks.

3. Completeness

- profiles completed;
- parcels with GPS/DigiPin;
- crop cycles with stage/activity evidence;
- field events with valid media;
- sync events successfully materialized.

4. Quality and auditability

- media has GPS/timestamp/hash;
- no duplicate/reused suspicious media;
- low sync failure/conflict rate after normalization for workload;
- no orphaned/invalid context submissions;
- clean assignment handoff records.

5. Outcome proxies

- advisory read/ack rates in assigned cohort;
- stage/activity progression;
- farmer retention or project continuation;
- follow-up completion after field events;
- farmer readiness improvement.

6. Risk and anomaly signals

- repeated reports from same coordinates across many farmers;
- high media reuse or suspicious media similarity;
- impossible travel patterns;
- abnormal claim/report volume;
- repeated stale-context or workflow-invalid submissions;
- many assigned farmers with no activity trail.

## Comparison examples

### Freelance agent comparison

Agent A and Agent B both support a company’s maize project.

Useful comparison:

- farmers assigned;
- farmers actively visited;
- parcel GPS completion;
- crop-cycle creation rate;
- activity logs per active crop cycle;
- field-event follow-up completion;
- advisory read/ack rate;
- evidence quality score;
- anomaly/risk flags.

Avoid unfair comparison:

- raw number of visits without geography/travel normalization;
- raw number of farmers when one agent has denser villages;
- punishing areas with poor connectivity;
- treating all crop/project complexity as equal.

### Company agronomist benchmarking

Company-employed agronomists can be compared against peers in similar geographies/crops/projects.

Metrics should be grouped by:

- project;
- crop;
- village/PIN;
- farmer density;
- assignment size;
- season stage;
- connectivity context;
- task type.

The output should be:

- coaching and assignment planning;
- workload balancing;
- escalation support;
- incentive design where appropriate.

Not:

- automatic punitive ranking;
- decontextualized productivity score;
- opaque black-box decision.

## Fraud/waste/abuse connection

Agent performance analysis also supports fraud/waste/abuse review.

Examples:

- an agent creates many claims with recycled photos;
- multiple farmers under one agent submit claims for overlapping parcels;
- an agent’s field events cluster at identical coordinates despite different villages;
- many project farmers assigned to an agent have no genuine crop-cycle trail;
- an agent repeatedly submits stale/invalid context rows that fail materialization;
- advisory or field-event follow-up is marked complete without evidence.

These are review signals, not automatic proof of misconduct.

They should feed:

- supervisor review;
- field verification;
- claim packet risk notes;
- training/coaching;
- assignment policy changes;
- temporary hold/escalation only with human review.

## Future graph analytics outputs

### Agent scorecard

- coverage;
- timeliness;
- completeness;
- evidence quality;
- farmer engagement;
- advisory follow-up;
- risk/anomaly indicators;
- comparison cohort.

### Company/project dashboard

- agent leaderboard with context-adjusted metrics;
- project coverage map;
- farmer readiness by agent;
- crop-stage progression by agent/project;
- advisory delivery/read/ack by cohort;
- field-event closure funnel;
- risk/anomaly watchlist.

### Farmer/cohort graph

- farmer-project memberships;
- assigned agents over time;
- parcel/crop-cycle/activity completeness;
- advisory exposure and acknowledgement;
- field-event history;
- claim/evidence readiness score, if an insurance module is later added.

## Data and governance requirements

Before operationalizing agent performance scoring:

- define metric formulas and normalization;
- separate employee evaluation from freelance marketplace reputation;
- obtain consent/notice for agent reputation portability;
- provide explainable metric breakdowns;
- support correction/dispute workflows;
- avoid black-box punitive scores;
- restrict sensitive views by role and company/project scope;
- audit score generation and data access.

## Landing-page framing

Safe current claim:

“AgriFabric structures agriculture operations as a connected field evidence graph across farmers, agents, companies, projects, parcels, crop cycles, media, advisories, and audit trails.”

Safe roadmap claim:

“This graph can power future field-agent performance intelligence, assignment planning, and review-assistive fraud/waste/abuse signals.”

Avoid:

- “We automatically rank all field agents.”
- “We detect fraud.”
- “We replace supervisor review.”
- “We decide claims automatically.”

## Implementation status

Implemented foundation:

- farmer/project memberships;
- field-agent worklists;
- agent reassignment lifecycle;
- FPO/project farmer search and drill-down;
- parcel/crop-cycle/activity capture;
- field events and media;
- broadcast targeting and read/ack audit;
- sync/conflict/audit trails;
- DigiPin/GPS evidence.

Not yet implemented:

- formal graph analytics API;
- field-agent performance dashboard;
- agent reputation/profile marketplace;
- fraud/risk scoring engine;
- NDVI/satellite scoring;
- supervisor review workflow for agent anomalies.

