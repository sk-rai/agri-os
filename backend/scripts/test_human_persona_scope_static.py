#!/usr/bin/env python3
"""Static contract for strict authenticated-human persona scope."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "backend/app/core/human_persona_scope.py").read_text(
    encoding="utf-8"
)


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def main() -> int:
    require("class HumanPersonaScope:" in SOURCE, "Persona scope exists")
    require("own_farmer_ids" in SOURCE, "Personal farmer identity is explicit")
    require("assigned_farmer_ids" in SOURCE, "Assigned farmer identity is explicit")
    require("active_agent_profile_id" in SOURCE, "Agent persona is explicit")
    require("is_dual_persona" in SOURCE, "Dual persona is explicit")
    require("can_operate_farmer" in SOURCE, "Farmer operation capability exists")
    require("Farmer.user_id == principal.user_id" in SOURCE, "Personal farm uses authenticated user")
    require("AgentProfile.user_id == principal.user_id" in SOURCE, "Agent profile uses authenticated user")
    require('AgentProfile.status == "ACTIVE"' in SOURCE, "Inactive agent profiles are excluded")
    require('FarmerProjectEnrollment.status == "ACTIVE"' in SOURCE, "Inactive enrollments are excluded")
    require("enrollment.assigned_user_ids" in SOURCE, "Explicit farmer assignment is required")
    require("ProjectRole.user_id == principal.user_id" in SOURCE, "Project roles use authenticated user")
    require("Project.tenant_id == principal.tenant_id" in SOURCE, "Project access is tenant bounded")
    require("Farmer.tenant_id == principal.tenant_id" in SOURCE, "Farmer access is tenant bounded")
    require("_actor_can_manage_farmer" not in SOURCE, "Compatibility-permissive helper is not reused")
    require("mobile_number" not in SOURCE, "Authorization does not rely on mobile-number matching")
    require("X-Actor-ID" not in SOURCE, "Authorization does not trust actor headers")
    print("HUMAN PERSONA SCOPE STATIC CONTRACT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
