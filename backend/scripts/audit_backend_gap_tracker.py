#!/usr/bin/env python3
"""Audit docs/backend-gap-closure-tracker.md for stale or malformed rows."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACKER = ROOT / "docs/backend-gap-closure-tracker.md"

VALID_STATUSES = {
    "Closed",
    "Active next",
    "Deferred",
    "Needs research",
    "Watch during Android",
}


def parse_rows(text: str) -> list[dict]:
    rows = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.startswith("| "):
            continue
        if line.startswith("| Item ") or line.startswith("| ---"):
            continue

        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) != 4:
            rows.append(
                {
                    "line": line_no,
                    "raw": line,
                    "parse_error": f"expected 4 columns, got {len(parts)}",
                }
            )
            continue

        rows.append(
            {
                "line": line_no,
                "item": parts[0],
                "status": parts[1],
                "notes": parts[2],
                "evidence": parts[3],
                "parse_error": None,
            }
        )
    return rows


def main() -> int:
    text = TRACKER.read_text()
    rows = parse_rows(text)

    parse_errors = [row for row in rows if row.get("parse_error")]
    invalid_status = [
        row for row in rows
        if not row.get("parse_error") and row["status"] not in VALID_STATUSES
    ]
    missing_evidence = [
        row for row in rows
        if not row.get("parse_error") and not row["evidence"]
    ]

    status_counts = {}
    for row in rows:
        if row.get("parse_error"):
            continue
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    active_next = [
        {
            "line": row["line"],
            "item": row["item"],
            "notes": row["notes"],
            "evidence": row["evidence"],
        }
        for row in rows
        if not row.get("parse_error") and row["status"] == "Active next"
    ]

    potentially_stale = []
    stale_patterns = [
        r"\bActive next\b.*\bClosed\b",
        r"\bready.*no\b.*\bClosed\b",
        r"\bTODO\b",
        r"\bTBD\b",
    ]

    for row in rows:
        if row.get("parse_error"):
            continue
        combined = f"{row['item']} {row['status']} {row['notes']} {row['evidence']}"
        if any(re.search(pattern, combined, flags=re.I) for pattern in stale_patterns):
            potentially_stale.append(row)

    result = {
        "schema_version": "backend_gap_tracker_audit.v1",
        "tracker_path": str(TRACKER),
        "row_count": len([row for row in rows if not row.get("parse_error")]),
        "status_counts": status_counts,
        "active_next": active_next,
        "parse_errors": parse_errors,
        "invalid_status": invalid_status,
        "missing_evidence": missing_evidence,
        "potentially_stale": potentially_stale,
        "readiness": {
            "tracker_parseable": not parse_errors,
            "statuses_valid": not invalid_status,
            "evidence_present": not missing_evidence,
            "has_active_next": bool(active_next),
            "single_active_next": len(active_next) == 1,
        },
        "next_actions": [
            "Keep exactly one Active next row unless deliberately running parallel backend tracks.",
            "Move audited-but-not-implementing items to Deferred or Needs research.",
            "Update this tracker after each backend gap closure commit.",
        ],
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    ok = (
        result["readiness"]["tracker_parseable"]
        and result["readiness"]["statuses_valid"]
        and result["readiness"]["evidence_present"]
        and result["readiness"]["has_active_next"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
