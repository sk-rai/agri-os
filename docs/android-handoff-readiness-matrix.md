# Android Handoff Readiness Matrix

Status date: 2026-07-26

This matrix captures the current backend/admin readiness for Android handoff, including what is closed, what must be seeded before emulator testing, and what is intentionally deferred. It complements docs/android-backend-handoff-packet.md; the packet explains contracts, while this document tracks handoff decision status.

## Decision legend

- Ready for Android MVP: Android can integrate/test now using backend contracts and sample payloads.
- Seed before emulator testing: the contract exists, but local/demo data should be populated so Android testers see meaningful screens.
- Admin/backend only: not an Android surface for MVP; Android should not call it directly.
- Known later: intentionally deferred beyond MVP or beyond local handoff.
- Needs review: still open enough that we should decide before final Android handoff.

## Modular readiness overview

| Area | Current status | Evidence | Android action | Remaining work / decision |
| --- | --- | --- | --- | --- |
| Farmer mode | Ready for Android MVP | 01-mode-bootstrap.json, farmer/profile endpoints, profile readiness | Test login/profile capture as direct farmer | Confirm Android auth/profile hydration wiring against allowlist |
| Field-agent mode | Ready for Android MVP | GET /api/v1/field-agent/worklist, agent profiles/admin page, profile readiness | Test agent-assisted enrollment and worklist flows | Confirm Android role switching UX with real token/tenant data |
| Farmer associated with company/project | Ready for Android MVP | `backend/scripts/audit_android_emulator_persona_readiness.py`; 4 farmer-project enrollment fixtures present | Test farmer with project/company context and project-enabled crop workflow | None for MVP; keep deterministic fixture IDs documented for Android QA |
| Independent farmer | Ready for Android MVP | `backend/scripts/audit_android_emulator_persona_readiness.py`; 119 independent active farmers present | Test farmer without project enrollment; avoid company-only assumptions | None for MVP |
| Geography/PIN lookup | Ready for Android MVP | All-India OGD LGD/PIN data loaded locally; 03-pin-code-villages.json; PIN guardrail response | Use backend PIN guardrail; do not ship local PIN DB | Cloud deployment must run authoritative latest OGD apply from validated staged snapshot |
| Crop metadata | Seed before emulator testing | Crop taxonomy/admin pages; metadata audit target minimum is 15 crops | Render crop choices from backend | Ensure scenario seed pack covers representative crops used in Android tests |
| Inputs/products metadata | Ready after local seed; production verification later | Input/product catalogs; `docs/company-product-catalog-seed.md`; `backend/scripts/seed_company_product_catalog.py` | Render input/product choices from backend where exposed; keep organic/natural distinctions from backend metadata | Replace demo/reference products with manufacturer/regulator-verified product rows before production |
| Workflow templates/crop stages | Ready for MVP, needs hardening review | Workflow templates, versions, draft/publish, stage/recommendation admin edits, project workflow enablement | Render backend workflow/stage labels and transitions; do not hardcode stages | Formal decision-node/current-stage onboarding metadata remains known later/hardening |
| Dynamic labels/language readiness | Ready for core forms/content; seed translations before broad language QA | Backend-driven form labels/options; broadcast localized content; workflow stage names as configurable metadata | Android renders backend labels, language content, and option labels | Add language QA checklist and Hindi/local-language sample coverage for crops/stages/advisories |
| Finance summaries | Ready for Android MVP | Stage-cost/P&L endpoints, persisted config, fixed formula, sample payloads 22/23 | Android renders backend-computed summary; no local P&L math | None for MVP; later materialize aggregates when volume grows |
| Finance analytics/admin UI | Admin/backend ready | /finance-analytics admin page; 25-finance-analytics-summary.json; aggregate endpoint | Android may consume only if product wants farmer-facing analytics; otherwise admin-only | Decide whether Android MVP shows aggregate analytics or keeps it admin-only |
| Weather snapshots | Ready as saved backend snapshots; live provider deferred | Weather snapshot/latest endpoints and worker stubs | Render backend snapshot cards only | Live provider execution remains blocked until explicitly approved/configured |
| Soil enrichment | Ready as saved snapshots/readiness; live provider deferred | Soil enrichment summary/latest endpoints and worker stubs | Render backend readiness/snapshot cards only | Live provider adapters remain backend-controlled and approval-gated |
| Broadcast/advisories | Ready after local seed | Broadcast campaign/content/audience/delivery/read/ack; sample payloads 16-19; `backend/scripts/seed_android_emulator_advisories.py` | Android consumes assigned advisories/feed/detail/read/ack | Run the emulator advisory seed for selected local farmers before Android broadcast QA |
| Offline sync dependency behavior | Ready for Android MVP | 24-sync-dependency-error.json, sync closeout regression | Test dependency failure and retry behavior | Final replay order review with Android team |
| Company discovery/profile | Admin/backend ready after local seed | Company profile/discovery docs/admin pages; seeded manufacturer/company candidates from Screener/TNAU references | Android should not call company admin endpoints | Admin should review candidates before marking verified; public-source confidence improvements later |
| Global/non-India geography | Known later | India compatibility profile and all-India OGD path documented | Android should use hierarchy-profile, not hardcode India assumptions | Generic multi-country geo_entity migration later |

## Android persona test matrix

| Persona | Required local fixture | Must test | Expected backend-owned behavior |
| --- | --- | --- | --- |
| Direct farmer | User with FARMER role, farmer profile, one parcel, optional soil profile | Login, mode bootstrap, farmer profile read/write, parcel create/update, soil profile create/update, profile readiness | Forms/options/readiness come from backend; Android does not hardcode option lists |
| Field agent | User/agent profile with field-agent mode and assigned/enrollable farmers | Mode switch, worklist, assisted farmer/parcel/soil capture | Worklist and next actions come from backend readiness APIs |
| Company/project-associated farmer | Farmer enrolled in active project/company tenant with project workflows/inputs | Project context, enabled crop workflow, project input/product restrictions, advisories | Project workflow/input eligibility is backend-owned |
| Independent farmer | Farmer with no active project enrollment | Profile/parcel/soil/crop cycle capture without company assumptions | Core capture remains usable without project/company context |

## Emulator seed-data checklist

Before Android emulator testing, create or verify local fixtures for:

Verified on 2026-07-27 with `backend/scripts/audit_android_emulator_persona_readiness.py`:

- 123 active farmers;
- 97 active parcels;
- 65 farmers with active parcels;
- 4 company/project-associated farmers;
- 119 independent active farmers;
- 2 agent profiles;
- advisory fixtures present: 72 campaigns and 92 deliveries;
- crop/workflow/input/product metadata ready.


1. one direct farmer;
2. one field agent with worklist-visible farmer(s);
3. one company/project-associated farmer;
4. one independent farmer;
5. at least one active project with enabled crop workflow and input/product assignments;
6. representative crop/input/product metadata for the demo path via `backend/scripts/seed_company_product_catalog.py --tenant-id default --apply`;
7. generic published advisory campaigns with generated deliveries via `backend/scripts/seed_android_emulator_advisories.py --tenant-id default --limit-farmers 5 --apply`;
8. weather and soil sample snapshots for at least one parcel/location;
9. PIN examples covering valid postal PIN with LGD villages, valid postal PIN without LGD villages, and unknown PIN.

## Known later / not doing now

- Live weather/soil/provider execution is blocked until provider config approval, retry policy, and rate/cost guardrails are ready.
- Global non-India geography migration is later; MVP remains India-compatible while Android uses hierarchy metadata to avoid hardcoding.
- Formal workflow decision-node metadata and perennial/orchard current-stage onboarding are tracked as hardening; current stage/recommendation structures remain editable/versioned.
- Public company discovery source citation and confidence scoring are backend/admin hardening, not Android MVP blockers.
- Materialized finance aggregate tables are deferred; current finance analytics is a backend read-model over operational tables.

## Immediate next implementation slices

1. Build or update Android emulator fixture seed script for the four persona scenarios.
2. Add a language/readiness QA checklist for Hindi/local-language labels in forms, crop workflows, option sets, and advisories.
3. Review metadata audit output after scenario seed data to decide whether crop/input/product seed coverage is sufficient for Android handoff.
4. Keep `backend/scripts/seed_android_emulator_advisories.py` idempotent and rerun it whenever emulator farmer fixtures are refreshed.
