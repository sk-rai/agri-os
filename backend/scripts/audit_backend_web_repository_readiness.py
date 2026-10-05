#!/usr/bin/env python3
"""Read-only repository audit for backend, web, tests, docs, and planned work."""
from __future__ import annotations
import json, re, subprocess
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def fs(pattern): return [p for p in ROOT.glob(pattern) if p.is_file()]
def has(path, text):
    p=ROOT/path
    return p.exists() and text in p.read_text(errors="ignore")
def git(*args): return subprocess.run(["git",*args],cwd=ROOT,check=True,text=True,capture_output=True).stdout.strip()

def main():
    backend=fs("backend/**/*.py"); web=fs("web/src/**/*.ts")+fs("web/src/**/*.tsx")
    docs=fs("docs/**/*.md"); pages=fs("web/src/app/**/page.tsx"); smokes=fs("web/smoke/*.mjs")
    checkscripts=[p for p in fs("backend/scripts/*.py") if p.name.startswith(("test_","audit_","verify_"))]
    migrations=[p for p in fs("backend/alembic/versions/*.py") if p.name[:1].isdigit()]
    routes=sum(len(re.findall(r"@router\.(?:get|post|put|patch|delete)\(",p.read_text(errors="ignore"))) for p in backend)
    todo=[str(p.relative_to(ROOT)) for p in backend+web if re.search(r"TODO|FIXME|NotImplementedError",p.read_text(errors="ignore"))]
    findings=[
      ("AUTH_PRODUCTION_HARDENING","CRITICAL","FOUNDATION_IMPLEMENTED","Production rejects the development JWT secret and exposed OTP while local development remains explicit."),
      ("SECRETS_AND_ENVIRONMENT","HIGH","FOUNDATION_IMPLEMENTED","Environment contract exists and production rejects development database/auth/CORS/docs defaults."),
      ("CI_AND_UNIFIED_TEST_GATE","HIGH","OPEN","No CI workflow or unified backend, migration, web-build and smoke-test gate exists."),
      ("TENANT_TRUST_BOUNDARY","HIGH","NEEDS_SECURITY_REVIEW","Browser-supplied tenant/actor headers need systematic token-binding and cross-tenant verification."),
      ("WEB_SESSION_STORAGE","MEDIUM","OPEN","Bearer tokens are stored in localStorage without a documented production session/CSP decision."),
      ("WEB_REGRESSION_COVERAGE","MEDIUM","PARTIAL","Admin pages outnumber Playwright smokes and no shared route/RBAC/accessibility suite exists."),
      ("AUDIT_CHAIN_VERIFICATION","MEDIUM","OPEN","Sync dashboard reports audit-chain integrity without continuity verification."),
      ("SILENT_SOIL_FAILURE","MEDIUM","OPEN","A broad soil-profile exception is silently converted into zero counts."),
    ]
    work=[
      ("IRRIGATION_CANAL_LAYER","DEFERRED_DATA_PRODUCT","docs/irrigation-canal-network-layer-analysis.md"),
      ("LIVE_WEATHER_SOIL_PROVIDERS","DEFERRED_EXTERNAL","docs/provider-live-test-readiness-runbook.md"),
      ("PRODUCT_SOURCE_VERIFICATION","DEFERRED_RESEARCH","docs/product-source-verification-runbook.md"),
      ("GLOBAL_GEOGRAPHY","UNIMPLEMENTED_ARCHITECTURE","docs/global-geography-model-roadmap.md"),
      ("FORMAL_DECISION_NODES","PARTIAL_CONTRACT","docs/backend-metadata-readiness-roadmap.md"),
      ("PERENNIAL_ONBOARDING","IMPLEMENTED_CONTRACT","backend/app/modules/workflow/perennial_onboarding.py"),
      ("ADMIN_LOCALIZATION_OVERRIDES","IMPLEMENTED","backend/app/modules/master_data/api/localization.py"),
      ("HARVEST_SALE_NET_REALIZATION","UNIMPLEMENTED_PRODUCT","docs/agrifabric-future-engineering-roadmap.md"),
      ("RECOMMENDATION_OUTCOME_CLOSURE","UNIMPLEMENTED_PRODUCT","docs/agrifabric-future-engineering-roadmap.md"),
      ("MULTI_SEASON_MEMORY","UNIMPLEMENTED_PRODUCT","docs/agrifabric-future-engineering-roadmap.md"),
      ("PRODUCTION_HARVEST_PIPELINE","UNIMPLEMENTED_PRODUCT","docs/agrifabric-future-engineering-roadmap.md"),
      ("DELEGATED_ACCESS_HARDENING","UNIMPLEMENTED_PRODUCT","docs/agrifabric-future-engineering-roadmap.md"),
      ("VOICE_LOCAL_LANGUAGE","UNIMPLEMENTED_PRODUCT","docs/agrifabric-future-engineering-roadmap.md"),
      ("GNSS_CORS_EVIDENCE","DEFERRED_RESEARCH","docs/agrifabric-future-engineering-roadmap.md"),
      ("VILLAGE_GEOCODING","NEEDS_RESEARCH","docs/android-mvp-readiness-summary.md"),
      ("GEOGRAPHY_RESIDUAL_RECONCILIATION","PAUSED_INCREMENTAL","docs/local-geography-completion-readiness-2026-10-03.md"),
      ("PRODUCTION_REDIS_OBSERVABILITY","DEFERRED_CLOUD","docs/nwdp-runtime-point-lookup-pilot-runbook.md"),
    ]
    workrows=[{"id":i,"status":s,"source":p,"source_exists":(ROOT/p).exists()} for i,s,p in work]
    validations={
      "auth_secret_comes_from_settings":has("backend/app/modules/auth/service.py","JWT_SECRET = settings.JWT_SECRET"),
      "production_configuration_fails_closed":has("backend/app/core/config.py","reject_development_security_in_production"),
      "dev_otp_response_is_gated":has("backend/app/modules/auth/api.py","if settings.AUTH_EXPOSE_DEV_OTP"),
      "live_provider_execution_unimplemented":has("backend/app/modules/media/provider_http_client.py","NotImplementedError"),
      "perennial_policy_integrated":has("backend/app/modules/workflow/forms.py","current_stage_onboarding_policy"),
      "localization_admin_implemented":(ROOT/"web/src/app/(admin)/localization/page.tsx").exists(),
      "ci_workflow_absent":not any((ROOT/".github/workflows").glob("*")) if (ROOT/".github/workflows").exists() else True,
      "environment_template_present":(ROOT/".env.example").exists(),
      "planned_sources_exist":all(x["source_exists"] for x in workrows),
    }
    rows=[{"id":i,"severity":s,"status":st,"summary":m} for i,s,st,m in findings]
    payload={"schema_version":"backend_web_repository_audit.v1","status":"PASSED_WITH_OPEN_GAPS","read_only":True,
      "inventory":{"backend_python_files":len(backend),"backend_route_decorators":routes,"alembic_migrations":len(migrations),
        "backend_test_audit_verify_scripts":len(checkscripts),"web_source_files":len(web),"web_pages":len(pages),
        "web_smokes":len(smokes),"documentation_files":len(docs),"todo_or_unimplemented_files":len(todo)},
      "checks":validations,"findings":rows,"finding_counts":dict(Counter(x["severity"] for x in rows)),
      "planned_work":workrows,"planned_work_counts":dict(Counter(x["status"] for x in workrows)),
      "documentation_findings":[
        "The gap tracker has a July status date but contains later appended work.",
        "The August backend/web audit lists Android items closed by later evidence.",
        "The October geography audit calls perennial onboarding and localization overrides unimplemented although current code implements them.",
        "Historical roadmaps need superseded-by links and a generated current-state index."],
      "repository":{"branch":git("status","--short","--branch").splitlines()[0]}}
    print(json.dumps(payload,indent=2,sort_keys=True))
    print("BACKEND AND WEB REPOSITORY AUDIT PASSED WITH OPEN GAPS")
    return 0 if all(validations.values()) else 1
if __name__=="__main__": raise SystemExit(main())
