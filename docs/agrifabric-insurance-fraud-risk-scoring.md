# AgriFabric insurance fraud, waste, abuse, and claim-risk scoring

Status date: 2026-08-15

This note captures a future product positioning and architecture direction for AgriFabric as an agriculture insurance and subsidy integrity layer. It is not an implementation commitment. The goal is to describe how the field data already captured through Android, admin workflows, parcel mapping, media evidence, crop cycles, and sync audit trails can support fraud/waste/abuse detection and claim-risk scoring.

## Positioning

AgriFabric can be positioned as a field evidence fabric for agriculture insurance, credit, subsidy, and relief programs.

Instead of relying only on uploaded documents or claim forms, insurers and program administrators can cross-check claims against a living operational record:

- farmer identity and app/device usage;
- parcel and plot mapping;
- crop-cycle declarations;
- stage and activity logs;
- field-event reports;
- geo-tagged media;
- DigiPin and GPS-derived location evidence;
- weather and soil context;
- satellite time-series signals;
- sync/audit history.

The system should be described as review-assistive and fraud-resistant, not as an automatic fraud judge. A risk score should trigger review, field verification, or extra documentation; it should not by itself deny a genuine farmer claim.

## Public fraud patterns this can address

Recent crop-insurance and compensation reports show recurring abuse patterns that AgriFabric is structurally suited to flag:

- land insured without owner consent;
- forged tenant certificates or lease documents;
- false crop declarations, such as one crop insured while another crop is actually cultivated;
- fake or manipulated land ownership and tenancy records;
- repeated use of the same crop-damage photo across claims;
- claims linked to ineligible, inactive, or deceased identities;
- abnormal behavior by intermediaries, agents, CSC operators, surveyors, or field officials;
- questionable crop-loss assessment or documentation trails.

AgriFabric should not replace statutory insurance, revenue, or KYC systems. Its role is to add a field-verifiable evidence layer that helps detect inconsistencies earlier.

## Insurance-enforced app workflow

If an insurer or government program requires participating farmers, FPOs, agents, or surveyors to use a registered AgriFabric app, the claim can be linked to an auditable field trail:

1. Farmer is onboarded under a tenant, project, or insurer program.
2. Farmer identity, mobile, device, and project enrollment are linked.
3. Parcel is captured with GPS polygon, centroid, DigiPin/address context, and project association.
4. Crop cycle is declared with crop, season, sowing date, and expected harvest window.
5. Field activities and crop-stage changes are logged during the season.
6. Field events or damage claims require fresh geo-tagged media and metadata.
7. Backend generates an evidence bundle and risk flags for the insurer.

The resulting claim packet can include:

- farmer id and policy/program reference;
- parcel id, boundary, centroid, and DigiPin;
- crop cycle id, crop code, season, stage status, and timeline;
- field event id and damage category;
- media asset ids, hashes, capture metadata, and GPS proximity;
- sync event ids and audit entries;
- risk score, risk reasons, and recommended review action.

## Core risk flags

### Same parcel claimed by multiple farmers

If the same parcel polygon or parcel id appears under two farmers in the same season, crop, or claim window, AgriFabric should flag it.

This should be treated as a review signal, not automatic fraud. Valid explanations may include tenancy, family cultivation, shared ownership, or delayed record updates. The system should ask for supporting tenancy/owner confirmation and route high-risk overlaps for review.

### Crop mismatch

The declared insured crop should be compared with:

- app crop cycle;
- field activity logs;
- crop-stage timeline;
- field photos;
- FPO/project crop scope;
- satellite time-series evidence.

Example:

`	ext
Insured crop: chana
App crop cycle: maize
Field activities: maize stage and input logs
Satellite curve: Kharif maize-like vegetation pattern
Risk flag: insured crop mismatch
`

### Duplicate or recycled damage photos

Uploaded media can be checked for:

- exact hash reuse;
- perceptual similarity reuse;
- same photo submitted for multiple farmers or villages;
- mismatched GPS metadata;
- suspiciously old capture timestamps;
- identical media used by the same agent across multiple claims.

This can catch repeated photo reuse even before deeper ML-based image analysis is added.

### Geo/time plausibility

AgriFabric can compare claim evidence against location and time:

- Was the photo captured inside or near the parcel polygon?
- Was the claim date consistent with the crop stage?
- Did the damage date align with rainfall, hail, flood, drought, or pest events?
- Did the app sync event occur much later than the claimed field capture?
- Did the same agent submit too many geographically distant claims in a short window?

### Sparse cultivation trail

A high-value claim with no prior crop-cycle activity, no stage progression, no field visit, no input logs, and no parcel evidence should receive a higher review score than a claim backed by a complete season trail.

### Agent or intermediary anomaly

The risk engine can flag:

- one agent/device associated with abnormal claim volume;
- repeated uploads from the same coordinates;
- many claims for farmers who never logged in or acknowledged enrollment;
- policy/claim creation patterns disconnected from farmer app usage.

## Parcel polygon and NDVI time-series intelligence

GPS parcel polygons unlock a powerful satellite evidence layer. Once the plot boundary is known, AgriFabric can compute a time series for that exact plot rather than relying on village-level or district-level assumptions.

Useful signals include:

- NDVI/EVI vegetation curves;
- green-up timing as a proxy for sowing window;
- peak canopy timing and duration;
- harvest or senescence drop;
- fallow versus cultivated detection;
- stress or damage signals from sudden vegetation decline;
- crop-type plausibility by comparing curves to expected crop calendars.

This changes the question from:

`	ext
What document did someone upload?
`

to:

`	ext
What does the plot itself appear to have done over the season?
`

Example:

`	ext
Claimed crop: paddy
Satellite signal: no sustained water/vegetation pattern consistent with paddy
App crop cycle: mustard
Field activities: mustard inputs
Risk flag: crop declaration mismatch
`

Another example:

`	ext
Claimed damage date: 2026-08-20
Weather event: heavy rainfall around 2026-08-18 to 2026-08-22
NDVI signal: vegetation decline after rainfall window
Photo GPS: inside parcel polygon
Risk effect: claim plausibility improves
`

The best near-term design is to expose NDVI-derived signals as evidence and risk reasons, not as final determinations. Satellite data has cloud cover, revisit, mixed-pixel, and crop-similarity limitations.

## Risk score model

Start with transparent rules before ML:

- identity risk;
- parcel overlap risk;
- crop mismatch risk;
- media reuse risk;
- geo/time plausibility risk;
- agent/intermediary anomaly risk;
- sparse cultivation trail risk;
- sync/audit anomaly risk;
- satellite time-series inconsistency risk.

Suggested outputs:

- LOW: claim has consistent field evidence; candidate for faster processing.
- MEDIUM: minor inconsistencies; desk review.
- HIGH: strong anomaly; require field verification.
- CRITICAL: severe duplication, forged-document indicators, or identity/parcel contradictions; hold for investigation.

Each score must include explainable reasons.

## Why this matters

For insurers and governments, AgriFabric can reduce leakage, false claims, duplicated claims, and weak field verification.

For genuine farmers, the same system can improve trust and speed. A claim with consistent app, parcel, media, weather, and satellite evidence should be easier to process fairly.

For FPOs and agri-enterprises, it creates a clean operational record that supports insurance, credit, compliance, advisory, and subsidy programs from the same data fabric.
