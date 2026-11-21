#!/usr/bin/env python3
"""Current read-contract assertions for committed direct crop activities.

This module does not configure or open a database and is not executable on its
own.  The destructive focused regression supplies its already-admitted client,
identity, cycle, and independently expected totals.
"""

from __future__ import annotations

from decimal import Decimal


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"DIRECT_ACTIVITY_READ_CONTRACT_FAILED:{label}")
    print(f"PASS {label}")


def assert_current_read_contracts(
    *,
    client,
    headers: dict[str, str],
    cycle_id: str,
    activity_ids: set[str],
    expected_total: Decimal,
) -> None:
    listed = client.get(f"/api/v1/crop-cycles/{cycle_id}/activities", headers=headers)
    _require(listed.status_code == 200, "activity list remains available")
    rows = listed.json()
    _require(len(rows) == len(activity_ids), "activity list length is exact")
    _require(
        {row.get("id") for row in rows} == activity_ids,
        "activity list contains exactly the committed activities",
    )

    stage = client.get(
        f"/api/v1/crop-cycles/{cycle_id}/stage-cost-summary",
        headers=headers,
    )
    _require(stage.status_code == 200, "stage cost summary remains available")
    _require(
        Decimal(stage.json()["totals"]["actual_expense"]) == expected_total,
        "stage cost summary retains direct costs",
    )

    pnl = client.get(
        f"/api/v1/crop-cycles/{cycle_id}/profit-loss-summary",
        headers=headers,
    )
    _require(pnl.status_code == 200, "profit and loss summary remains available")
    _require(
        Decimal(pnl.json()["totals"]["total_expenses"]) == expected_total,
        "profit and loss includes direct costs",
    )
