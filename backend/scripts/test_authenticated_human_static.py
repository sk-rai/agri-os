#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app/core/human_auth.py").read_text(encoding="utf-8")


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main() -> int:
    require(
        "class AuthenticatedPrincipal:" in SOURCE,
        "Role-neutral principal exists",
    )
    require(
        "def require_authenticated_human():" in SOURCE,
        "Human authentication dependency exists",
    )
    require("jwt.decode(" in SOURCE, "Bearer JWT is verified")
    require("User.is_active == True" in SOURCE, "Inactive users are rejected")
    require("ACTOR_ID_MISMATCH" in SOURCE, "Actor mismatch is explicit")
    require("TENANT_ID_MISMATCH" in SOURCE, "Tenant mismatch is explicit")
    require(
        "x_actor_id != str(user.id)" in SOURCE,
        "Actor is bound to token subject",
    )
    require(
        "token_tenant != tenant_id" in SOURCE,
        "Header tenant is bound to token tenant",
    )
    require(
        "user.tenant_id != tenant_id" in SOURCE,
        "Tenant is bound to persisted user",
    )
    require(
        "AdminPermission" not in SOURCE,
        "Human authentication is not admin authorization",
    )
    require(
        "ROLE_PERMISSIONS" not in SOURCE,
        "Farmer and field-agent roles are not excluded",
    )
    print("AUTHENTICATED HUMAN STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
