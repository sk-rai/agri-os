# Village resolution evidence review pilot — 2026-10-04

## Purpose

The first human review exercise is a frozen ten-row pilot. It tests whether the
available local evidence is sufficient for two independent administrators to
reach defensible decisions. It does not authorize or apply canonical mappings.

## Selection policy

The pilot builder selects exactly ten active-snapshot rows that:

- are `TWO_SESSION_REVIEW_ELIGIBLE`;
- have match rank 1;
- retain their prior evidence disposition for reviewer context rather than using
  it as an eligibility gate;
- do not already have a review record.

Rows are ordered deterministically by evidence strength, LGD hierarchy codes,
village code, and source feature identity. The manifest records the snapshot
identity and both upstream source hashes.

The prior disposition does not mean that the row is automatically safe to
apply. It only makes the row suitable for this bounded human review pilot.

## Review evidence

Each row contains:

- canonical state, district, block, village name, and LGD codes;
- NWDP source state, district, subdistrict, block, village, and source code;
- match rank and match basis;
- evidence disposition and prior candidate evidence;
- source reuse count and collision status;
- snapshot identity and source hashes.

All primary and second-review decision fields start blank.

## Safety boundary

Building the pilot:

- creates no review decision;
- performs no database write;
- changes no canonical village;
- changes no PIN link;
- changes no runtime crosswalk;
- changes no project geography;
- changes no Android behavior;
- authorizes no automatic application.

The ten rows still require human review through the existing two-session admin
workflow. An approved review remains evidence only and is not an applied
mapping.

## Generated artifacts

The builder writes:

- `village_resolution_evidence_review_pilot.csv`;
- `village_resolution_evidence_review_pilot.json`.

Generated pilot artifacts are local review evidence and must not be committed.
Only the reproducible builder, static contract, and this definition document
belong in source control.

## Validation

- `backend/scripts/report_village_resolution_evidence_review_pilot.py`
- `backend/scripts/test_village_resolution_evidence_review_pilot_static.py`
