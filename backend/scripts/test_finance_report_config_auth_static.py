#!/usr/bin/env python3
"""Static authorization contract for finance report configuration routes."""

from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "app/modules/workflow/api.py"
).read_text(encoding="utf-8-sig")


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def block(name: str, next_name: str) -> str:
    start = SOURCE.index(f"def {name}(")
    end = SOURCE.index(f"\ndef {next_name}(", start)
    return SOURCE[start:end]


def main() -> None:
    validate = block(
        "validate_finance_report_config_endpoint",
        "publish_finance_report_config",
    )
    publish = block(
        "publish_finance_report_config",
        "get_finance_analytics_summary",
    )

    check(
        "require_admin_permission(AdminPermission.EDIT)" in validate,
        "Finance config validation requires edit permission",
    )
    check(
        "principal.tenant_id" in validate,
        "Finance config validation derives tenant from verified administrator",
    )
    check(
        "_assert_finance_report_config_project_scope" in validate,
        "Finance config validation tenant-bounds optional project",
    )
    check(
        "actor_id = str(principal.user_id)" in validate,
        "Finance config validation derives actor from verified administrator",
    )
    check(
        'validation["validated_by"] = actor_id' in validate,
        "Finance config validation reports verified validator",
    )
    check(
        "X-Tenant-ID" not in validate and "X-Actor-ID" not in validate,
        "Finance config validation does not trust identity headers directly",
    )

    check(
        "require_admin_permission(AdminPermission.PUBLISH)" in publish,
        "Finance config publishing requires publish permission",
    )
    check(
        "tenant_id = principal.tenant_id" in publish,
        "Finance config publishing derives tenant from verified administrator",
    )
    check(
        "actor_id = str(principal.user_id)" in publish,
        "Finance config publishing derives actor from verified administrator",
    )
    check(
        "_assert_finance_report_config_project_scope" in publish,
        "Finance config publishing tenant-bounds optional project",
    )
    check(
        "published_by=actor_id" in publish,
        "Finance config publishing records verified administrator",
    )
    check(
        "row.archived_by = actor_id" in publish,
        "Finance config archival records verified administrator",
    )
    check(
        "X-Tenant-ID" not in publish and "X-Actor-ID" not in publish,
        "Finance config publishing does not trust identity headers directly",
    )
    check(
        'metadata_={"fixed_formula": '
        '"profit_or_loss = total_income - total_expenses"}' in publish,
        "Finance config publishing preserves fixed formula boundary",
    )

    print("FINANCE REPORT CONFIG AUTH STATIC CONTRACT PASSED")


if __name__ == "__main__":
    main()
