#!/usr/bin/env python3
"""CI gate requiring a stable, zero-finding tenant/actor boundary audit."""

from __future__ import annotations

from collections import Counter
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "backend/scripts/audit_tenant_actor_trust_boundary.py"
EXPECTED_ROUTE_COUNT = 361


def main() -> int:
    spec = importlib.util.spec_from_file_location(
        "tenant_actor_trust_boundary_audit",
        AUDIT_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load trust-boundary auditor")

    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    rows = []
    for source in sorted(audit.APP.rglob("*.py")):
        if not source.name.startswith("__"):
            rows.extend(audit.scan(source))

    flagged = [row for row in rows if row["flags"]]
    findings_by_flag = Counter(
        flag
        for row in flagged
        for flag in row["flags"]
    )

    summary = {
        "audit_schema": "tenant_actor_trust_boundary_audit.v1",
        "route_count": len(rows),
        "expected_route_count": EXPECTED_ROUTE_COUNT,
        "finding_count": len(flagged),
        "findings_by_flag": dict(sorted(findings_by_flag.items())),
    }
    print(summary)

    if len(rows) != EXPECTED_ROUTE_COUNT:
        raise AssertionError(
            "Audited route count changed. Review every added or removed route "
            "and update EXPECTED_ROUTE_COUNT in this gate intentionally: "
            f"{summary}"
        )

    if flagged:
        for row in flagged:
            print({
                "file": row["file"],
                "line": row["line"],
                "method": row["method"],
                "path": row["path"],
                "function": row["function"],
                "flags": row["flags"],
            })
        raise AssertionError(
            f"Trust-boundary audit produced findings: {summary}"
        )

    print("TENANT ACTOR TRUST BOUNDARY ZERO-FINDING GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
