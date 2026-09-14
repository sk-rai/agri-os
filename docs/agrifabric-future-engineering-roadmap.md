# AgriFabric Future Engineering Roadmap

## Purpose

This document records feasible future product extensions identified through
competitive analysis and internal product review.

It is a deferred roadmap. It does not authorize implementation, change current
runtime behavior, or supersede active geography, boundary, workflow, Android,
or operational-governance work.

## Product boundary

AgriFabric is a configurable, backend-driven, offline-first farm operations
platform. Its core operational graph connects:

`Farmer → Parcel → Crop cycle → Crop stage → Recommendation → Activity → Input → Cost → Field event → Evidence → Outcome → Season history`

Future work should strengthen this operational graph rather than turn
AgriFabric into a generic advisory app, marketplace, hardware company, or
agricultural super-app.

## Existing capabilities

The following are existing product capabilities and must not be presented as
unimplemented future ideas:

- backend-configurable forms and crop workflows
- farmer, parcel, crop-cycle and crop-stage operations
- recommendations, activities, field events, evidence and media
- detailed stage-, activity- and input-linked cost capture
- farmer and field-agent-assisted operations
- assignment-aware authorization
- offline operation, synchronization and conflict recovery
- multi-project, multi-village and multi-tenant operation
- project and operational traceability
- immutable lifecycle and configuration history
- localization foundations
- canonical project geography using village LGD codes

## Existing capabilities needing stronger presentation

These items primarily require aggregation, visualization, demonstration, or
clearer product communication rather than a new underlying data model.

### Crop-cycle cost roll-up

Expose existing cost records through:

- total crop-cycle cultivation cost
- cost by crop stage
- cost by activity
- cost by input
- cost per acre
- planned versus actual cost
- largest cost drivers
- farmer, project and FPO-level summaries
- drill-down from totals to source activities and evidence

### Operational-history demonstration

Demonstrate one complete, understandable flow:

`Recommendation → actual activity → input → cost → field event → evidence → outcome`

Then show how the same structure scales from one farmer to an FPO, multiple
villages and multiple projects.

### Agricultural geography communication

AgriFabric has a nationwide village-level geography intelligence foundation
connecting:

- canonical village LGD codes
- village names and administrative hierarchy
- states and Union Territories
- districts and blocks/subdistricts
- PIN-code relationships and crosswalks
- village and project geography scope
- village boundary datasets and readiness classification
- demographic datasets
- climatic datasets
- ecological and biospheric datasets
- soil, terrain and land-intelligence sources where available
- source provenance, reconciliation and validation artifacts

Canonical geography and project village-scope administration are operational.
Data availability, validation, runtime eligibility, promotion and Android
enablement remain separate governance states.

Do not claim that every national layer or boundary is already fully validated,
promoted or runtime-enabled.

Preferred claim:

> AgriFabric combines field execution with a nationwide village-level
> geography foundation, connecting canonical LGD identity, PIN-code
> relationships and administrative hierarchy with progressively governed
> boundary, demographic, climatic, ecological and biospheric context.

## Feasible product extensions

These extensions fit the existing architecture but should be scheduled only
after current committed work is complete.

### 1. Harvest, sale and net realization

Extend existing cultivation-cost capture with:

- harvested quantity
- marketable, rejected and lost quantity
- quality or grade
- buyer and sale date
- quantity sold and realized price
- transport, loading and unloading
- packaging, grading and storage
- commission, mandi and transaction charges
- invoiced, received and outstanding amounts

Derived result:

`Realized revenue − cultivation cost − harvest/post-harvest cost − selling cost = net realization`

This is an extension of the existing cost architecture, not a replacement.

### 2. Operational-to-financial posting

Allow verified operations to create corresponding economic records:

- input application → input expense
- labour activity → labour cost
- machinery/service completion → service cost or payable
- harvest → output quantity
- sale → revenue or receivable
- payment → settlement

AgriFabric should remain the agricultural operational source of truth and
should not become a general-purpose accounting ERP.

### 3. Recommendation-to-outcome closure

Capture:

- recommendation accepted, modified or rejected
- execution timing and variance
- actual input and dosage
- follow-up observation
- crop response
- yield and quality
- economic result

This enables evidence-backed learning without requiring generic generative AI.

### 4. Multi-season Agricultural Memory

Progress from:

`Operational History → Agricultural Memory → Agricultural Intelligence`

Potential capabilities:

- season-over-season comparison
- cost, activity and yield trends
- comparable farmer and parcel benchmarking
- recurring risk identification
- evidence-backed recommendations

### 5. Production and harvest pipeline

Use parcel area, crop, planting date, stage and historical outcome data to
derive:

- area under each crop
- current stage distribution
- expected harvest windows
- estimated production volume
- village and FPO aggregation forecasts
- delayed or at-risk harvests

### 6. Delegated agricultural access

Extend existing assignments with:

- farmer consent
- task-specific permissions
- project and crop-cycle scope
- time-bound access
- contact masking
- economics visibility controls
- revocation and immutable access history

### 7. Voice and local-language interaction

Potential extensions:

- voice-assisted navigation
- structured dictation of observations
- recommendations read aloud
- regional-language workflow labels
- reviewable voice-to-field capture

Voice should simplify structured operations rather than create a generic
chatbot.

### 8. External evidence adapters

Define provenance-aware adapters for:

- weather
- soil tests
- IoT sensors
- satellite imagery
- drone observations
- machinery
- storage monitoring
- quality testing
- market information

External observations should attach to the appropriate tenant, project,
farmer, parcel, crop cycle, stage or field event.

## Opportunities to track without immediate implementation

- verified market-price feeds
- buyer discovery
- receivables and payment settlement
- QR and batch traceability
- procurement and logistics integration
- outbreak heatmaps
- yield forecasting
- sustainability and carbon reporting
- scheme and insurance discovery

These must not delay core geography, field execution, evidence and operational
history work.

## Out of scope for the core product

AgriFabric should not directly become:

- a generic AI advisory platform
- a broad agricultural marketplace
- a farmer-to-consumer ecommerce platform
- an export logistics platform
- an autonomous robotics or drone company
- an IoT hardware manufacturer
- a proprietary disease-diagnosis company
- an irrigation-equipment company
- a general accounting ERP
- an unrelated agricultural super-app

Physical innovations may be represented as inputs, assets, services,
activities, events or external evidence without becoming AgriFabric product
lines.

## Prioritization after current commitments

### P1 — Expose and extend existing value

1. Crop-cycle cost aggregation and drill-down.
2. Harvest, sale and net-realization records.
3. Recommendation-to-execution-to-outcome closure.
4. Multi-season operational comparison.

### P2 — Organizational intelligence

1. Production and harvest pipeline.
2. Delegated agricultural access.
3. Farmer, parcel and crop-cycle benchmarking.
4. Voice-assisted structured field entry.

### P3 — Ecosystem integration

1. External evidence adapter framework.
2. Market and downstream transaction integrations.
3. Batch and custody traceability.
4. Outcome-driven intelligence after adequate data accumulation.

## Current implementation hold

Do not begin these extensions until the currently prioritized geography,
boundary-validation, promotion-governance and related platform work is
completed or explicitly reprioritized.

Any future implementation must preserve:

- backend configurability
- offline-first behavior
- assisted operations
- tenant and project isolation
- evidence provenance
- immutable auditability
- deterministic synchronization
- the distinction between staged data and runtime-enabled behavior
