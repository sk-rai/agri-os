#!/usr/bin/env python3
"""Static contract for the authoritative identity source worklist."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "backend/scripts/"
    "build_geography_authoritative_identity_source_worklist.py"
)


def main():
    source = SCRIPT.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    checks = [
        (
            "geography_canonical_identity_gap_audit.v1",
            "Existing identity audit is pinned",
        ),
        (
            'duplicate.get("lgd_code") != "476380"',
            "Duplicate LGD identity is exact",
        ),
        (
            'chandigarh.get("state_lgd_code") != "4"',
            "Chandigarh LGD identity is exact",
        ),
        (
            'chandigarh.get("review_row_count") != 12',
            "Twelve Chandigarh rows are exact",
        ),
        (
            "madhya_pradesh.geojson",
            "Madhya Pradesh NWDP evidence is inventoried",
        ),
        (
            "chandigarh.geojson",
            "Chandigarh NWDP evidence is inventoried",
        ),
        (
            "CORROBORATING_BOUNDARY_GEOMETRY_ONLY",
            "Boundary geometry is corroborating only",
        ),
        (
            "NOT_CANONICAL_IDENTITY_AUTHORITY",
            "NWDP is denied canonical authority",
        ),
        (
            "madhya_pradesh_village_hierarchy.csv",
            "Madhya Pradesh LGD export is required",
        ),
        (
            "chandigarh_complete_hierarchy.csv",
            "Complete Chandigarh hierarchy is required",
        ),
        (
            "LGD_CANONICAL",
            "LGD authority is explicit",
        ),
        (
            "BLOCKED_PENDING_AUTHORITATIVE_LGD_EXPORTS",
            "Missing sources block correction planning",
        ),
        (
            "required_provenance_fields",
            "Source provenance is required",
        ),
        (
            "reference_or_effective_date",
            "Source effective date is required",
        ),
        (
            '"downloads_attempted": False',
            "Automatic downloads are forbidden",
        ),
        (
            '"database_writes_attempted": False',
            "Database writes are forbidden",
        ),
        (
            '"canonical_merge_authorized": False',
            "Canonical merge remains unauthorized",
        ),
        (
            '"canonical_reparent_authorized": False',
            "Canonical reparent remains unauthorized",
        ),
        (
            '"runtime_activation_authorized": False',
            "Runtime activation remains unauthorized",
        ),
        (
            '"android_changes_authorized": False',
            "Android changes remain unauthorized",
        ),
    ]

    for needle, label in checks:
        if needle not in normalized:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    prohibited = [
        "sqlalchemy",
        "insert into",
        "update geography_",
        "delete from",
        "requests.get",
        "urllib.request",
        "subprocess",
    ]
    present = [
        item
        for item in prohibited
        if item in normalized.lower()
    ]
    if present:
        raise AssertionError(
            f"Worklist contains forbidden operations: {present}"
        )

    print(
        "PASS Worklist contains no database access "
        "or network acquisition"
    )
    print(
        "GEOGRAPHY AUTHORITATIVE IDENTITY SOURCE "
        "WORKLIST STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
