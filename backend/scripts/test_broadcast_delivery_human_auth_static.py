#!/usr/bin/env python3
"""Static contract for authenticated broadcast delivery consumption."""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SOURCE = (BACKEND / "app/modules/media/broadcast_api.py").read_text(
    encoding="utf-8"
)
SAMPLE = (BACKEND / "scripts/capture_android_sample_payloads.py").read_text(
    encoding="utf-8"
)
LIFECYCLE = (
    BACKEND / "scripts/verify_android_broadcast_read_ack_lifecycle.py"
).read_text(encoding="utf-8")
TERMINAL = (
    BACKEND / "scripts/prepare_android_broadcast_terminal_visibility.py"
).read_text(encoding="utf-8")


def require(condition: bool, label: str) -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}")
    if not condition:
        raise AssertionError(label)


def main() -> int:
    require(
        SOURCE.count("Depends(require_authenticated_human())") >= 2,
        "Read and acknowledge require authenticated humans",
    )
    require(
        "BROADCAST_DELIVERY_ACCESS_DENIED" in SOURCE,
        "Unrelated delivery access is rejected",
    )
    require(
        "delivery.user_id == principal.user_id" in SOURCE,
        "Explicit delivery user is accepted",
    )
    require(
        "farmer.user_id == principal.user_id" in SOURCE,
        "Linked farmer user is accepted",
    )
    require(
        'FarmerProjectEnrollment.status == "ACTIVE"' in SOURCE,
        "Only active project assignments are considered",
    )
    require(
        "BroadcastDelivery.tenant_id == principal.tenant_id" in SOURCE,
        "Delivery lookup uses verified tenant",
    )
    require(
        SOURCE.count("actor_id=principal.user_id") == 2,
        "Both audit events use authenticated actor",
    )
    require(
        SOURCE.count("actor_type=principal.role") == 2,
        "Both audit events use authenticated role",
    )
    require(
        '"/deliveries/{delivery_id}/read"' in SOURCE,
        "Read endpoint path remains stable",
    )
    require(
        '"/deliveries/{delivery_id}/acknowledge"' in SOURCE,
        "Acknowledge endpoint path remains stable",
    )
    require(
        "delivery.farmer_id" not in "\n".join(
            line
            for line in SOURCE.splitlines()
            if "_record_broadcast_audit" in line
            and (
                "MARK_DELIVERY_READ" in line
                or "ACKNOWLEDGE_DELIVERY" in line
            )
        ),
        "Farmer record is no longer used as audit actor",
    )
    require(
        "headers=farmer_headers" in SAMPLE,
        "Android sample read and acknowledge use farmer bearer",
    )
    require(
        "authenticated_farmer_headers()" in LIFECYCLE,
        "Read-ack lifecycle uses linked farmer identity",
    )
    require(
        "create_jwt(user" in LIFECYCLE,
        "Read-ack lifecycle creates a verified bearer",
    )
    require(
        "create_test_admin(" in TERMINAL
        and "delete_test_admin(" in TERMINAL,
        "Terminal fixture bounds its temporary admin",
    )
    require(
        "headers=admin_headers" in TERMINAL,
        "Terminal campaign mutations use admin bearer",
    )
    require(
        "headers=farmer_headers" in TERMINAL,
        "Terminal read and acknowledge use farmer bearer",
    )
    print("BROADCAST DELIVERY HUMAN AUTH STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
