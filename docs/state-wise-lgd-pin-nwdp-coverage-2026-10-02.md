# State-wise LGD, PIN, and NWDP coverage — 2026-10-02

## Purpose

This report combines three previously separate read-only views:

- canonical LGD village coverage;
- active matched village-to-PIN links;
- NWDP candidate and active-runtime village mappings.

The existing Geography Layer Readiness matrix reports LGD and PIN counts by
district. The NWDP Boundary Review reports source and candidate buckets by
source state. Earlier LGD/NWDP reconciliation artifacts report mapped and
unresolved NWDP populations. None previously provided a state-wise PIN × NWDP
matrix in both the LGD-to-NWDP and NWDP-to-LGD directions.

## Corrected report

The authoritative artifact is:

`data/staged/core_stack/promotion_review/20261001-state-wise-lgd-pin-nwdp-coverage-v2/state_wise_lgd_pin_nwdp_coverage.json`

Associated CSV views:

- `state_wise_lgd_pin_nwdp_lgd_centric.csv`;
- `state_wise_lgd_pin_nwdp_nwdp_centric.csv`.

Schema: `state_wise_lgd_pin_nwdp_coverage.v2`

Status: `PASSED`

The v1 artifact is diagnostic and superseded. It treated candidate
`proposed_village_id` as the only NWDP mapping and therefore excluded the
17,498-row post-LGD runtime cohort.

## Definitions

An LGD village has a PIN mapping when it has at least one active
`geography_village_pin_links` row with `match_status = MATCHED`.

Candidate NWDP mapping means the canonical village is referenced by at least
one NWDP crosswalk candidate through `proposed_village_id`.

Active runtime NWDP mapping means the canonical village is referenced by at
least one active `geography_boundary_runtime_crosswalks` row.

Effective NWDP mapping is the union of candidate mapping and active runtime
mapping. Candidate and runtime counts remain visible separately.

NWDP source-feature counts remain separate from canonical village counts
because multiple source features can resolve to one canonical village.

## National LGD-centric result

| Resolution measure | Villages |
|---|---:|
| Active LGD villages | 600,647 |
| Villages with PIN | 560,151 |
| Villages without PIN | 40,496 |
| Villages with candidate NWDP mapping | 470,501 |
| Runtime-only post-LGD mapping | 17,498 |
| Villages with any effective NWDP mapping | 487,999 |
| Villages without effective NWDP mapping | 112,648 |
| Villages with active NWDP runtime | 467,397 |

The mutually exclusive village-resolution classes are:

| Resolution status | PIN | Effective NWDP | Villages |
|---|---|---|---:|
| `FULLY_RESOLVED` | Present | Present | 454,996 |
| `PIN_ONLY` | Present | Missing | 105,155 |
| `NWDP_ONLY` | Missing | Present | 33,003 |
| `UNRESOLVED` | Missing | Missing | 7,493 |

These four counts sum exactly to 600,647.

## NWDP-centric result

| Measure | Source features |
|---|---:|
| NWDP source features | 654,285 |
| Candidate-level LGD mapping | 474,558 |
| Runtime-only LGD mapping | 17,498 |
| Any effective LGD mapping | 492,056 |
| No effective LGD mapping | 162,229 |
| Effective mapping to LGD village with PIN | 459,053 |
| Effective mapping to LGD village without PIN | 33,003 |
| Active runtime features | 467,397 |

## Post-LGD lineage correction

The runtime/candidate lineage partition is exact:

- 449,899 active runtime villages overlap candidate
  `proposed_village_id`;
- 17,498 active runtime villages are mapped through runtime crosswalks but not
  candidate `proposed_village_id`;
- 20,602 candidate-mapped villages are not active runtime villages.

The 17,498 runtime-only rows exactly match the completed post-LGD activation
cohort. Effective mapping must therefore include runtime crosswalks.

## Admin visibility

The current Geography Layer Readiness page shows district-level LGD, PIN,
candidate, and runtime aggregates. NWDP Boundary Review shows candidate-level
queues. Neither currently exposes a canonical village-level combined
resolution status.

The implemented read-only admin view uses the existing state and district
filters and classifies each canonical village as:

- `FULLY_RESOLVED`;
- `PIN_ONLY`;
- `NWDP_ONLY`;
- `UNRESOLVED`.

It must expose PIN codes, candidate-mapping presence, active-runtime presence,
effective mapping, village LGD code, and hierarchy context. Results must be paginated;
the endpoint must never return the entire 600,647-row population in
one response.

The admin endpoint is GET /api/v1/master-data/geography/village-resolution. It requires AdminPermission.VIEW, accepts state, optional district and resolution-status filters, and bounds pages to at most 200 rows. The Geography Layer Readiness page exposes the four summary classes and the paginated village table while keeping candidate and active-runtime evidence separate.

The corrected report is reproducible from the repository root with:

    venv/bin/python backend/scripts/report_state_wise_lgd_pin_nwdp_coverage.py --output-dir /tmp/state-wise-lgd-pin-nwdp-coverage-v2

Generated report data is review evidence and is intentionally not committed; the reusable read-only generator, static contract, endpoint, UI, and this definition document are the maintained artifacts.

## Safety boundary

This report and planned admin view are read-only. They do not:

- alter canonical LGD geography;
- add, remove, or modify PIN links;
- activate or promote NWDP candidates;
- modify runtime features or crosswalks;
- create project-boundary matches;
- change Android behavior;
- change lookup enablement or access authorization.
