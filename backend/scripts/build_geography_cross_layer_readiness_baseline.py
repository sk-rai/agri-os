#!/usr/bin/env python3
"""Build a read-only consolidated geography cross-layer readiness baseline."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

CLIMATE_REPORT = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness/"
    "climate_agro_ecology_readiness_report.json"
)
CORE_MANIFEST = ROOT / (
    "data/staged/core_stack/core_stack_climate_layer_manifest.json"
)
OVERLAY_SUMMARY = ROOT / (
    "data/staged/core_stack/nwdp_full_overlay_runs/"
    "20260829_full_national_2worker/"
    "combined_national_overlay_summary.json"
)
OUTPUT = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness/"
    "geography_cross_layer_readiness_baseline.json"
)

EXPECTED_SHA256 = {
    "climate_readiness": (
        "daf108a90d95d6ec4af1f467f73315b7506b9426868004251b5b81d0b62b6f41"
    ),
    "core_layer_manifest": (
        "430e03172e4524c3d970b0ae2ff4861eaf78572efc8cd6ba61b6426f39b9d758"
    ),
    "national_overlay": (
        "6fdea1f102d8dba49ee721f9939e83ddcf94ccd350f8fa7087f0adf25eb91c94"
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def normalized_state(value: str) -> str:
    aliases = {
        "andaman and nicobar islands": "Andaman And Nicobar Islands",
        "dadra and nagar haveli and daman diu": (
            "Dadra And Nagar Haveli And Daman And Diu"
        ),
        "jammu kashmir": "Jammu & Kashmir",
        "jammu and kashmir": "Jammu & Kashmir",
        "nct of delhi": "Delhi",
        "orissa": "Odisha",
        "pondicherry": "Puducherry",
        "the dadra and nagar haveli and daman and diu": (
            "Dadra And Nagar Haveli And Daman And Diu"
        ),
    }
    normalized = " ".join(value.strip().split())
    return aliases.get(normalized.casefold(), normalized)


def read_overlay_states(
    overlay: dict[str, Any],
) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []

    for relative_path in overlay["summaries"]:
        path = ROOT / relative_path
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                states.append(
                    {
                        "state_or_ut": normalized_state(row["state_or_ut"]),
                        "healthy": row["healthy"].strip().casefold() == "true",
                        "eligible_candidate_count": int(
                            row["eligible_candidate_count"]
                        ),
                        "overlaid_count": int(row["overlaid_count"]),
                        "invalid_or_missing_geometry_count": int(
                            row["invalid_or_missing_geometry_count"]
                        ),
                    }
                )

    return sorted(states, key=lambda row: row["state_or_ut"])


def checksum_payload(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    climate = load_json(CLIMATE_REPORT)
    core = load_json(CORE_MANIFEST)
    overlay = load_json(OVERLAY_SUMMARY)

    source_hashes = {
        "climate_readiness": sha256(CLIMATE_REPORT),
        "core_layer_manifest": sha256(CORE_MANIFEST),
        "national_overlay": sha256(OVERLAY_SUMMARY),
    }

    overlay_states = read_overlay_states(overlay)
    overlay_by_state = {
        row["state_or_ut"]: row
        for row in overlay_states
    }

    excluded_states = sorted(
        normalized_state(value)
        for value in overlay["excluded_zero_eligible_states"]
    )

    state_rows: list[dict[str, Any]] = []
    for climate_row in sorted(
        climate["state_summary"],
        key=lambda row: row["state_or_ut"],
    ):
        state = normalized_state(climate_row["state_or_ut"])
        overlay_row = overlay_by_state.get(state)

        district_count = int(climate_row["district_count"])
        districts_with_mapping = int(
            climate_row["districts_with_climate_mapping"]
        )
        districts_without_mapping = int(
            climate_row["districts_without_climate_mapping"]
        )

        state_rows.append(
            {
                "state_or_ut": state,
                "climate_readiness_state_row_present": True,
                "canonical_lgd_village_count": int(
                    climate_row["lgd_village_count"]
                ),
                "district_count": district_count,
                "districts_with_climate_mapping": districts_with_mapping,
                "districts_without_climate_mapping": districts_without_mapping,
                "district_climate_coverage_ratio": (
                    round(districts_with_mapping / district_count, 6)
                    if district_count
                    else 0.0
                ),
                "crop_climate_rule_count": int(
                    climate_row["crop_climate_rule_count"]
                ),
                "nwdp_overlay_eligible_candidate_count": (
                    overlay_row["eligible_candidate_count"]
                    if overlay_row
                    else 0
                ),
                "nwdp_overlay_overlaid_count": (
                    overlay_row["overlaid_count"]
                    if overlay_row
                    else 0
                ),
                "nwdp_overlay_invalid_or_missing_geometry_count": (
                    overlay_row["invalid_or_missing_geometry_count"]
                    if overlay_row
                    else 0
                ),
                "nwdp_overlay_healthy": (
                    overlay_row["healthy"] if overlay_row else None
                ),
                "nwdp_overlay_zero_eligible_exclusion": (
                    state in excluded_states
                ),
            }
        )

    climate_state_names = {
        row["state_or_ut"]
        for row in state_rows
    }
    overlay_only_states = sorted(
        set(overlay_by_state) - climate_state_names
    )

    for state in overlay_only_states:
        overlay_row = overlay_by_state[state]
        state_rows.append(
            {
                "state_or_ut": state,
                "climate_readiness_state_row_present": False,
                "canonical_lgd_village_count": None,
                "district_count": None,
                "districts_with_climate_mapping": None,
                "districts_without_climate_mapping": None,
                "district_climate_coverage_ratio": None,
                "crop_climate_rule_count": None,
                "nwdp_overlay_eligible_candidate_count": (
                    overlay_row["eligible_candidate_count"]
                ),
                "nwdp_overlay_overlaid_count": (
                    overlay_row["overlaid_count"]
                ),
                "nwdp_overlay_invalid_or_missing_geometry_count": (
                    overlay_row[
                        "invalid_or_missing_geometry_count"
                    ]
                ),
                "nwdp_overlay_healthy": overlay_row["healthy"],
                "nwdp_overlay_zero_eligible_exclusion": False,
            }
        )

    state_rows.sort(key=lambda row: row["state_or_ut"])

    summary = climate["summary"]
    aggregate = overlay["aggregate"]

    missing_overlay_states = sorted(
        row["state_or_ut"]
        for row in state_rows
        if (
            row["state_or_ut"] not in overlay_by_state
            and row["state_or_ut"] not in excluded_states
        )
    )

    checks = {
        "automatic_actions_disabled": True,
        "climate_readiness_healthy": climate.get("healthy") is True,
        "core_layer_count_exact": core.get("layer_count") == 3,
        "core_layer_manifest_schema_exact": (
            core.get("schema_version")
            == "core_stack_climate_layer_manifest.v1"
        ),
        "district_counts_reconcile": (
            int(summary["districts_with_climate_mapping"])
            + int(summary["districts_without_climate_mapping"])
            == int(summary["state_district_row_count"])
        ),
        "national_overlay_complete": (
            int(aggregate["eligible_candidate_count"])
            == int(aggregate["overlaid_count"])
        ),
        "national_overlay_count_exact": (
            int(aggregate["overlaid_count"]) == 452_930
        ),
        "national_overlay_geometry_valid": (
            int(aggregate["invalid_or_missing_geometry_count"]) == 0
        ),
        "national_overlay_healthy": overlay.get("healthy") is True,
        "national_overlay_schema_exact": (
            overlay.get("schema_version")
            == "nwdp_core_agro_zone_full_national_2worker_summary.v1"
        ),
        "no_database_writes": True,
        "no_unexplained_overlay_state_gaps": not missing_overlay_states,
        "not_authorized": True,
        "source_hashes_pinned": source_hashes == EXPECTED_SHA256,
        "state_identity_unique": (
            len({row["state_or_ut"] for row in state_rows})
            == len(state_rows)
        ),
        "state_overlay_counts_reconcile": (
            sum(
                row["nwdp_overlay_eligible_candidate_count"]
                for row in state_rows
            )
            == int(aggregate["eligible_candidate_count"])
        ),
    }

    readiness = {
        "canonical_lgd_geography_available": True,
        "core_gee_layer_inventory_ready": core.get("layer_count") == 3,
        "district_climate_mapping_complete": (
            int(summary["districts_without_climate_mapping"]) == 0
        ),
        "national_nwdp_polygon_overlay_evidence_ready": (
            overlay.get("healthy") is True
            and int(aggregate["eligible_candidate_count"])
            == int(aggregate["overlaid_count"])
            and int(aggregate["invalid_or_missing_geometry_count"]) == 0
        ),
        "state_fallback_climate_mapping_available": (
            int(summary["state_scope_mapping_count"]) > 0
        ),
        "village_climate_mapping_available": (
            int(summary["village_scope_mapping_count"]) > 0
        ),
        "ready_for_admin_read_only_visibility": True,
        "ready_for_runtime_climate_activation": False,
        "ready_for_android_direct_gee_access": False,
    }

    result: dict[str, Any] = {
        "schema_version": "geography_cross_layer_readiness_baseline.v1",
        "status": "CROSS_LAYER_BASELINE_VERIFIED_NOT_AUTHORIZED",
        "healthy": all(checks.values()),
        "checks": checks,
        "source_artifacts": {
            "climate_readiness": {
                "path": str(CLIMATE_REPORT),
                "sha256": source_hashes["climate_readiness"],
                "schema_version": climate["schema_version"],
            },
            "core_layer_manifest": {
                "path": str(CORE_MANIFEST),
                "sha256": source_hashes["core_layer_manifest"],
                "schema_version": core["schema_version"],
            },
            "national_overlay": {
                "path": str(OVERLAY_SUMMARY),
                "sha256": source_hashes["national_overlay"],
                "schema_version": overlay["schema_version"],
            },
        },
        "canonical_geography": {
            "lgd_village_count": int(summary["lgd_village_count"]),
            "state_district_row_count": int(
                summary["state_district_row_count"]
            ),
        },
        "core_layers": [
            {
                "layer_type": row["layer_type"],
                "layer_name": row["layer_name"],
                "short_name": row["short_name"],
                "region_system": row["region_system"],
                "gee_asset_id": row["gee_asset_id"],
            }
            for row in core["layers"]
        ],
        "nwdp_overlay": {
            "eligible_candidate_count": int(
                aggregate["eligible_candidate_count"]
            ),
            "overlaid_count": int(aggregate["overlaid_count"]),
            "invalid_or_missing_geometry_count": int(
                aggregate["invalid_or_missing_geometry_count"]
            ),
            "healthy_state_count": int(aggregate["healthy_state_count"]),
            "excluded_zero_eligible_states": excluded_states,
            "layer_status_counts": aggregate["layer_status_counts"],
        },
        "climate_mapping": {
            "active_region_system_count": int(
                summary["active_region_system_count"]
            ),
            "active_climate_region_count": int(
                summary["active_climate_region_count"]
            ),
            "active_climate_mapping_count": int(
                summary["active_climate_mapping_count"]
            ),
            "district_scope_mapping_count": int(
                summary["district_scope_mapping_count"]
            ),
            "state_scope_mapping_count": int(
                summary["state_scope_mapping_count"]
            ),
            "village_scope_mapping_count": int(
                summary["village_scope_mapping_count"]
            ),
            "districts_with_climate_mapping": int(
                summary["districts_with_climate_mapping"]
            ),
            "districts_without_climate_mapping": int(
                summary["districts_without_climate_mapping"]
            ),
            "district_coverage_ratio": float(
                summary["climate_mapping_district_coverage_ratio"]
            ),
            "active_crop_count": int(summary["active_crop_count"]),
            "crops_with_climate_rules": int(
                summary["crops_with_climate_rule_count"]
            ),
            "crops_without_climate_rules": int(
                summary["active_crops_without_climate_rules_count"]
            ),
        },
        "readiness": readiness,
        "state_rows": state_rows,
        "unexplained_overlay_state_gaps": missing_overlay_states,
        "overlay_states_absent_from_climate_readiness": overlay_only_states,
        "policy": {
            "lgd_remains_canonical_geography": True,
            "core_layers_are_reference_intelligence": True,
            "android_calls_gee_directly": False,
            "database_writes_authorized": False,
            "runtime_climate_activation_authorized": False,
            "runtime_spatial_matching_authorized": False,
            "project_mapping_apply_authorized": False,
        },
        "database_writes_attempted": False,
    }

    checksum_source = dict(result)
    result["summary_checksum"] = checksum_payload(checksum_source)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
