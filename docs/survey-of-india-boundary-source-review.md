# Survey of India ABDB Boundary Source Review

Status date: 2026-08-07

This document records validation of the staged Survey of India Administrative Boundary Data Base (ABDB) files.

## Source files staged locally

Files are staged under:

    data/staged/boundaries/survey_of_india/

Important local files:

    State_District_Subdistrict_PAN_INDIA.rar
    Metadata_ABDB.zip
    state_district_subdistrict_pan_india/
    metadata_abdb/

The staged source data is not committed to git.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/validate_survey_of_india_boundary_source.py

The script is read-only and does not write database rows.

## Metadata summary

Survey of India metadata identifies these datasets:

| Dataset | Metadata identifier | Publication date | Scale | Owner |
| --- | --- | --- | --- | --- |
| State boundary | `SOI/ABDB/VECTOR/50000/2025/STATE/INDIA` | 2026-05-06 | 1:50,000 | Survey of India |
| District boundary | `SOI/ABDB/VECTOR/50000/2025/DISTRICT/INDIA` | 2026-05-06 | 1:50,000 | Survey of India |
| Subdistrict boundary | `SOI/ABDB/VECTOR/50000/2025/SUBDISTRICT/INDIA` | 2026-05-06 | 1:50,000 | Survey of India |
| Village boundary | `SOI/ABDB/VECTOR/50000/2025/VILLAGE/INDIA` | 2026-05-08 | 1:50,000 | Survey of India |

Metadata states that the district/state/subdistrict/village datasets were harmonized with ORGI in 2024 for Lakshadweep, Chandigarh, Sikkim, and Delhi, and in 2025 for several states including Karnataka, Maharashtra, Uttar Pradesh, Punjab, and West Bengal.

Metadata also states a plotting accuracy of approximately 12.5 m at 1:50,000.

## Latest local validation result

Summary:

- metadata present: yes;
- state/district/subdistrict shapefiles present: yes;
- district layer present: yes;
- district layer has LGD fields: yes;
- acceptable as official geometry source for review: yes;
- safe for automatic DB import: no.

District layer:

| Item | Value |
| --- | --- |
| Record count | 808 |
| Shape type | `POLYGONZ` |
| Projection | Lambert Conformal Conic, WGS84, metres |
| LGD fields | `STATE_LGD`, `DIST_LGD` |
| Invalid/blank/not-available `DIST_LGD` rows | 31 |
| Invalid/blank/not-available `STATE_LGD` rows | 28 |

Subdistrict layer:

| Item | Value |
| --- | --- |
| Record count | 6,667 |
| Shape type | `POLYGON` |
| LGD fields | `STATE_LGD`, `DIST_LGD`, `SUBDIS_LGD` |

State layer:

| Item | Value |
| --- | --- |
| Record count | 40 |
| Shape type | `POLYGON` |
| Note | includes disputed rows, so record count is greater than normal state/UT count |

## Source decision

Survey of India ABDB should become the preferred official geometry source for review.

The backend LGD master remains canonical for administrative code/name/state truth.

BharatAtlas remains useful as an operational LGD-coded geometry source and comparison layer, but it should not outrank SOI when SOI geometry is validated and usable.

## Import implication

Do not automatically import SOI rows.

A future SOI-based overlay pipeline should:

1. filter out blank, `NOT AVAILABLE`, disputed, or non-LGD rows;
2. crosswalk SOI `STATE_LGD` / `DIST_LGD` against backend LGD master;
3. compare SOI district geometry against BharatAtlas candidate geometry;
4. regenerate CoRE/LGD overlay candidates using SOI geometry if validation passes;
5. write only inactive `MANUAL_REVIEW` candidate mappings;
6. preserve existing fallback mappings until reviewed polygon-derived mappings are promoted.

## Android / web impact

No Android Maestro flow is required for this source validation.

Android and web behavior changes only after reviewed polygon-derived mappings are imported and promoted into effective `land-intelligence-context` output.
