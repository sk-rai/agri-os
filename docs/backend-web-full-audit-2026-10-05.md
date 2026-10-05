# Backend and web full repository audit — 2026-10-05

## Executive conclusion

The backend and admin web app are broad, locally testable, and unusually well supplied with deterministic regression scripts. They are suitable for controlled local/demo operation. They are **not production-ready** without auth/secrets hardening, a repeatable CI gate, and an explicit deployment/observability design.

This audit reconciles current code with historical roadmaps. An item mentioned as pending in an old Markdown file is not treated as open unless current code and newer evidence agree.

## Inventory and evidence model

The repository currently contains 759 backend Python files, 356 FastAPI route decorators, 67 numbered Alembic migrations through revision `067`, 369 backend test/audit/verification scripts, 46 Next.js pages, 32 Playwright helpers/smokes, and more than 200 Markdown records. Counts are rerun by `backend/scripts/audit_backend_web_repository_readiness.py`.

Evidence precedence:

1. current code and migration chain;
2. executable behavior/static tests and Playwright smokes;
3. newest bounded readiness/audit documents;
4. older trackers and roadmaps;
5. aspirational design documents.

## Release blockers

### Critical — production authentication is still development-mode

- `backend/app/modules/auth/service.py` contains a hard-coded JWT signing secret.
- `backend/app/modules/auth/api.py` returns the generated OTP in the response body.
- SMS delivery is still a TODO.

Before external deployment, require the signing key from secret configuration, suppress OTP values outside an explicit test mode, connect an approved OTP provider, add abuse throttling tests, and test key/device revocation.

### High — secrets and environment contract

`backend/app/core/config.py` supplies a development database password by default and there is no canonical `.env.example`. Production settings must fail closed when secrets are missing. Document CORS origins, docs exposure, Redis, providers, database TLS, and migration ownership.

### High — CI and unified regression gate

There are many useful scripts but no `.github/workflows`, pytest configuration, Playwright configuration, or single test command. Add a deterministic gate covering Python syntax/imports, clean-database Alembic upgrade, backend suites, Next lint/build, selected Playwright smokes, contract drift, production defaults, and cleanup assertions.

### High — tenant and actor trust boundary needs a security audit

The browser supplies `X-Tenant-ID` and `X-Actor-ID` from localStorage. Many endpoints separately verify token identity and permissions, but that repo-wide invariant has not been proven. Audit every non-reference route so tenant/actor identity is derived from or compared with the verified token. Header presence alone is not authorization.

## Engineering gaps

| Gap | Status | Consequence / next action |
| --- | --- | --- |
| Web bearer token in localStorage | Open | XSS can exfiltrate it. Choose hardened cookie/BFF or enforce CSP and document accepted risk. |
| Audit-chain integrity placeholder | Open | `sync/dashboard.py` reports integrity without checking hash continuity. Implement it or rename the field. |
| Silent soil-profile exception | Open | A broad exception is swallowed in a report path. Log it and distinguish unavailable from zero. |
| Web smoke coverage | Partial | Many high-value pages lack a directly named smoke. Add shared auth/navigation/RBAC and risk-based page tests. |
| Accessibility/browser matrix | Missing | Add a focused axe, keyboard, and multi-browser gate. |
| Dependency/security automation | Missing | Add scheduled vulnerability scanning and a controlled update policy. |
| Backup/recovery and observability | Deferred cloud | Define DB/Redis restore drills, logs, metrics, alerts, ownership, and incident runbooks. |
| API lifecycle discipline | Partial | Add OpenAPI snapshot review, endpoint ownership, and a deprecation registry. |

## Implemented but described as pending in older documents

- **Admin localization overrides:** model, migration, API, runtime overlay, admin page, browser smoke, and Android delivery evidence exist. The older gap tracker still labels it deferred.
- **Perennial/current-stage onboarding:** `workflow/perennial_onboarding.py` is integrated into workflow forms and tested. The 2026-10-03 geography audit still calls it unimplemented.
- **Several Android audit items:** the 2026-08-12 audit lists work that later tracker entries close.
- **Project-local villages:** single-admin web authorization, scoped catalog, retirement, audit, and Playwright lifecycle are implemented. No new Android work is required because this is intentionally a backend web-admin function.

These are documentation gaps. Add explicit superseded-by metadata or a generated current-state index instead of appending contradictory status blocks.

## Planned work still genuinely pending

### Data, geography, and research

- **Irrigation/canal layer — deferred data/product work.** NWIC/CWC data can be plausibility evidence, never proof of water availability. It still needs governed acquisition, license/refresh review, normalization, proximity bands, provenance, admin visibility, and false-positive evaluation.
- **Residual PIN/NWDP/canonical reconciliation — paused incremental work.** Resume only with new authoritative evidence or a bounded campaign.
- **Village geocoding — needs research.** Select a licensed, refreshable coordinate source and preserve accuracy/provenance.
- **Global/non-India geography — unimplemented architecture.** Preserve India API stability while adding country-specific hierarchy profiles.
- **Product source verification — deferred research.** Catalog data remains demo/reference quality until official sources and review states are governed.
- **Vernacular village evidence — blocked on data.** The framework exists but the current cohorts have no usable vernacular strings.

### External/cloud capabilities

- Live weather/soil HTTP execution is intentionally unwired; the provider boundary raises `NotImplementedError`.
- Satellite/NDVI, market, sensor, and related adapters require credentials, legal review, budgets, rate/retry policy, monitoring, and provenance.
- Production Redis needs TLS/secrets, persistence, HA, restore drills, capacity policy, and monitoring.

### Product extensions

- Formal decision-node execution is partial: metadata contracts exist, but the governed branching state machine, authoring UI, validation, and transition tests do not.
- Harvest/sale/receivables/net realization, operational-to-financial posting, recommendation-to-outcome closure, multi-season memory, and harvest forecasting remain unimplemented.
- Delegated-access hardening, structured voice/local-language interaction, and raw-GNSS/CORS evidence remain roadmap/research work.
- Materialized finance aggregates remain an optimization, not a correctness gap.

## Requirements and test-record assessment

- Backend dependencies are pinned, but there is no lock/hash or reproducible image.
- Web has build/lint scripts but no unit/integration test script.
- Regression scripts and smokes are decentralized and lack a manifest/runner.
- Clean bootstrap to migration `067` should be a CI rehearsal, not only an upgraded developer DB.
- Untracked staging evidence/screenshots need retention, privacy, checksum, and artifact-governance policy.

## Recommended execution order

1. Harden auth, secrets, OTP behavior, CORS/docs exposure, and tenant/actor invariants.
2. Add one local/CI quality gate with clean migration and web build coverage.
3. Fix misleading integrity/error reporting and add observability contracts.
4. Add risk-based web RBAC/navigation/accessibility smokes.
5. Generate a current-state documentation index and mark historical plans superseded.
6. Choose one product track: verified products, decision-node execution, harvest economics, or canal research.

## Scope boundaries

This read-only audit does not authorize production exposure, provider calls, geography mutation, Android changes, or automatic geography resolution.

Run:

```bash
cd backend
../venv/bin/python scripts/test_backend_web_repository_audit_static.py
../venv/bin/python scripts/audit_backend_web_repository_readiness.py
```
