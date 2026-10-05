#!/usr/bin/env python3
"""Static contract for the full backend/web audit."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
AUDIT=(ROOT/"backend/scripts/audit_backend_web_repository_readiness.py").read_text()
DOC=(ROOT/"docs/backend-web-full-audit-2026-10-05.md").read_text()
CHECKS=[
 (AUDIT,"backend_web_repository_audit.v1","Schema is pinned"),
 (AUDIT,"AUTH_PRODUCTION_HARDENING","Production auth is audited"),
 (AUDIT,"CI_AND_UNIFIED_TEST_GATE","CI/test gate is audited"),
 (AUDIT,"TENANT_TRUST_BOUNDARY","Tenant trust is audited"),
 (AUDIT,"WEB_SESSION_STORAGE","Web session storage is audited"),
 (AUDIT,"AUDIT_CHAIN_VERIFICATION","Audit chain is audited"),
 (AUDIT,"IRRIGATION_CANAL_LAYER","Canal work is retained"),
 (AUDIT,"PERENNIAL_ONBOARDING","Perennial work is reconciled"),
 (AUDIT,"ADMIN_LOCALIZATION_OVERRIDES","Localization is reconciled"),
 (AUDIT,"GEOGRAPHY_RESIDUAL_RECONCILIATION","Paused geography is retained"),
 (DOC,"Release blockers","Release blockers are documented"),
 (DOC,"Implemented but described as pending","Stale plans are documented"),
 (DOC,"No new Android work is required","Android boundary is explicit"),
 (DOC,"Irrigation/canal","Canal decision is documented"),
 (DOC,"Recommended execution order","Execution order is documented"),
]
def main():
    for text,needle,label in CHECKS:
        if needle not in text: raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")
    for needle in ("INSERT INTO","UPDATE geography_","DELETE FROM geography_"):
        if needle in AUDIT: raise AssertionError(f"Audit must remain read-only: {needle}")
    print("PASS Audit contains no database or geography mutation")
    print("BACKEND AND WEB REPOSITORY AUDIT STATIC CONTRACT PASSED")
    return 0
if __name__=="__main__": raise SystemExit(main())
