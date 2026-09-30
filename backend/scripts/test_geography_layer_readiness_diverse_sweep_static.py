#!/usr/bin/env python3
"""Static safety contract for the diverse readiness Playwright sweep."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SMOKE = (
    ROOT / "web/smoke/geography_layer_readiness_gated_smoke.mjs"
)
RUNNER = (
    ROOT / "web/scripts/run_geography_layer_readiness_diverse_sweep.mjs"
)


def main() -> int:
    smoke = SMOKE.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    checks = [
        (
            "READINESS_SWEEP_STATE",
            smoke,
            "Existing gated smoke accepts a state anchor",
        ),
        (
            "Requested state was not found",
            smoke,
            "Missing state anchors fail closed",
        ),
        (
            "READINESS_SWEEP_MAX_MS",
            smoke,
            "Read latency ceiling is configurable",
        ),
        (
            "readinessElapsedMs > maxReadMs",
            smoke,
            "Each browser read has a latency ceiling",
        ),
        (
            "option.value !== firstState.value",
            smoke,
            "Reset uses a different state",
        ),
        (
            "create_web_ui_smoke_session.py",
            runner,
            "Existing authenticated session creator is reused",
        ),
        (
            "geography_layer_readiness_gated_smoke.mjs",
            runner,
            "Existing gated UI lifecycle is reused",
        ),
        (
            '"Andaman And Nicobar Islands"',
            runner,
            "Island geography is sampled",
        ),
        (
            '"Assam"',
            runner,
            "Northeast geography is sampled",
        ),
        (
            '"Karnataka"',
            runner,
            "Plateau geography is sampled",
        ),
        (
            '"Rajasthan"',
            runner,
            "Arid geography is sampled",
        ),
        (
            '"Kerala"',
            runner,
            "Coastal geography is sampled",
        ),
        (
            "for (const state of states)",
            runner,
            "Every state fixture runs independently",
        ),
        (
            "token_logged: false",
            runner,
            "Credential token is not logged",
        ),
        (
            "read_only: true",
            runner,
            "Sweep declares read-only behavior",
        ),
        (
            "fileURLToPath(import.meta.url)",
            runner,
            "Runner is independent of invocation directory",
        ),
    ]

    for needle, source, label in checks:
        if needle not in source:
            raise AssertionError(
                f"{label}: missing {needle!r}"
            )
        print(f"PASS {label}")

    prohibited = [
        'method: "POST"',
        'method: "PUT"',
        'method: "PATCH"',
        'method: "DELETE"',
        "DB_PASSWORD",
        "agrios_dev_2026",
        "geography_layer_readiness_snapshots set",
        "geography_layer_readiness_snapshots insert",
    ]

    present = [
        needle for needle in prohibited
        if needle in runner.lower()
    ]
    if present:
        raise AssertionError(
            "Diverse sweep contains forbidden operations: "
            f"{present}"
        )

    print(
        "PASS Diverse sweep contains no application writes "
        "or credential material"
    )
    print(
        "GEOGRAPHY LAYER READINESS DIVERSE SWEEP "
        "STATIC CONTRACT PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
