# Geography layer readiness and enablement roadmap

Status date: 2026-09-04

## Executive decision

Use backend LGD and LGD village-to-pin-code mapping as the canonical runtime geography layer for Android, farmer onboarding, land profiles, and village/pin-code lookup.

Keep NWDP village boundaries and NWDP demographic profiles as admin/web layers unless a separate reviewed runtime promotion is completed. Farmers and agents do not need raw NWDP demographic attributes in Android, and Android behavior must not change as a side effect of geography enrichment.

For boundaries, BharatAtlas is the current operational development/review geometry source because it is LGD-keyed and mostly aligns with backend LGD. Survey of India ABDB remains an official reference source, but the current staged extract is not safe for direct LGD joins without a reviewed crosswalk because prior audits found severe district LGD/name mismatches.

## Current proof points

Latest committed baseline:

- bfe17fb test: update nwdp demographic regressions for full admin rollout
- NWDP BOUNDARY REGRESSION RUNNER PASSED
- NWDP DEMOGRAPHIC ANDROID NON-REGRESSION GUARD PASSED
- nwdp_boundary_regressions_exit=0

The current database layer matrix was generated as geography_layer_matrix.v2 with healthy=true.

## Readiness matrix

| Layer | Current state | Runtime / Android | Admin / web | Next action |
| --- | --- | --- | --- | --- |
| LGD spine | 35 states/UTs, 778 districts, 7,061 blocks, 576,083 villages | Ready | Ready | Keep as canonical geography identity. |
| Village pin codes | 560,316 active matched village-pin links; 165,617 postal references | Ready | Ready | Add periodic freshness/audit reporting. |
| NWDP demographics | 453,036 rows; 450,026 approved/active/promoted; 1,570 blocked; 0 remaining eligible | Keep disabled | Ready | Admin/web preview only; expose blocked duplicate diagnostics. |
| NWDP/GSI boundary staging | 654,285 source features and 654,285 candidates | Not broadly ready | Ready for review | Build state/district layer matrix and project matching workflow. |
| Boundary runtime | 1 runtime set, 10 runtime features, 10 runtime crosswalks | Pilot only | Pilot verification | Keep runtime lookup disabled until reviewed promotion/rollback exists. |
| Project boundary matches | 0 project matches | Not ready | Preview/read model only | Implement dry-run, review, and guarded apply. |
| Climate/agro-ecology | 50 regions, 2,489 mappings, 45 crop-climate rules, 1 override | Partially seeded | Ready for coverage audit | Audit mapped/unmapped geography and crop-season rule gaps. |
| SOI ABDB | Official reference, but staged extract has high LGD/name mismatch | Not safe for direct runtime joins | Reference/review only | Build SOI-to-backend-LGD crosswalk and compare with BharatAtlas. |
| BharatAtlas | Operational LGD-like boundary source | Not authoritative by itself | Useful for review/overlay | Use with provenance caveats and review gates. |
| External APIs/providers | Audit scripts exist, not proven by this geography run | Unknown | Needs readiness console | Run provider/integration audits and add to enablement matrix. |

## LGD and pincode layer

LGD remains the spine of the application. It should drive:

- farmer profile geography
- agent/farmer village selection
- land profile village and pin-code mapping
- backend joins across administrative layers
- Android-facing lookup responses

The current matrix shows all 560,316 village pin-code links as active and matched. This layer is fit for Android and farmer workflows.

## NWDP demographic profile layer

The demographic rollout is complete for admin/web purposes.

Final accepted baseline:

- profile rows: 453,036
- active/promoted rows: 450,026
- approved rows: 450,026
- blocked duplicate-safe exclusions: 1,570
- remaining eligible rows: 0

Earlier intermediate reports may show 451,596 approved and 1,570 remaining eligible after duplicate-safe promotion. That state was superseded by duplicate-blocked cleanup. The final accepted baseline is the Android non-regression guard state: 450,026 approved/promoted and 0 remaining eligible.

The 1,570 blocked rows are intentionally not promoted. The remaining-eligible audit confirmed all 1,570 were blocked by active promoted duplicates and that 0 still-safe candidates remained.

This layer should stay read-only admin/web. Do not enable it for Android runtime lookup.

## NWDP boundary layer

The boundary layer is staged and reviewable, but not broadly runtime-promoted.

Candidate buckets:

| Bucket | Rows | Meaning |
| --- | ---: | --- |
| DIRECT_VLCODE_MATCH | 453,046 | Best future review/promotion class. |
| BLOCKED_SOURCE_CAVEAT | 97,276 | Exclude until source caveat is resolved. |
| PARENT_MATCH_VILLAGE_UNRESOLVED | 77,022 | Parent matches, village unresolved. |
| DIRECT_VLCODE_PARENT_MISMATCH | 18,484 | Needs review due parent hierarchy conflict. |
| SPECIAL_REFERENCE_FEATURE | 5,258 | Reference only unless separately classified. |
| DISTRICT_SCOPED_AMBIGUOUS | 1,971 | Too broad for village runtime use. |
| PARENT_SCOPED_NAME_MATCH | 1,025 | Review candidate, not automatic. |
| DISTRICT_ONLY_UNRESOLVED | 171 | Unresolved below district. |
| PARENT_SCOPED_NAME_AMBIGUOUS | 32 | Manual review only. |

Review statuses:

| Status | Rows |
| --- | ---: |
| AUTO_CANDIDATE | 453,036 |
| BLOCKED | 102,534 |
| MANUAL_REVIEW | 98,705 |
| APPROVED_FOR_PROMOTION | 10 |

All 654,285 boundary candidates remain NOT_PROMOTED. Runtime has only a tiny pilot: 1 runtime set, 10 features, and 10 crosswalks. Project matches are 0.

This means the boundary layer is ready for admin inspection and matching workflows, but not ready for broad Android/runtime spatial matching.

## Climate, ecology, and biosphere layers

The current climate/agro-ecology layer is seeded but not fully enabled:

- climate regions: 50
- geography climate mappings: 2,489
- crop-climate suitability rules: 45
- crop-climate suitability overrides: 1

Before these layers drive recommendations or advisories, the admin UI should show:

- mapped vs unmapped states/districts/blocks/villages/pin codes
- mapping scope level
- confidence and source references
- crop-season-region rule coverage
- missing rules by crop, season, and geography
- overrides and review status

## SOI and BharatAtlas posture

Existing policy docs remain valid:

- docs/core-lgd-boundary-source-policy.md
- docs/bharatlas-boundary-source-review.md
- docs/survey-of-india-boundary-source-review.md

Operational posture:

1. Backend LGD remains canonical for names/codes.
2. BharatAtlas is the current operational geometry source for development and overlay review.
3. SOI is official and should remain a reference/review source.
4. The current SOI extract is not safe for automatic direct LGD joins.
5. No source should become runtime-active without reviewed promotion, provenance, and rollback.

## Admin UI enablement target

Build an admin geography layer matrix, filterable by state and district. Each row should show:

- LGD district/village counts
- village pin-code coverage
- NWDP demographic profile, active/promoted, blocked, and remaining eligible counts
- NWDP boundary candidate counts by bucket
- NWDP boundary review status counts
- promoted runtime boundary count
- project boundary match count
- climate/agro-ecology mapping coverage
- crop-climate suitability rule coverage
- SOI/BharatAtlas caveats
- external provider readiness where applicable

Suggested endpoint:

GET /api/v1/admin/geography/layer-readiness

Suggested filters:

- state_or_ut
- district
- layer
- status
- limit
- offset

The endpoint must be read-only and must not promote, import, activate, enable runtime lookup, or change Android behavior.

## External APIs and broader enablement

The geography matrix should become part of a wider admin readiness console. Existing audit scripts suggest these domains also need visibility:

- provider/live integration readiness
- product catalog readiness
- product source verification readiness
- language/localization readiness
- workflow/BBCH/crop-system readiness
- season and land-unit readiness
- metadata readiness
- web UI auth readiness
- Android emulator persona readiness

The admin should be able to answer: for this tenant/project/state/district, what is enabled, what is matched, what is unmatched, what is blocked, and what is safe to use in Android/runtime?

## Recommended implementation sequence

1. Keep this document as the committed baseline.
2. Formalize a read-only state/district geography layer matrix script that emits JSON and CSV.
3. Add GET /api/v1/admin/geography/layer-readiness as a read-only backend endpoint.
4. Add a web admin page for cross-layer geography readiness and drilldowns.
5. After the matrix is reliable, implement promotion/apply workflows for:
   - climate/agro-ecology coverage
   - project boundary matching
   - selected boundary runtime promotion
   - external API readiness activation

Each apply must have dry-run, explicit policy flag, audit JSON/CSV, rollback/supersession plan, and no Android behavior change unless specifically intended.

## Current conclusion

The application is ready to use LGD and village pin-code geography for Android/runtime workflows.

NWDP demographic profiles are ready for admin/web preview only.

NWDP boundary, climate/ecology/biosphere, project boundary matching, SOI/BharatAtlas reconciliation, and external API enablement still need read-only cross-layer visibility before they should be broadly promoted into runtime application behavior.
