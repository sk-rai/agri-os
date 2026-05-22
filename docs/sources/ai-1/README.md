# AI-1 Source Documents

Original documents shared by AI-1 (another AI review agent).
These are the RAW source material from which governance insights were extracted
into `docs/reconciliation/`.

## Document Index

Place the original AI-1 files here. Expected files:

| # | Filename | Content | Status |
|---|----------|---------|--------|
| 1 | `comprehensive-platform-analysis.txt` | 4-pass review (architecture, semantics, workflow, UX) | Pending |
| 2 | `feedback-week1-4.txt` | Week 1-4 deliverables feedback | Pending |
| 3 | `sprint1-day2-3-deliverables.txt` | OpenAPI spec, Drift schema, integration checklist | Pending |
| 4 | `syncmanager-conflict-resolver.txt` | Dart SyncManager + ConflictResolver code | Pending |
| 5 | `ui-sync-status-widget.txt` | Flutter sync status widget + manual review screen | Pending |
| 6 | `farmer-parcel-list-tile-validation.txt` | List tiles + offline form validation rules | Pending |
| 7 | `farmer-parcel-detail-screens.txt` | Detail screen rules + image pipeline | Pending |
| 8 | `testing-strategy-rural-ux.txt` | Testing strategy + rural UX protocol | Pending |
| 9 | `deployment-infrastructure-runbook.txt` | Deployment, DR, monitoring, canary | Pending |
| 10 | `enterprise-dashboard-spec.txt` | Dashboard widgets, KPI cards, exports | Pending |
| 11 | `api-capability-versioning.txt` | API tree, versioning, webhooks | Pending |
| 12 | `go-live-operational-playbook.txt` | Tenant provisioning, SLAs, incident response | Pending |
| 13 | `master-data-caching-strategy.txt` | Master data categories, delta sync, fallback | Pending |
| 14 | `security-audit-framework.txt` | JWT, PII, audit log, pen-test checklist | Pending |
| 15 | `master-data-foundation-guide.txt` | Step-by-step implementation guide for master data | Pending |

## How Insights Were Extracted

For each AI-1 document:
1. Technology-specific code (Dart, Flutter, YAML) was DISCARDED
2. Behavioral contracts and governance rules were EXTRACTED
3. Extracted content was placed in `docs/reconciliation/contracts/` or `operations/`
4. The extraction analysis is in `ai1-additional-insights.md` (this folder)

## Why Keep These?

- **Provenance**: Know where each governance rule came from
- **Re-extraction**: If governance docs need updating, re-read source
- **Completeness check**: Verify nothing was missed
- **Onboarding**: New team members can see the full analysis history
