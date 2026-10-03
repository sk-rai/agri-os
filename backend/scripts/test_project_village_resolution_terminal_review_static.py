#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "backend/alembic/versions/065_add_project_village_resolution_terminal_review_events.py"
).read_text()
API = (ROOT / "backend/app/modules/master_data/api/project_village_resolutions.py").read_text()
UI = (ROOT / "web/src/components/admin/ProjectVillageResolutionReviewQueue.tsx").read_text()
TEST = (
    ROOT / "backend/scripts/test_project_village_resolution_terminal_review_workflow.py"
).read_text()
DOC = (ROOT / "docs/project-scoped-village-resolution-worklist-2026-10-02.md").read_text()

checks = [
    (MIGRATION, 'revision = "065"', "Migration revision is pinned"),
    (MIGRATION, 'down_revision = "064"', "Migration follows review workflow"),
    (MIGRATION, "'REJECTED','CANCELLED'", "Terminal events are bounded"),
    (API, "@router.post('/projects/{project_id}/resolutions/{resolution_id}/reject')", "Reject endpoint exists"),
    (API, "@router.post('/projects/{project_id}/resolutions/{resolution_id}/cancel')", "Cancel endpoint exists"),
    (API, "ENTERPRISE_ADMIN_REJECTION_REQUIRED", "Rejection requires enterprise admin"),
    (API, "SECOND_ADMIN_MUST_DIFFER_FROM_PROPOSER", "Proposer cannot independently reject"),
    (API, "ONLY_PROPOSER_CAN_CANCEL_DRAFT", "Only proposer can cancel"),
    (API, "resolution_status in ('DRAFT', 'APPROVED')", "Open states can be rejected"),
    (API, "resolution_status = 'DRAFT'", "Only drafts can be cancelled"),
    (API, "REJECT PROJECT CANONICAL ENRICHMENT", "Reject phrase is exact"),
    (API, "CANCEL PROJECT CANONICAL ENRICHMENT", "Cancel phrase is exact"),
    (API, "'android_visible': False", "Android remains hidden"),
    (API, "'global_geography_changed': False", "Global geography remains unchanged"),
    (UI, "currentActorId", "UI resolves current actor"),
    (UI, "Cancel draft", "Proposer cancellation control exists"),
    (UI, "Reject proposal", "Independent rejection control exists"),
    (UI, 'event.action === "PROPOSED"', "UI identifies proposer from immutable history"),
    (TEST, '["PROPOSED", "CANCELLED"]', "Cancellation history is exact"),
    (TEST, '["PROPOSED", "REJECTED"]', "Draft rejection history is exact"),
    (TEST, '"APPROVED",\n            "REJECTED"', "Approved rejection history is exact"),
    (DOC, "## Proposal rejection and cancellation — 2026-10-03", "Terminal workflow is documented"),
]

for source, needle, label in checks:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")

for forbidden, label in [
    ("PROJECT_LOCAL_ADDITION", "Terminal behavior test excludes project-local addition"),
    ("update geography_villages", "API does not update canonical villages"),
    ("update geography_village_pin_links", "API does not update global PIN links"),
]:
    source = TEST if forbidden == "PROJECT_LOCAL_ADDITION" else API
    if forbidden in source:
        raise AssertionError(label)
    print(f"PASS {label}")

print("PROJECT VILLAGE RESOLUTION TERMINAL REVIEW STATIC CONTRACT PASSED")
