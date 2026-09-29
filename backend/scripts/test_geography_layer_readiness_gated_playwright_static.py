#!/usr/bin/env python3
"""Static contract for gated geography-readiness Playwright smoke."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "web/smoke/geography_layer_readiness_gated_smoke.mjs"
RUNNER = ROOT / "web/scripts/run_geography_layer_readiness_gated_smoke.mjs"


def main() -> int:
    smoke = SMOKE.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    normalized = " ".join(smoke.split())

    checks = [
        ('from "playwright"', smoke, "Existing Playwright package is reused"),
        ("WEB_SWEEP_TOKEN", smoke, "Existing smoke token variable is reused"),
        (
            "create_web_ui_smoke_session.py",
            runner,
            "Existing authenticated session creator is reused",
        ),
        (
            'getByTestId( "geography-readiness-filters"',
            normalized,
            "Readiness controls use a stable test boundary",
        ),
        (
            'getByLabel("State / UT"',
            smoke,
            "State selector uses its accessible label",
        ),
        (
            'getByLabel("District"',
            smoke,
            "District selector uses its accessible label",
        ),
        (
            "readinessRequests.length !== 0",
            smoke,
            "Initial readiness request is forbidden",
        ),
        (
            "District selector was enabled before selecting a state",
            smoke,
            "District selection is state gated",
        ),
        (
            "Readiness lookup ran after state-only selection",
            smoke,
            "State-only readiness lookup is forbidden",
        ),
        (
            "Readiness lookup ran before explicit load",
            smoke,
            "District selection alone does not fetch",
        ),
        (
            'name: "Load readiness"',
            smoke,
            "Explicit readiness load is exercised",
        ),
        (
            "readinessRequests.length !== 1",
            smoke,
            "Exactly one readiness request is required",
        ),
        (
            'actualFilters.limit !== "50"',
            normalized,
            "Narrow readiness limit is verified",
        ),
        (
            "geography_layer_readiness_matrix.v1",
            smoke,
            "Readiness response schema is verified",
        ),
        (
            "Readiness response escaped the selected scope",
            smoke,
            "Returned rows are scope checked",
        ),
        (
            "Changing state did not clear district/readiness state",
            smoke,
            "State change reset is verified",
        ),
        (
            "read_only: true",
            smoke,
            "Smoke declares read-only behavior",
        ),
        (
            "geography-layer-readiness-gated.png",
            smoke,
            "Focused evidence screenshot is captured",
        ),
        (
            "fileURLToPath(import.meta.url)",
            runner,
            "Runner is independent of invocation directory",
        ),
        (
            "token_logged: false",
            runner,
            "Credential token is not logged",
        ),
    ]

    for needle, source, label in checks:
        if needle not in source:
            raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")

    prohibited = [
        'method: "POST"',
        'method: "PUT"',
        'method: "PATCH"',
        'method: "DELETE"',
        "password",
        "DB_PASSWORD",
        "agrios_dev_2026",
    ]
    combined = smoke + "\n" + runner
    present = [needle for needle in prohibited if needle in combined]
    if present:
        raise AssertionError(
            f"Read-only smoke contains forbidden operations: {present}"
        )

    print("PASS Smoke contains no writes or credential material")
    print(
        "GEOGRAPHY LAYER READINESS GATED PLAYWRIGHT "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
