#!/usr/bin/env python3
"""Read-only consolidated geography and deferred-engineering audit."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings
from app.core.database import SessionLocal

SCHEMA_VERSION = "local_geography_completion_readiness.v1"
EXPECTED = {
    "states": 35, "districts": 779, "blocks": 7066, "villages": 600647,
    "pin_linked_villages": 560151, "effective_nwdp_villages": 487999,
    "active_runtime_villages": 467397, "fully_resolved": 454996,
    "pin_only": 105155, "nwdp_only": 33003, "unresolved": 7493,
}
FUTURE_WORK = [
    ("GEO_PIN_RECONCILIATION", "DATA_RECONCILIATION", "Resolve canonical villages without active matched PIN coverage.", "docs/state-wise-lgd-pin-nwdp-coverage-2026-10-02.md"),
    ("GEO_NWDP_RECONCILIATION", "DATA_RECONCILIATION", "Reconcile villages without effective NWDP mapping plus inactive and held cohorts.", "docs/geography-coverage-reconciliation-2026-09-24.md"),
    ("PROJECT_LOCAL_VILLAGE_ANDROID", "DEFERRED_PRODUCT_AUTHORIZATION", "Deliver reviewed project-local village identities without changing canonical LGD.", "docs/project-scoped-village-resolution-worklist-2026-10-02.md"),
    ("LOOKUP_PRODUCTION_INFRASTRUCTURE", "DEFERRED_CLOUD", "Add production Redis TLS/secrets, persistence, HA, backups, external monitoring, and exposure authorization.", "docs/nwdp-runtime-point-lookup-pilot-runbook.md"),
    ("GLOBAL_GEOGRAPHY_MODEL", "UNIMPLEMENTED_ARCHITECTURE", "Generalize geography beyond India while preserving stable India APIs.", "docs/global-geography-model-roadmap.md"),
    ("LIVE_PROVIDER_ADAPTERS", "DEFERRED_CLOUD", "Activate governed weather, soil, satellite, market, and other external adapters.", "docs/agrifabric-future-engineering-roadmap.md"),
    ("VILLAGE_GEOCODING", "NEEDS_RESEARCH", "Select and govern a village-coordinate geocoding source.", "docs/android-mvp-readiness-summary.md"),
    ("PRODUCT_SOURCE_VERIFICATION", "NEEDS_RESEARCH", "Replace demo/reference products with governed source verification.", "docs/android-mvp-readiness-summary.md"),
    ("ADMIN_TRANSLATION_OVERRIDES", "UNIMPLEMENTED_PRODUCT", "Add tenant/project translation management and reviewed native-language coverage.", "docs/backend-gap-closure-tracker.md"),
    ("DECISION_NODES_PERENNIAL_ONBOARDING", "UNIMPLEMENTED_PRODUCT", "Add formal branching decisions and current-stage orchard/perennial onboarding.", "docs/backend-metadata-readiness-roadmap.md"),
    ("HARVEST_SALE_NET_REALIZATION", "UNIMPLEMENTED_PRODUCT", "Extend costs through harvest, sale, receivables, and net realization.", "docs/agrifabric-future-engineering-roadmap.md"),
    ("OPERATIONAL_FINANCIAL_POSTING", "UNIMPLEMENTED_PRODUCT", "Derive bounded economic records from verified farm operations.", "docs/agrifabric-future-engineering-roadmap.md"),
    ("RECOMMENDATION_OUTCOME_CLOSURE", "UNIMPLEMENTED_PRODUCT", "Connect recommendations, execution variance, crop response, yield, quality, and economics.", "docs/agrifabric-future-engineering-roadmap.md"),
    ("MULTI_SEASON_MEMORY", "UNIMPLEMENTED_PRODUCT", "Add season comparisons, trends, benchmarking, and recurring-risk review.", "docs/agrifabric-future-engineering-roadmap.md"),
    ("PRODUCTION_HARVEST_PIPELINE", "UNIMPLEMENTED_PRODUCT", "Forecast crop area, stages, harvest windows, and production volume.", "docs/agrifabric-future-engineering-roadmap.md"),
    ("DELEGATED_ACCESS_HARDENING", "UNIMPLEMENTED_PRODUCT", "Add consent, task/time scope, masking, economics controls, and revocation.", "docs/agrifabric-future-engineering-roadmap.md"),
    ("VOICE_LOCAL_LANGUAGE_INTERACTION", "UNIMPLEMENTED_PRODUCT", "Add structured voice navigation, dictation, read-aloud, and reviewable capture.", "docs/agrifabric-future-engineering-roadmap.md"),
    ("GNSS_POSITIONING_EVIDENCE", "DEFERRED_RESEARCH", "Research raw-GNSS/CORS evidence and provenance-preserving processing.", "docs/agrifabric-future-engineering-roadmap.md"),
    ("MATERIALIZED_FINANCE_AGGREGATES", "DEFERRED_PRODUCT", "Materialize finance aggregates only when operational scale requires them.", "docs/android-mvp-readiness-summary.md"),
    ("INSURANCE_RISK_REVIEW", "ROADMAP_ONLY", "Build governed human-review evidence bundles before any risk scoring.", "docs/agrifabric-future-engineering-roadmap.md"),
]


def geography_counts(db):
    row = db.execute(text("""
with pins as (
 select distinct geography_village_id village_id
 from geography_village_pin_links where is_active and match_status='MATCHED'
), candidates as (
 select distinct c.proposed_village_id village_id
 from geography_boundary_crosswalk_candidates c
 join geography_boundary_import_batches b on b.id=c.import_batch_id
 where b.source_system='NWDP_GSI_VILLAGE_BOUNDARY'
   and c.proposed_village_id is not null
), runtime as (
 select distinct x.village_id
 from geography_boundary_runtime_crosswalks x
 join geography_boundary_runtime_features f on f.id=x.runtime_feature_id and f.is_active
 where x.is_active
), effective as (
 select village_id from candidates union select village_id from runtime
), classified as (
 select v.id,(p.village_id is not null) has_pin,(e.village_id is not null) has_nwdp
 from geography_villages v
 left join pins p on p.village_id=v.id
 left join effective e on e.village_id=v.id
 where v.is_active
)
select
 (select count(*) from geography_states where is_active) states,
 (select count(*) from geography_districts where is_active) districts,
 (select count(*) from geography_blocks where is_active) blocks,
 count(*) villages,
 count(*) filter(where has_pin) pin_linked_villages,
 count(*) filter(where has_nwdp) effective_nwdp_villages,
 (select count(*) from runtime) active_runtime_villages,
 count(*) filter(where has_pin and has_nwdp) fully_resolved,
 count(*) filter(where has_pin and not has_nwdp) pin_only,
 count(*) filter(where not has_pin and has_nwdp) nwdp_only,
 count(*) filter(where not has_pin and not has_nwdp) unresolved
from classified
""")).mappings().one()
    return {key: int(value) for key, value in row.items()}


def operations(db):
    return dict(db.execute(text("""
select
 (select version_num from alembic_version) migration_head,
 (select count(*) from geography_project_village_resolutions) project_resolution_rows,
 (select count(*) from geography_project_village_resolution_events) project_resolution_events,
 (select count(*) from geography_boundary_runtime_features where is_active) active_runtime_features,
 (select count(*) from geography_boundary_runtime_crosswalks where is_active) active_runtime_crosswalks,
 (select count(*) from geography_boundary_crosswalk_candidates where is_active) active_candidates,
 (select count(*) from geography_boundary_crosswalk_candidates where promotion_status='PROMOTED') promoted_candidates,
 (select count(*) from geography_boundary_project_matches where is_active) active_project_matches
""")).mappings().one())


def redis_posture():
    result = {"configured": bool(settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL), "ping": None}
    if not result["configured"]:
        return result
    try:
        import redis
        result["ping"] = bool(redis.Redis.from_url(
            settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL,
            socket_connect_timeout=2, socket_timeout=2
        ).ping())
    except Exception as exc:
        result.update(ping=False, error_type=type(exc).__name__)
    return result


def git_posture():
    lines = subprocess.run(
        ["git", "status", "--short", "--branch"], cwd=ROOT,
        check=True, capture_output=True, text=True
    ).stdout.splitlines()
    return {
        "branch": lines[0] if lines else "",
        "tracked_change_count": sum(1 for line in lines[1:] if not line.startswith("??")),
        "untracked_entry_count": sum(1 for line in lines[1:] if line.startswith("??")),
    }


def markdown(payload):
    g, o = payload["geography"], payload["operations"]
    labels = [
        ("states", "Active states/UTs"), ("districts", "Active districts"),
        ("blocks", "Active blocks/subdistricts"), ("villages", "Active canonical villages"),
        ("pin_linked_villages", "Villages with PIN"), ("effective_nwdp_villages", "Villages with effective NWDP"),
        ("active_runtime_villages", "Villages with active runtime"), ("fully_resolved", "FULLY_RESOLVED"),
        ("pin_only", "PIN_ONLY"), ("nwdp_only", "NWDP_ONLY"), ("unresolved", "UNRESOLVED"),
    ]
    lines = [
        "# Local geography completion and engineering readiness — 2026-10-03", "",
        "## Executive conclusion", "",
        "The local geography control plane is operational and regression-backed. "
        "This does not mean every village is resolved or that cloud/public exposure is authorized.", "",
        "## Current geography baseline", "", "| Measure | Count |", "| --- | ---: |",
    ]
    lines += [f"| {label} | {g[key]:,} |" for key, label in labels]
    lines += [
        "", "The four resolution classes partition the canonical village total exactly.", "",
        "## Local operational posture", "",
        f"- Database migration head: {o['migration_head']}.",
        f"- Active runtime features/crosswalks: {o['active_runtime_features']:,} / {o['active_runtime_crosswalks']:,}.",
        f"- Project resolution rows/events after tests: {o['project_resolution_rows']} / {o['project_resolution_events']}.",
        f"- Effective local lookup enabled: {payload['configuration']['effective_lookup_enabled']}.",
        f"- Effective local limiter enabled: {payload['configuration']['effective_limiter_enabled']}.",
        f"- Project resolution activation enabled: {payload['configuration']['project_resolution_activation_enabled']}.",
        "- Customer, Android, public, and production lookup exposure remain unauthorized.", "",
        "## Future engineering work reconciled from repository roadmaps", "",
        "These are planned or deferred items, not local-completion blockers unless separately prioritized.", "",
        "| Work item | Classification | Source |", "| --- | --- | --- |",
    ]
    lines += [f"| {item['summary']} | {item['status']} | {item['source']} |" for item in payload["future_work"]]
    lines += [
        "", "## Decision boundary", "",
        "Continue local work only for explicitly prioritized reconciliation or product scope. "
        "Production Redis, live providers, public/Android lookup exposure, and HA/monitoring belong "
        "to cloud deployment. Roadmap-only intelligence must not be presented as operational.", "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    future = [
        {"id": row[0], "status": row[1], "summary": row[2], "source": row[3], "local_blocker": False}
        for row in FUTURE_WORK
    ]
    missing = [item["source"] for item in future if not (ROOT / item["source"]).is_file()]
    with SessionLocal() as db:
        geo, ops = geography_counts(db), operations(db)
    checks = {
        "expected_geography_baseline": geo == EXPECTED,
        "resolution_partition_exact": geo["fully_resolved"] + geo["pin_only"] + geo["nwdp_only"] + geo["unresolved"] == geo["villages"],
        "runtime_features_crosswalks_exact": ops["active_runtime_features"] == ops["active_runtime_crosswalks"] == EXPECTED["active_runtime_villages"],
        "migration_head_065": ops["migration_head"] == "065",
        "project_resolution_tests_cleaned": ops["project_resolution_rows"] == 0 and ops["project_resolution_events"] == 0,
        "future_work_sources_exist": not missing,
        "future_work_not_local_blocking": not any(item["local_blocker"] for item in future),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASSED" if all(checks.values()) else "FAILED",
        "healthy": all(checks.values()), "read_only": True, "checks": checks,
        "geography": geo,
        "geography_gaps": {
            "without_pin": geo["villages"] - geo["pin_linked_villages"],
            "without_effective_nwdp": geo["villages"] - geo["effective_nwdp_villages"],
            "without_active_runtime": geo["villages"] - geo["active_runtime_villages"],
        },
        "operations": ops,
        "configuration": {
            "repository_lookup_default": False, "repository_limiter_default": False,
            "effective_lookup_enabled": settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED,
            "effective_limiter_enabled": settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED,
            "project_resolution_activation_enabled": settings.PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED,
        },
        "redis": redis_posture(), "repository": git_posture(),
        "future_work": future, "missing_future_work_sources": missing,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    args.output_md.write_text(markdown(payload))
    print(json.dumps(payload, indent=2, default=str))
    if not payload["healthy"]:
        raise SystemExit("LOCAL GEOGRAPHY COMPLETION READINESS AUDIT FAILED")
    print("LOCAL GEOGRAPHY COMPLETION READINESS AUDIT PASSED")


if __name__ == "__main__":
    main()
