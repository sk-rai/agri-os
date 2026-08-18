# AgriFabric geography and DigiPin visual spec

Status date: 2026-08-18

This spec defines the geography/DigiPin visual language for the landing page, demo videos, and investor/product materials. The goal is to explain the location model clearly: AgriFabric separates administrative geography, postal reference, coordinate evidence, parcel geometry, DigiPin precision, and enrichment/analytics layers.

Source docs:

- `docs/digipin-location-architecture.md`
- `docs/geography-enrichment-analytics-model.md`
- `docs/global-geography-model-roadmap.md`
- `docs/geography-data-source-contract.md`
- `docs/android-digipin-gps-materialization-test.md`
- `docs/android-land-intelligence-summary-screen-test.md`
- `docs/landing-page-wireframe.md`
- `docs/demo-asset-inventory.md`

## Primary message

Use this as the main caption:

```text
AgriFabric keeps location layers separate: administration, postal reference, GPS/parcel evidence, DigiPin precision, and land intelligence.
```

Short version for small overlays:

```text
PIN is context. GPS and DigiPin are precision evidence.
```

## Claim boundary

The visual can show:

- India-compatible LGD/PIN/GPS/DigiPin foundation;
- backend-owned geography lookup and validation;
- DigiPin generated from captured coordinates;
- parcel-friendly location evidence;
- land-intelligence cards as informational guidance;
- future support for soil, weather, Census, satellite, and global geography.

The visual must not imply:

- DigiPin is preloaded for every PIN code;
- Android computes canonical DigiPin;
- PIN code is precise parcel location;
- live village geocoding is implemented;
- global geography coverage is complete;
- live weather/soil provider calls are demo-safe;
- NDVI/EVI satellite analysis is implemented.

Recommended boundary label:

```text
India-compatible MVP now. Global geography, live providers, and satellite analytics are roadmap or approval-gated.
```

## Visual style

Tone:

- layered;
- map-aware;
- precise but not technical-heavy;
- evidence-oriented.

Recommended style:

- stacked layer diagram;
- small map/grid card;
- parcel shape outline;
- DigiPin as a precise pin/cell;
- clear “backend-owned” badge near generation/validation.

Avoid:

- showing PIN as a single point;
- showing village as a parcel boundary;
- mixing Census/postal/LGD as if they are the same source;
- implying automatic live data ingestion during demo.

## Core visual model

Use a layer stack:

```text
Country / state / district / block / village
  + PIN postal reference
  + GPS point or parcel polygon
  + DigiPin derived from coordinates
  + land-intelligence guidance
  + future enrichment: weather / soil / Census / satellite
```

Landing-page copy:

```text
AgriFabric separates broad address context from precise field evidence. LGD identifies administrative geography. PIN narrows postal/reference context. GPS and parcel geometry identify the physical location. DigiPin is generated from coordinates. Land intelligence stays backend-owned and informational.
```

## Layer definitions

### Layer 1 — Administrative geography

Label:

```text
LGD administrative hierarchy
```

Examples:

- state;
- district;
- sub-district/block/tehsil/taluk;
- village/locality;
- LGD codes.

Purpose:

- official operational grouping;
- project geography scope;
- farmer/parcel administrative identity;
- reporting and source reconciliation.

Status:

India-compatible foundation.

Visual treatment:

- broad region outline;
- hierarchy chips;
- blue “canonical admin source” badge.

Do not say:

- Census or postal names overwrite LGD identity.

### Layer 2 — PIN/postal reference

Label:

```text
PIN postal reference
```

Purpose:

- PIN-code validation;
- candidate village/locality lookup;
- postal office metadata;
- delivery/non-delivery hints;
- broad address context.

Status:

Foundation / source-refresh dependent.

Visual treatment:

- translucent postal zone overlay;
- many-to-many connector from PIN to multiple village/locality candidates.

Do not say:

- PIN identifies a parcel.
- one PIN equals one village.
- DigiPins are preloaded per PIN.

### Layer 3 — GPS and parcel geometry

Label:

```text
GPS / parcel evidence
```

Purpose:

- physical location evidence;
- farmer home coordinate when captured;
- parcel centroid/polygon;
- plot-resolution-friendly capture;
- future spatial grouping and proximity analysis.

Status:

Verified MVP foundation.

Visual treatment:

- parcel polygon outline;
- centroid point;
- phone GPS capture marker;
- small “captured in field” label.

Do not say:

- GPS is always required.
- manual village/PIN entry is enough for parcel precision.

### Layer 4 — DigiPin

Label:

```text
DigiPin from coordinates
```

Purpose:

- precise coordinate-derived digital address;
- farmer home precision when enrollment GPS exists;
- parcel centroid precision when parcel coordinates exist;
- future nearest-service and duplicate/overlap review.

Status:

Verified MVP foundation.

Visual treatment:

- small grid cell around coordinate point;
- “backend generated” badge;
- algorithm/version/timestamp callout if needed in technical assets.

Do not say:

- Android computes canonical DigiPin.
- DigiPin can be guessed from PIN, village, district, or text address.
- DigiPin replaces LGD/PIN/GPS/parcel geometry.

### Layer 5 — Land intelligence

Label:

```text
Backend-owned land intelligence
```

Purpose:

- project/PIN/season/crop summary cards;
- crop options and caveats;
- informational guidance during onboarding;
- company/FPO-editable overrides when configured.

Status:

Verified MVP for backend-owned informational summary cards.

Visual treatment:

- card overlay attached to parcel/PIN context;
- “informational only” badge;
- “do not block onboarding” chip.

Do not say:

- land intelligence automatically determines farmer eligibility;
- live provider data is currently demo-safe;
- Android computes the summary locally.

### Layer 6 — Future enrichment

Label:

```text
Future enrichment
```

Examples:

- weather;
- soil;
- Census;
- satellite NDVI/EVI;
- global geography profiles;
- village coordinate geocoding.

Status:

Roadmap or approval-gated.

Visual treatment:

- dashed outer ring;
- amber/purple roadmap badge;
- no filled “live” treatment.

Do not say:

- NDVI/EVI analysis is implemented;
- live weather/soil calls are enabled for demo;
- global geography is fully live.

## Recommended landing-page layout

Desktop:

```text
┌──────────────────────────────┬───────────────────────────────┐
│ Copy block                    │ Layered map/stack visual       │
│ - LGD = admin identity        │                               │
│ - PIN = postal context        │  Admin boundary                │
│ - GPS/parcel = field evidence │    + PIN zone                  │
│ - DigiPin = coordinate cell   │       + parcel polygon         │
│ - Land intelligence = guidance│          + DigiPin cell        │
└──────────────────────────────┴───────────────────────────────┘
```

Mobile:

- Render as stacked cards:
  1. Administrative geography.
  2. PIN/postal reference.
  3. GPS/parcel.
  4. DigiPin.
  5. Land intelligence.
  6. Future enrichment.

## Highlighted paths

### Path 1 — Address context to precise evidence

```text
PIN / village context → GPS point → DigiPin
```

Caption:

```text
The app can start with familiar address context, but precision comes from captured coordinates.
```

Status:

Verified foundation.

### Path 2 — Parcel-resolution evidence

```text
Parcel polygon or centroid → backend validation → parcel DigiPin
```

Caption:

```text
Parcel evidence can be represented as a point or polygon, with DigiPin generated from the coordinate.
```

Status:

Verified foundation.

### Path 3 — Project land-intelligence guidance

```text
Project + PIN + season + crop → backend summary → Android informational card
```

Caption:

```text
Backend-owned land intelligence can guide onboarding without blocking the farmer workflow.
```

Status:

Verified MVP.

### Path 4 — Future risk and enrichment layer

```text
Parcel/GPS/DigiPin + crop cycle + future weather/soil/satellite → review-assistive intelligence
```

Caption:

```text
The same location evidence can later support risk review, provider enrichment, and satellite time-series checks.
```

Status:

Roadmap / approval-gated.

## Color and badge system

Recommended colors:

```text
Administrative geography: blue
PIN/postal reference: cyan
GPS/parcel evidence: green
DigiPin precision: teal
Land intelligence: indigo
Future enrichment: amber or purple dashed
Claim boundary: amber outline
```

Badge labels:

- LGD admin identity
- Postal reference
- Field-captured coordinate
- Backend-generated DigiPin
- Informational only
- Roadmap / approval-gated

## SVG-ready coordinate sketch

Use this as a first static SVG layout guide. Coordinates assume a 1200 × 720 viewBox.

| Element | x | y | width | height | Treatment |
| --- | ---: | ---: | ---: | ---: | --- |
| Admin region outline | 120 | 90 | 760 | 500 | Soft blue boundary |
| PIN zone | 250 | 180 | 520 | 320 | Translucent cyan blob |
| Village/locality chips | 170 | 120 | 220 | 44 | Blue chips |
| Parcel polygon | 440 | 310 | 220 | 150 | Green polygon |
| Parcel centroid point | 550 | 385 | 18 | 18 | Green dot |
| DigiPin grid cell | 525 | 360 | 54 | 54 | Teal square/grid |
| Phone GPS marker | 650 | 270 | 60 | 90 | Small phone/pin |
| Land intelligence card | 820 | 230 | 280 | 190 | Indigo card |
| Future enrichment ring | 80 | 60 | 1040 | 600 | Amber dashed outer ring |
| Boundary label | 820 | 455 | 280 | 90 | Amber outline callout |

Suggested connectors:

```text
Village/locality chips -> PIN zone
PIN zone -> Parcel polygon
Phone GPS marker -> Parcel centroid point
Parcel centroid point -> DigiPin grid cell
DigiPin grid cell -> Land intelligence card
Parcel polygon -> Future enrichment ring
Land intelligence card -> Boundary label
```

## Copy blocks for the geography section

### Option A — concise

```text
AgriFabric keeps geography layers separate. LGD defines administrative identity, PIN gives postal context, GPS and parcel geometry provide physical evidence, and DigiPin is generated from coordinates. Land intelligence is backend-owned and informational.
```

### Option B — more explanatory

```text
A PIN code is useful, but it is not a plot. AgriFabric uses PIN and village data as reference context, then uses GPS, parcel geometry, and backend-generated DigiPin for precise field evidence. This lets projects keep clean administrative reporting without losing plot-level resolution.
```

### Option C — roadmap-aware

```text
The same model can grow beyond India. Today the MVP supports India-compatible LGD/PIN/GPS/DigiPin flows. Tomorrow, country-specific geography profiles, provider-gated weather and soil signals, and satellite time-series evidence can attach to the same location foundation.
```

## Demo overlay labels

Use these labels in short videos:

```text
LGD admin identity
PIN postal context
Candidate village lookup
GPS captured in field
Parcel centroid / polygon
Backend-generated DigiPin
Land intelligence card
Informational only
Roadmap: live weather/soil
Roadmap: NDVI time series
Roadmap: global geography profile
```

## Overseas/generalized geography variant

Use a separate small visual when explaining overseas readiness.

Message:

```text
The current MVP is India-compatible, but the model can generalize by making geography levels country-specific instead of hardcoding state/district/block/village everywhere.
```

Generic hierarchy examples:

```text
Country → Province → District → Municipality → Village
Country → State → County → Sub-county → Parish
Country → Region → Department → Commune
Country → Province → Regency → District → Village
```

Visual:

```text
Country profile
  → level definitions
  → source identifiers
  → postal-code links
  → aliases/translations
  → operational groupings
```

Claim boundary:

```text
Generic global geography is a documented architecture path, not a completed rollout.
```

## Accessibility requirements

- Do not rely only on color to distinguish layer roles.
- Use labels and badges for each layer.
- Ensure the DigiPin cell is visibly different from the broad PIN zone.
- Keep text large enough for mobile.
- Provide alt text:

```text
Layered geography visual showing LGD administrative hierarchy, PIN postal reference, GPS and parcel geometry, backend-generated DigiPin precision, backend-owned land-intelligence guidance, and dashed future enrichment layers for weather, soil, Census, satellite, and global geography.
```

## Acceptance checklist

Before using the visual publicly:

- PIN is shown as broad postal/reference context, not parcel precision.
- DigiPin is shown as coordinate-derived and backend-generated.
- LGD/admin geography remains separate from postal and Census/reference layers.
- Land intelligence is marked informational and non-blocking.
- Future weather/soil/satellite/global geography layers are visibly roadmap or approval-gated.
- The visual supports both landing page and demo-video overlay use.

