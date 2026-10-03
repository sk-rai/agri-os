#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "backend/alembic/versions/064_add_project_village_resolution_review_workflow.py").read_text()
API = (ROOT / "backend/app/modules/master_data/api/project_village_resolutions.py").read_text()
PANEL = (ROOT / "web/src/components/admin/ProjectVillageResolutionPanel.tsx").read_text()
QUEUE = (ROOT / "web/src/components/admin/ProjectVillageResolutionReviewQueue.tsx").read_text()
DOC = (ROOT / "docs/project-scoped-village-resolution-worklist-2026-10-02.md").read_text()

checks = [
    (MIGRATION, 'revision = "064"', "Migration revision is pinned"),
    (MIGRATION, 'down_revision = "063"', "Migration follows audit-event foundation"),
    (MIGRATION, "'PROPOSED','APPROVED','APPLIED','ROLLED_BACK'", "Review actions are bounded"),
    (MIGRATION, "uq_project_village_resolution_open_canonical", "Concurrent open proposals are blocked"),
    (API, "@router.post('/projects/{project_id}/proposals')", "Proposal endpoint exists"),
    (API, "'PROJECT_LOCAL_ADDITION_PROPOSAL_DISABLED'", "Project-local additions remain disabled"),
    (API, "'PROPOSED'", "Proposal event is appended"),
    (API, "@router.post('/projects/{project_id}/resolutions/{resolution_id}/approve')", "Approval endpoint exists"),
    (API, "SECOND_ADMIN_MUST_DIFFER_FROM_PROPOSER", "Self-approval is rejected"),
    (API, "ENTERPRISE_ADMIN_APPROVAL_REQUIRED", "Approval requires enterprise admin"),
    (API, "APPROVE PROJECT CANONICAL ENRICHMENT", "Approval phrase is exact"),
    (API, "@router.get('/projects/{project_id}/resolutions')", "Read-only review queue exists"),
    (API, "project_village_resolution_review_queue.v1", "Review queue schema is pinned"),
    (API, "@router.post('/projects/{project_id}/resolutions/{resolution_id}/activate')", "Activation endpoint exists"),
    (API, "PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED", "Activation remains flag gated"),
    (API, "ACTIVATE APPROVED PROJECT CANONICAL ENRICHMENT", "Activation phrase is exact"),
    (PANEL, "Create review proposal", "Admin can create a proposal"),
    (QUEUE, "Load review queue", "Admin can load audit history"),
    (QUEUE, "Approve proposal", "Independent approval control exists"),
    (QUEUE, "queue.activation_enabled", "Activation control follows server gate"),
    (QUEUE, "Activate approved resolution", "Activation control is explicit"),
    (QUEUE, "different enterprise-admin session", "Two-session boundary is visible"),
    (DOC, "## Two-session proposal and approval workflow — 2026-10-03", "Workflow is documented"),
    (DOC, "PROJECT_LOCAL_ADDITION remains disabled", "Documentation preserves local-addition boundary"),
]

for source, needle, label in checks:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")

for forbidden, label in [
    ("android_visible':True", "API never enables Android"),
    ('"android_visible": true', "UI never claims Android visibility"),
]:
    if forbidden in API + PANEL + QUEUE:
        raise AssertionError(label)
    print(f"PASS {label}")

print("PROJECT VILLAGE RESOLUTION REVIEW WORKFLOW STATIC CONTRACT PASSED")
