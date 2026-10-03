#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE = (ROOT / "web/smoke/project_village_resolution_review_smoke.mjs").read_text()
API = (ROOT / "backend/app/modules/master_data/api/project_village_resolutions.py").read_text()
UI = (ROOT / "web/src/components/admin/ProjectVillageResolutionReviewQueue.tsx").read_text()
CONFIG = (ROOT / "backend/app/core/config.py").read_text()
DOC = (ROOT / "docs/project-scoped-village-resolution-worklist-2026-10-02.md").read_text()

checks = [
    (SMOKE, "project_village_resolution_two_session_web_smoke.v1", "Smoke schema is pinned"),
    (SMOKE, "create_test_admin(db,role='ENTERPRISE_ADMIN'", "Two enterprise admins are created"),
    (SMOKE, "proposerContext", "Proposer browser context exists"),
    (SMOKE, "approverContext", "Approver browser context exists"),
    (SMOKE, "Approver authentication preflight failed", "Approver token is preflighted"),
    (SMOKE, "Approver panel did not render after retry", "Approver UI has bounded retry diagnostics"),
    (SMOKE, "Create review proposal", "Proposal is created through the UI"),
    (SMOKE, "SECOND_ADMIN_MUST_DIFFER_FROM_PROPOSER", "Self-approval rejection is required"),
    (SMOKE, "Approve proposal", "Approval is performed through the UI"),
    (SMOKE, '"PROPOSED,APPROVED"', "Exact audit sequence is required"),
    (SMOKE, "Activate approved resolution", "Hidden activation control is checked"),
    (SMOKE, "activation_enabled !== false", "Server activation gate is checked"),
    (SMOKE, "protectedSnapshotCode", "Protected geography is compared"),
    (SMOKE, "delete from geography_project_village_resolution_events", "Events are cleaned"),
    (SMOKE, "delete from geography_project_village_resolutions", "Proposal is cleaned"),
    (SMOKE, "delete_test_admin", "Temporary admins are cleaned"),
    (SMOKE, "android_visible: false", "Android remains hidden"),
    (API, "SECOND_ADMIN_MUST_DIFFER_FROM_PROPOSER", "Backend rejects self-approval"),
    (UI, "different enterprise-admin session", "UI explains independent authentication"),
    (UI, "queue.activation_enabled", "UI follows the server activation gate"),
    (CONFIG, "PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED: bool = False", "Activation defaults off"),
    (DOC, "## Two-session browser smoke gate — 2026-10-03", "Browser gate is documented"),
    (DOC, "The expected event sequence is exactly PROPOSED then APPROVED", "Audit sequence is documented"),
]

for source, needle, label in checks:
    if needle not in source:
        raise AssertionError(f"{label}: missing {needle!r}")
    print(f"PASS {label}")

if not (
    SMOKE.index("proposer_id=str(proposer.id)")
    < SMOKE.index('  "db.close()",')
):
    raise AssertionError("Temporary admin IDs must be captured before session close")
print("PASS Temporary admin IDs are captured before session close")

for forbidden, label in [
    ("PROJECT_LOCAL_ADDITION", "Smoke does not exercise project-local addition"),
    ("geography_villages set", "Smoke does not update canonical villages"),
    ("geography_village_pin_links set", "Smoke does not update global PIN links"),
]:
    if forbidden in SMOKE:
        raise AssertionError(label)
    print(f"PASS {label}")

print("PROJECT VILLAGE RESOLUTION TWO-SESSION WEB SMOKE STATIC CONTRACT PASSED")
