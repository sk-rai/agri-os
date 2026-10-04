# Local geography completion and engineering readiness — 2026-10-03

## Executive conclusion

The local geography control plane is operational and regression-backed through
Alembic revision 065. Canonical/project geography administration, national
runtime boundaries, the authenticated local lookup pilot, Redis rate limiting,
observability, fail-closed recovery, village-resolution reporting, and the
project-scoped proposal lifecycle have implementation and regression evidence.

This is not the same as complete village resolution or production readiness.
Data reconciliation remains measurable, and cloud infrastructure, wider
exposure, provider integration, Android project-local delivery, and broader
product extensions remain separately governed.

## Current geography baseline

| Measure | Current count |
| --- | ---: |
| Active states/UTs | 35 |
| Active districts | 779 |
| Active blocks/subdistricts | 7,066 |
| Active canonical villages | 600,647 |
| Villages with active matched PIN | 560,151 |
| Villages with effective NWDP mapping | 487,999 |
| Villages with active NWDP runtime | 467,397 |
| FULLY_RESOLVED | 454,996 |
| PIN_ONLY | 105,155 |
| NWDP_ONLY | 33,003 |
| UNRESOLVED | 7,493 |

The four resolution classes sum exactly to 600,647. The measurable gaps are
40,496 villages without PIN, 112,648 without effective NWDP mapping, and
133,250 without active NWDP runtime. These are reconciliation and governance
queues, not evidence that the canonical LGD hierarchy is unusable.

The national runtime campaign documentation also retains 65,005 inactive
rehabilitation rows across normalized-direct, parent-drift, and district-drift
cohorts, plus a separately held 14,773-row cohort. Those source-feature cohorts
must not be added directly to canonical-village gap counts because they use a
different unit of analysis and may contain duplication or unresolved identity.

## Implemented and locally validated

- Canonical LGD hierarchy and PIN relationships are usable for current Android
  and project workflows.
- State-wise LGD/PIN/NWDP reporting uses the corrected effective mapping union.
- The active runtime set contains 467,397 feature/crosswalk pairs.
- The local authenticated-admin lookup pilot is enabled in WSL, guarded by
  Redis actor/tenant/global quotas and privacy-safe observability.
- Anonymous, customer, Android, public, and production lookup access remain
  unauthorized.
- Project village resolution supports read-only prioritization, NWDP candidate
  search, validation, proposals, independent approval/rejection, proposer
  cancellation, gated activation, rollback, and immutable history.
- PROJECT_LOCAL_ADDITION remains disabled.
- Repository-safe defaults retain lookup, limiter, and project-resolution
  activation gates as false even where the local WSL pilot has explicitly
  enabled lookup and limiter configuration.

## Future engineering work reconciled from repository roadmaps

The following are planned or deferred items, not local-completion blockers
unless separately prioritized.

### Geography and data reconciliation

| Work | Classification | Current boundary |
| --- | --- | --- |
| Canonical PIN gaps | Data reconciliation | Resolve 40,496 villages without active matched PIN evidence. |
| Effective NWDP gaps | Data reconciliation | Resolve 112,648 canonical villages without candidate/runtime mapping. |
| Runtime expansion | Controlled promotion | Reconcile inactive and held source-feature cohorts; do not equate them directly with canonical village gaps. |
| Project-local Android villages | Deferred product authorization | Define and authorize project-scoped delivery without adding identities to global LGD APIs. |
| Village coordinate geocoding | Needs research | Select provider/source, licensing, provenance, and accuracy policy. |
| Global/non-India geography | Unimplemented architecture | Introduce country/profile/entity hierarchy while preserving stable India contracts. |

### Cloud and production operations

| Work | Classification | Current boundary |
| --- | --- | --- |
| Production Redis | Deferred to cloud | Secrets/TLS, persistence, replication/HA, backup recovery, and capacity policy. |
| Observability operations | Deferred to cloud | External log collection, metrics export, dashboards, alert routing, and incident ownership. |
| Wider lookup exposure | Separate authorization | Customer, Android, public, and production callers remain unauthorized. |
| Live provider adapters | Deferred to cloud | Weather, soil, satellite, market, sensor, and related calls need credentials, budgets, retries, rate limits, and monitoring. |
| Product-source verification | Needs research/governance | Demo/reference catalog data must not be presented as regulatory or manufacturer truth. |

### Workflow and financial product extensions

| Work | Classification | Source intent |
| --- | --- | --- |
| Formal decision nodes | Unimplemented product | Branch crop workflows using governed choices and downstream stages. |
| Perennial/orchard current-stage onboarding | Unimplemented product | Support established crops without forcing sowing/nursery flows. |
| Harvest, sale, and net realization | Unimplemented product | Extend cultivation cost through sale, receivables, post-harvest cost, and realized margin. |
| Operational-to-financial posting | Unimplemented product | Derive bounded economic records from verified operations without becoming a general ERP. |
| Recommendation-to-outcome closure | Unimplemented product | Record acceptance, execution variance, crop response, yield, quality, and economics. |
| Multi-season agricultural memory | Unimplemented product | Add comparisons, trends, benchmarking, and recurring-risk review. |
| Production and harvest pipeline | Unimplemented product | Forecast area, stages, harvest windows, output, and delays. |
| Materialized finance aggregates | Deferred product optimization | Current API summaries remain valid until scale justifies materialization. |

### Access, language, evidence, and roadmap intelligence

| Work | Classification | Current boundary |
| --- | --- | --- |
| Delegated agricultural access | Unimplemented product | Add consent, task/time scope, masking, economic visibility, revocation, and history. |
| Admin translation overrides | Unimplemented product | Add tenant/project management and reviewed native-language coverage. |
| Voice/local-language interaction | Unimplemented product | Structured voice navigation and reviewable capture, not a generic chatbot. |
| Raw-GNSS/CORS positioning evidence | Deferred research | Preserve original observations and provenance; do not infer survey precision from phone coordinates. |
| Insurance/subsidy risk review | Roadmap only | Human-review evidence bundles first; no automated fraud verdict, approval, or rejection claims. |

## Superseded-plan interpretation

Older Markdown files often describe the next step at the time they were
written. Those statements are historical when later commits, migrations, or
dated addenda implement the work. The consolidated audit therefore treats
current database state, active contracts, the latest dated readiness documents,
and committed regression evidence as authoritative. It retains only work that
still lacks implementation, operational authorization, governed data, or cloud
infrastructure.

## Recommended sequencing

1. Preserve the current local checkpoint and continue only explicitly selected
   data reconciliation.
2. At cloud/Render deployment, implement production Redis, secrets/TLS,
   persistence/HA, monitoring, alerts, and exposure authorization.
3. Decide whether project-local villages should be delivered to Android; keep
   them project-scoped and separate from canonical LGD.
4. Select one product extension rather than starting the entire roadmap. The
   strongest operational sequence is recommendation-to-outcome closure,
   followed by harvest/sale/net realization and then multi-season memory.
5. Keep live providers, global geography, GNSS processing, and insurance-risk
   intelligence in their separately researched and governed tracks.

## Reproduction

Run the read-only audit from the repository root:

    venv/bin/python backend/scripts/audit_local_geography_completion_readiness.py       --output-json /tmp/local-geography-completion-readiness.json       --output-md /tmp/local-geography-completion-readiness.md

The generated files are evidence artifacts and should not be committed. The
canonical checkpoint is this reviewed document plus the audit script and static
contract.
