# NWDP Karnataka boundary crosswalk candidate plan

Status date: 2026-08-21

This document records the read-only candidate plan for mapping NWDP/GSI Karnataka village-boundary features to backend LGD geography.

No database rows were written.

## Command

Run from backend:

    ../venv/bin/python scripts/plan_nwdp_karnataka_boundary_crosswalk_candidates.py --json-output /tmp/nwdp-karnataka-boundary-crosswalk-candidates.json --csv-output /tmp/nwdp-karnataka-boundary-crosswalk-candidates.csv

Outputs:

    /tmp/nwdp-karnataka-boundary-crosswalk-candidates.json
    /tmp/nwdp-karnataka-boundary-crosswalk-candidates.csv

## Latest result

Summary:

- source records: 29,789;
- planned candidate rows: 29,789;
- backend districts loaded: 778;
- backend blocks loaded: 7,061;
- backend villages loaded: 576,083;
- backend village LGD codes loaded: 576,082;
- backend census village codes loaded: 0.

## Candidate buckets

| Bucket | Count | Meaning |
| --- | ---: | --- |
| `DIRECT_VLCODE_MATCH` | 23,196 | Source `vlcode` directly matched backend `geography_villages.lgd_code` and parent geography was consistent. |
| `DIRECT_VLCODE_PARENT_MISMATCH` | 1,063 | Source `vlcode` matched a backend village code, but parent district/block consistency failed. Manual review required. |
| `PARENT_MATCH_VILLAGE_UNRESOLVED` | 4,388 | District/subdistrict/block parent geography matched, but village code/name did not resolve. |
| `DISTRICT_SCOPED_AMBIGUOUS` | 626 | District-level name match exists, but lower-level geography is ambiguous. |
| `PARENT_SCOPED_NAME_MATCH` | 233 | Parent-scoped normalized village name matched exactly. Manual review candidate. |
| `PARENT_SCOPED_NAME_AMBIGUOUS` | 28 | Parent-scoped name matched multiple backend candidates. Manual review required. |
| `SPECIAL_REFERENCE_FEATURE` | 255 | Non-village/special features such as river/reservoir/beat/plantation or source code patterns such as `999999`. |

## Review status summary

| Review status | Count |
| --- | ---: |
| `AUTO_CANDIDATE` | 23,196 |
| `MANUAL_REVIEW` | 6,593 |

## Confidence summary

| Confidence | Count |
| --- | ---: |
| `NWDP_DIRECT_VLCODE` | 23,196 |
| `NWDP_DIRECT_VLCODE_PARENT_MISMATCH` | 1,063 |
| `NWDP_PARENT_ONLY_VILLAGE_UNRESOLVED` | 4,388 |
| `NWDP_DISTRICT_ONLY_AMBIGUOUS` | 626 |
| `NWDP_PARENT_SCOPED_NAME` | 261 |
| `NWDP_SPECIAL_REFERENCE_FEATURE` | 255 |

## Proposed scope summary

| Scope | Count |
| --- | ---: |
| `village` | 24,259 |
| `district_subdistrict` | 4,388 |
| `district_review` | 626 |
| `village_review` | 261 |
| `district_subdistrict_reference_only` | 255 |

Important: `village` scope includes `DIRECT_VLCODE_PARENT_MISMATCH` rows. Those rows must remain manual review and must not be treated as effective village assignments.

## Interpretation

The planner confirms that NWDP Karnataka can support a high-confidence inactive candidate set, but not automatic ingestion.

A conservative import design should:

- stage `DIRECT_VLCODE_MATCH` rows as inactive `AUTO_CANDIDATE`;
- stage all other rows as inactive `MANUAL_REVIEW`;
- block runtime point-in-polygon use until promotion;
- preserve backend LGD master as identity source of truth;
- keep NWDP/SOI geometry as reference boundary geometry, not cadastral truth.

## Decision

Proceed to importer design only as a dry-run/manual-review candidate importer.

Do not activate any boundary mapping automatically.
Do not use unresolved records for village assignment.
Do not expose runtime spatial matching until crosswalk review and promotion semantics exist.
