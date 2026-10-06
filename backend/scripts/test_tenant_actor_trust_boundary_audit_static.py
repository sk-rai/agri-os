#!/usr/bin/env python3
"""Static contract for tenant/actor trust-boundary audit."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
AUDIT=(ROOT/"backend/scripts/audit_tenant_actor_trust_boundary.py").read_text()
DOC=(ROOT/"docs/tenant-actor-trust-boundary-audit-2026-10-05.md").read_text()
CHECKS=[
 (AUDIT,"tenant_actor_trust_boundary_audit.v1","Schema is pinned"),
 (AUDIT,"MUTATION_WITHOUT_AUTH_MARKER","Unauthenticated mutations are classified"),
 (AUDIT,"MUTATION_WITHOUT_TENANT_MARKER","Tenant gaps are classified"),
 (AUDIT,"MUTATION_WITHOUT_ACTOR_MARKER","Actor gaps are classified"),
 (AUDIT,"NON_REFERENCE_READ_WITHOUT_AUTH_MARKER","Read gaps are classified"),
 (AUDIT,"headers_are_not_authorization","Header boundary is explicit"),
 (AUDIT,"AuthenticatedPrincipal","Shared human principal is recognized"),
 (AUDIT,"require_authenticated_human","Shared human dependency is recognized"),
 (AUDIT,'automatic_enforcement_authorized":False',"Automatic enforcement is prohibited"),
 (DOC,"Compatibility-first remediation","Compatibility boundary is documented"),
 (DOC,"Mutation routes first","Mutation priority is documented"),
 (DOC,"Android and admin clients","Client impact is documented"),
]
def main():
    for source,needle,label in CHECKS:
        if needle not in source:raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")
    for needle in ("INSERT INTO","UPDATE ","DELETE FROM"):
        if needle in AUDIT:raise AssertionError(f"Read-only audit contains {needle}")
    print("PASS Audit contains no database mutation")
    print("TENANT ACTOR TRUST BOUNDARY STATIC CONTRACT PASSED")
    return 0
if __name__=="__main__":raise SystemExit(main())
