#!/usr/bin/env python3
"""Build the authoritative-source worklist for open geography identities.

Filesystem behavior: read-only except for the requested JSON report.
Database behavior: none.

NWDP boundary files are corroborating evidence only. Official LGD hierarchy
exports are required before a canonical correction proposal can be built.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "geography_authoritative_identity_source_worklist.v1"
LGD_DOWNLOAD_DIRECTORY = (
    "https://lgdirectory.gov.in/demo/downloadDirectory.do"
)
LGD_OGD_CATALOG = (
    "https://www.data.gov.in/catalog/local-government-directory-lgd"
)

DEFAULT_AUDIT = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260930-canonical-identity-gap-audit-v1"
    / "geography_canonical_identity_gap_audit.json"
)
DEFAULT_MP_NWDP = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/20260824T110250Z"
    / "madhya_pradesh.geojson"
)
DEFAULT_CHANDIGARH_NWDP = (
    ROOT
    / "data/raw/nwdp_boundary_all_state/20260824T110250Z"
    / "chandigarh.geojson"
)
DEFAULT_MP_LGD = (
    ROOT
    / "data/raw/lgd_identity_review/20260930"
    / "madhya_pradesh_village_hierarchy.csv"
)
DEFAULT_CHANDIGARH_LGD = (
    ROOT
    / "data/raw/lgd_identity_review/20260930"
    / "chandigarh_complete_hierarchy.csv"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260930-authoritative-identity-source-worklist-v1"
    / "geography_authoritative_identity_source_worklist.json"
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--identity-audit", type=Path, default=DEFAULT_AUDIT
    )
    parser.add_argument("--mp-nwdp", type=Path, default=DEFAULT_MP_NWDP)
    parser.add_argument(
        "--chandigarh-nwdp",
        type=Path,
        default=DEFAULT_CHANDIGARH_NWDP,
    )
    parser.add_argument("--mp-lgd", type=Path, default=DEFAULT_MP_LGD)
    parser.add_argument(
        "--chandigarh-lgd",
        type=Path,
        default=DEFAULT_CHANDIGARH_LGD,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path):
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def evidence_file(path, role, authority):
    exists = path.is_file()
    return {
        "path": relative(path),
        "exists": exists,
        "bytes": path.stat().st_size if exists else None,
        "sha256": sha256(path) if exists else None,
        "role": role,
        "authority": authority,
    }


def require_audit(path):
    if not path.is_file():
        raise SystemExit(f"Identity audit not found: {path}")

    audit = json.loads(path.read_text(encoding="utf-8"))

    if (
        audit.get("schema_version")
        != "geography_canonical_identity_gap_audit.v1"
    ):
        raise SystemExit("Identity audit schema is not recognized")

    if (
        audit.get("status") != "AUDITED_NOT_AUTHORIZED"
        or not audit.get("healthy")
    ):
        raise SystemExit(
            "Identity audit is not a healthy unauthorized baseline"
        )

    duplicate = audit.get("duplicate_village", {})
    chandigarh = audit.get("chandigarh_gap", {})

    if (
        duplicate.get("lgd_code") != "476380"
        or duplicate.get("row_count") != 2
    ):
        raise SystemExit(
            "Pinned duplicate village evidence is not exact"
        )

    if (
        chandigarh.get("state_lgd_code") != "4"
        or chandigarh.get("review_row_count") != 12
    ):
        raise SystemExit(
            "Pinned Chandigarh gap evidence is not exact"
        )

    return audit


def main():
    args = parse_args()
    audit = require_audit(args.identity_audit)

    corroborating = [
        evidence_file(
            args.mp_nwdp,
            "CORROBORATING_BOUNDARY_GEOMETRY_ONLY",
            "NOT_CANONICAL_IDENTITY_AUTHORITY",
        ),
        evidence_file(
            args.chandigarh_nwdp,
            "CORROBORATING_BOUNDARY_GEOMETRY_ONLY",
            "NOT_CANONICAL_IDENTITY_AUTHORITY",
        ),
    ]

    required = [
        evidence_file(
            args.mp_lgd,
            "AUTHORITATIVE_CURRENT_VILLAGE_PARENT_EVIDENCE",
            "LGD_CANONICAL",
        ),
        evidence_file(
            args.chandigarh_lgd,
            "AUTHORITATIVE_COMPLETE_HIERARCHY",
            "LGD_CANONICAL",
        ),
    ]

    missing = [
        item["path"]
        for item in required
        if not item["exists"]
    ]

    duplicate_rows = audit["duplicate_village"]["rows"]

    result = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "READY_FOR_AUTHORITATIVE_SOURCE_VALIDATION"
            if not missing
            else "BLOCKED_PENDING_AUTHORITATIVE_LGD_EXPORTS"
        ),
        "healthy": True,
        "authorized": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity_audit": {
            "path": relative(args.identity_audit),
            "sha256": sha256(args.identity_audit),
            "summary_checksum": audit["summary_checksum"],
        },
        "open_identity_work": {
            "duplicate_village_476380": {
                "row_count": 2,
                "candidate_village_ids": sorted(
                    row["village_id"]
                    for row in duplicate_rows
                ),
                "candidate_parent_blocks": sorted(
                    {
                        (
                            f'{row["block_lgd_code"]}:'
                            f'{row["block_name"]}'
                        )
                        for row in duplicate_rows
                    }
                ),
                "required_determination": (
                    "Identify the current official LGD parent and "
                    "classify the other row as historical, renamed, "
                    "reparented, or erroneous."
                ),
            },
            "chandigarh_state_4": {
                "canonical_hierarchy_present": False,
                "held_boundary_row_count": 12,
                "required_determination": (
                    "Establish the official state, district, "
                    "subdistrict/block, and village hierarchy before "
                    "additive import planning."
                ),
            },
        },
        "corroborating_sources": corroborating,
        "required_authoritative_sources": required,
        "missing_authoritative_sources": missing,
        "acquisition": {
            "official_sources": [
                LGD_DOWNLOAD_DIRECTORY,
                LGD_OGD_CATALOG,
            ],
            "required_provenance_fields": [
                "source_url",
                "retrieved_at",
                "sha256",
                "report_or_export_name",
                "state_lgd_code",
                "reference_or_effective_date",
            ],
            "instructions": [
                (
                    "Download an official current LGD village hierarchy "
                    "export for Madhya Pradesh."
                ),
                (
                    "Download official LGD hierarchy exports covering "
                    "Chandigarh state, district, subdistrict/block, "
                    "and village levels."
                ),
                (
                    "Place the reviewed exports at the required paths "
                    "or pass explicit --mp-lgd and --chandigarh-lgd paths."
                ),
                (
                    "Do not treat NWDP geometry, PIN data, or name "
                    "similarity as canonical identity authority."
                ),
            ],
        },
        "next_step": (
            "Validate and checksum the official LGD exports; only then "
            "build a read-only correction proposal."
        ),
        "policy": {
            "database_writes_attempted": False,
            "downloads_attempted": False,
            "automatic_resolution_authorized": False,
            "canonical_insert_authorized": False,
            "canonical_merge_authorized": False,
            "canonical_reparent_authorized": False,
            "reference_rewrite_authorized": False,
            "boundary_candidate_changes_authorized": False,
            "runtime_activation_authorized": False,
            "android_changes_authorized": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    print(
        "GEOGRAPHY AUTHORITATIVE IDENTITY SOURCE WORKLIST BUILT"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
