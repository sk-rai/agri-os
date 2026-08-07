# CoRE/LGD Boundary Source Policy

Status date: 2026-08-07

This document records the current source hierarchy for CoRE polygon-to-LGD district mapping.

## Source roles

| Role | Source | Treatment |
| --- | --- | --- |
| Canonical administrative identity | Backend LGD master | Source of truth for `state_lgd_code`, `district_lgd_code`, canonical district/state identity |
| Operational district polygon lookup | BharatAtlas LGD district layer | Current working geometry source for CoRE overlay review, because it is LGD-keyed and mostly aligns with backend LGD |
| Official geometry/reference | Survey of India ABDB | Official geometry reference; useful for comparison, but current extracted `DIST_LGD` values are not safe as direct backend LGD keys |

## BharatAtlas position

BharatAtlas is not an official government source. It is an open/community republication.

However, the staged BharatAtlas district layer is operationally useful because:

- it provides 785 district features;
- it has LGD-like `dist_lgd` / `state_lgd` attributes;
- it aligns with backend LGD master for most districts;
- it can support dry-run/manual-review CoRE overlay candidate generation.

Known issue:

- LGD `766` maps to `Mauganj`, Madhya Pradesh in backend/current LGD evidence.
- BharatAtlas maps `766` to `Itanagar Capital Complex`, Arunachal Pradesh.
- This should be treated as a BharatAtlas source/attribute error and excluded/overridden.

## Survey of India ABDB position

Survey of India ABDB is official and valuable as a geometry reference.

Local metadata identifies the district boundary dataset as:

    SOI/ABDB/VECTOR/50000/2025/DISTRICT/INDIA

with publication date:

    2026-05-06

The metadata credits Survey of India and describes administrative boundary harmonization with ORGI.

However, local attribute audits show the current extracted district shapefile is not safe as a direct LGD-keyed source:

- district layer record count: 808;
- invalid/disputed district LGD rows: 31;
- only 2 rows match backend by both name and code;
- 565 rows have `DIST_LGD` values that point to a different backend district;
- examples include:
  - SOI `DADRA AND NAGAR HAVELI` with `DIST_LGD=496`, while backend LGD `496` is `Solapur`;
  - SOI `DAMAN` with `DIST_LGD=495`, while backend LGD `495` is `Sindhudurg`;
  - SOI `DIU` with `DIST_LGD=494`, while backend LGD `494` is `Satara`;
  - encoded names such as `B>NKURA`, `PASCHIM MEDIN|PUR`, and `K>LIMPONG`.

Important distinction:

- `DIST_LGD` appears intended to represent LGD district code.
- But the values populated in the current SOI ABDB extract are unreliable for direct backend joins.

Encoding issues may explain garbled names, but cannot explain numeric LGD codes pointing to unrelated districts.

## Current pipeline decision

For the current CoRE overlay pipeline:

1. Backend LGD master remains canonical for administrative identity.
2. BharatAtlas remains the current operational LGD-keyed geometry source.
3. SOI ABDB remains official reference geometry, not direct import key source.
4. SOI should be used later through a reviewed crosswalk:
   - normalized state/district name;
   - backend LGD identity;
   - spatial comparison against BharatAtlas;
   - manual review for ambiguous/split/version-drift cases.

## Import policy

No polygon-derived mapping should become active automatically.

Any importer must:

1. write only candidate rows with `review_status=MANUAL_REVIEW`;
2. write rows as inactive / not effective in land intelligence;
3. exclude source-version drift, state-code mismatch, and missing backend district rows;
4. preserve all existing fallback mappings;
5. require explicit later review/promotion before changing web or Android behavior.

## Android / web impact

No Android Maestro flow is required for source-policy work.

Android and web behavior only need testing after backend `land-intelligence-context` output changes.
