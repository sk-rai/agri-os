#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN = (ROOT / "app/core/admin_auth.py").read_text(encoding="utf-8")
HUMAN = (ROOT / "app/core/human_auth.py").read_text(encoding="utf-8")


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main() -> int:
    require(
        "def resolve_authenticated_identity(" in HUMAN,
        "Shared identity resolver exists",
    )
    require(
        "resolve_authenticated_identity" in ADMIN,
        "Admin authentication reuses shared resolver",
    )
    require(
        "jwt.decode(" not in ADMIN,
        "Admin authentication no longer decodes JWT independently",
    )
    require(
        "User.is_active == True" not in ADMIN,
        "Admin authentication no longer queries active users independently",
    )
    require(
        "ROLE_PERMISSIONS" in ADMIN,
        "Admin role permissions remain",
    )
    require(
        "project_scoped" in ADMIN,
        "Project-scoped authorization remains",
    )
    require(
        "ADMIN_AUTHENTICATION_REQUIRED" in ADMIN,
        "Admin authentication error remains stable",
    )
    require(
        "ADMIN_PERMISSION_DENIED" in ADMIN,
        "Admin permission error remains stable",
    )
    require(
        "Bearer token is required for admin mutations." in ADMIN,
        "Admin missing-bearer message remains stable",
    )
    print("ADMIN AUTH SHARED IDENTITY STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
