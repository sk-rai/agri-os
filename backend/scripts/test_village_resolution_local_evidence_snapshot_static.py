#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "backend/alembic/versions/066_add_village_resolution_evidence_snapshots.py").read_text()
LOADER = (ROOT / "backend/scripts/load_canonical_village_resolution_evidence_snapshot.py").read_text()
API = (ROOT / "backend/app/modules/master_data/api/geography.py").read_text()
DOC = (ROOT / "docs/village-resolution-local-evidence-api-2026-10-04.md").read_text()


def main() -> int:
    checks = (
        ("Migration revision is pinned", 'revision = "066"', MIGRATION),
        ("Migration follows current head", 'down_revision = "065"', MIGRATION),
        ("Snapshot table exists", "geography_village_resolution_evidence_snapshots", MIGRATION),
        ("Item table exists", "geography_village_resolution_evidence_items", MIGRATION),
        ("Only one active snapshot is allowed", "uq_village_resolution_evidence_snapshot_active", MIGRATION),
        ("Automatic resolution is constrained off", "ck_village_resolution_evidence_no_automatic_resolution", MIGRATION),
        ("Loader schema is pinned", 'SCHEMA_VERSION = "canonical_village_resolution_evidence_snapshot_load.v1"', LOADER),
        ("Loader apply is explicit", 'parser.add_argument("--apply", action="store_true")', LOADER),
        ("Loader confirmation is exact", 'CONFIRMATION = "LOAD CANONICAL LOCAL EVIDENCE SNAPSHOT"', LOADER),
        ("Loader pins all unresolved villages", '"items": 7493', LOADER),
        ("Existing endpoint is reused", '@router.get("/village-resolution")', API),
        ("Evidence status filter exists", "local_evidence_status: Optional[str]", API),
        ("Eligibility filter exists", "review_eligibility: Optional[str]", API),
        ("Collision filter exists", "source_collision: Optional[bool]", API),
        ("Active snapshot is joined", "active_local_evidence as", API),
        ("Existing schema remains stable", '"schema_version": "lgd_pin_nwdp_village_resolution.v1"', API),
        ("Reuse decision is documented", "No cohort-specific endpoint is introduced", DOC),
        ("Default compatibility is documented", "backward-compatible", DOC),
        ("Snapshot refresh is controlled", "explicit confirmation phrase", DOC),
        ("Android remains unchanged", "Android behavior remains unchanged", DOC),
    )
    for label, needle, haystack in checks:
        if needle not in haystack:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")
    for needle in ('@router.get("/canonical-unresolved', '@router.get("/single-candidate'):
        if needle in API:
            raise AssertionError(f"Cohort-specific endpoint found: {needle}")
    print("PASS No cohort-specific endpoint exists")
    print("VILLAGE RESOLUTION LOCAL EVIDENCE SNAPSHOT STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
