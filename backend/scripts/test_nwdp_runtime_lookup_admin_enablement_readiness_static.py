#!/usr/bin/env python3
"""Static contract for admin-only lookup enablement readiness."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    ROOT / "backend" / "scripts"
    / "audit_nwdp_runtime_lookup_admin_enablement_readiness.py"
)


def main() -> int:
    source = AUDIT.read_text(encoding="utf-8")

    contracts = [
        (
            "nwdp_runtime_lookup_admin_enablement_readiness.v1",
            "Audit schema is versioned",
        ),
        (
            "EXPECTED_ACTIVE_TOTAL = 467_397",
            "Active runtime total is pinned",
        ),
        (
            "EXPECTED_VILLAGES = 600_647",
            "Canonical village baseline is pinned",
        ),
        (
            "database_snapshot",
            "Database before and after are measured",
        ),
        (
            "database_counts_unchanged",
            "Database immutability is required",
        ),
        (
            "AdminPermission.VIEW",
            "Admin-only permission is inspected",
        ),
        (
            "runtime_set_id: UUID = Query(...)",
            "Runtime-set scope is inspected",
        ),
        (
            "feature_flag_before_limiter",
            "Feature flag ordering is checked",
        ),
        (
            "limiter_before_spatial_query",
            "Limiter ordering is checked",
        ),
        (
            "statement_timeout_present",
            "Statement timeout is checked",
        ),
        (
            "bounded_ambiguity_probe",
            "Ambiguity bound is checked",
        ),
        (
            "gist_index_present",
            "Spatial index is checked",
        ),
        (
            "observability_present",
            "Observability is checked",
        ),
        (
            "tenant_tier_supported",
            "Persisted tenant tier is checked",
        ),
        (
            "READY_FOR_SEPARATE_ADMIN_ONLY_AUTHORIZATION",
            "Readiness is separate from authorization",
        ),
        (
            '"authorized": False',
            "Audit is not authorization",
        ),
        (
            "LOCAL_ADMIN_ONLY_RUNTIME_LOOKUP_PILOT",
            "Proposed scope is admin-only and local",
        ),
        (
            "set only the lookup feature flag true",
            "Proposed change is narrowly scoped",
        ),
        (
            "immediate rollback command",
            "Rollback preparation is required",
        ),
        (
            "NWDP_RUNTIME_LOOKUP_DISABLED",
            "Rollback outcome is stable",
        ),
        (
            "customer self-service access",
            "Customer access remains unauthorized",
        ),
        (
            "tenant tier mutation",
            "Tenant tier changes remain unauthorized",
        ),
        (
            '"lookup_enablement_authorized": False',
            "Lookup remains unauthorized",
        ),
        (
            '"database_writes_attempted": False',
            "Audit is read-only",
        ),
        (
            '"sample_coordinates_recorded": False',
            "Sample coordinates are not emitted",
        ),
    ]

    for needle, label in contracts:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    forbidden = [
        "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED=true",
        "NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED = True",
        "update tenants ",
        "insert into ",
        "delete from ",
        "alter table ",
        "drop table ",
        "redis-cli FLUSH",
        "systemctl stop redis",
        "systemctl restart redis",
    ]
    lowered = source.lower()
    for token in forbidden:
        if token.lower() in lowered:
            raise AssertionError(
                f"Forbidden mutation or enablement token: {token}"
            )

    print("PASS Audit contains no enablement")
    print("PASS Audit contains no database mutations")
    print("PASS Audit contains no Redis service mutation")
    print(
        "NWDP ADMIN-ONLY LOOKUP ENABLEMENT READINESS "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
