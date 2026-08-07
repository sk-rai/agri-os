# Survey of India District Name/Code Alignment Review

Status date: 2026-08-07

This review checks whether Survey of India ABDB district shapefile attributes can be used directly as LGD district keys.

## Command

Run:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/audit_soi_district_name_code_alignment.py

The script is read-only. It does not write database rows and does not make external calls.

## Latest result

Summary:

| Category | Count |
| --- | ---: |
| SOI records | 808 |
| SOI invalid/disputed | 31 |
| Name and code match backend LGD | 2 |
| SOI code points to different backend district | 565 |
| Code match, name not matched | 101 |
| Name match but code differs/not in backend | 82 |
| No backend match by name or code | 26 |
| State-code diff despite name match | 1 |

## Key finding

The SOI ABDB source is official and useful as a geometry reference, but the current extracted district shapefile's `DIST_LGD` attribute is not safe to use directly as the backend district key.

Examples from local audit:

- SOI row `DADRA AND NAGAR HAVELI` has `DIST_LGD=496`, but backend LGD `496` is `Solapur`.
- SOI row `DAMAN` has `DIST_LGD=495`, but backend LGD `495` is `Sindhudurg`.
- SOI row `DIU` has `DIST_LGD=494`, but backend LGD `494` is `Satara`.
- Several West Bengal district names appear with encoding artifacts such as `PASCHIM MEDIN|PUR`, `B>NKURA`, and `K>LIMPONG`.

This suggests either source-version/attribute mismatch, shapefile encoding issues, or a source-specific code field that cannot be treated as current LGD without additional crosswalk review.

## Source policy

For now:

1. Backend LGD master remains canonical for district/state identity.
2. BharatAtlas remains the preferred operational LGD-keyed geometry source for the current CoRE overlay pipeline.
3. Survey of India ABDB remains the preferred official geometry reference source, but not direct LGD-keyed import source yet.
4. SOI can be used for comparison/manual review after a reliable name/code crosswalk is built.
5. No automatic DB import should use SOI `DIST_LGD` directly.

## Impact

No Android Maestro flow is required for this review.

Web and Android behavior remain unchanged because no land-intelligence API output changes yet.

The current manual-review import plan remains intentionally inactive and non-effective.
