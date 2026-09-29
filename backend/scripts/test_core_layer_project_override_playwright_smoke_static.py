#!/usr/bin/env python3
"""Static contract for Core-layer project Playwright smoke."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SMOKE = (
    ROOT
    / "web/smoke/core_layer_project_override_smoke.mjs"
)
RUNNER = (
    ROOT
    / "web/scripts/run_core_layer_project_override_smoke.mjs"
)


def main() -> int:
    smoke = SMOKE.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    normalized = " ".join(smoke.split())

    checks = [
        (
            'from "playwright"',
            smoke,
            "Existing Playwright package is reused",
        ),
        (
            "WEB_SWEEP_TOKEN",
            smoke,
            "Existing smoke token variable is reused",
        ),
        (
            "WEB_SWEEP_TENANT_ID",
            smoke,
            "Existing tenant variable is reused",
        ),
        (
            "WEB_SWEEP_ACTOR_ID",
            smoke,
            "Existing actor variable is reused",
        ),
        (
            "create_web_ui_smoke_session.py",
            runner,
            "Existing authenticated session creator is reused",
        ),
        (
            '"ENTERPRISE_ADMIN"',
            runner,
            "Write-capable admin role is explicit",
        ),
        (
            "token_logged: false",
            runner,
            "Credential token is not logged",
        ),
        (
            "findFixture()",
            smoke,
            "Project village fixture is discovered",
        ),
        (
            "readinessResponsePromise",
            smoke,
            "Large readiness response is awaited",
        ),
        (
            "{ timeout: 240000 }",
            smoke,
            "Readiness timeout matches long-running page behavior",
        ),
        (
            "geography_layer_readiness_matrix.v1",
            smoke,
            "Readiness payload is validated",
        ),
        (
            "active_overrides.length === 0",
            normalized,
            "Existing assignments are protected",
        ),
        (
            'name: "Dry run"',
            smoke,
            "Dry run is exercised",
        ),
        (
            'data-testid="core-layer-project-override-panel"',
            (
                ROOT
                / "web/src/components/admin/CoreLayerProjectOverridePanel.tsx"
            ).read_text(encoding="utf-8"),
            "Core override panel exposes a stable test boundary",
        ),
        (
            'getByTestId(',
            smoke,
            "Lifecycle controls are scoped to the Core panel",
        ),
        (
            'corePanel.locator("select").first()',
            normalized,
            "Project selector is resolved inside the Core panel",
        ),
        (
            'name: "Use for this project"',
            smoke,
            "Project apply is exercised",
        ),
        (
            'name: "Roll back"',
            smoke,
            "Rollback is exercised",
        ),
        (
            "PROJECT_OVERRIDE",
            smoke,
            "Effective project precedence is verified",
        ),
        (
            "Emergency rollback",
            smoke,
            "Failure cleanup is guarded",
        ),
        (
            "core-layer-project-override-applied.png",
            smoke,
            "Applied screenshot is captured",
        ),
        (
            "await corePanel.screenshot({",
            smoke,
            "Large readiness page is not captured full-page",
        ),
        (
            "core-layer-project-override-rolled-back.png",
            smoke,
            "Rolled-back screenshot is captured",
        ),
    ]

    for needle, source, label in checks:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    prohibited = [
        "password",
        "DB_PASSWORD",
        "agrios_dev_2026",
    ]
    combined = smoke + "\n" + runner
    for needle in prohibited:
        if needle in combined:
            raise AssertionError(
                f"Smoke script contains credential material: {needle}"
            )

    print("PASS No password or database credential is embedded")
    print(
        "CORE LAYER PROJECT OVERRIDE PLAYWRIGHT "
        "SMOKE STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
