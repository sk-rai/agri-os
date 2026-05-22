# Architecture Review Reports

Multi-pass quality review reports produced during the architecture analysis phase.
These are the RAW review outputs — findings were resolved into ADRs and governance docs.

## Reports (from Kiro Windows session)

Place the review markdown files here:

| # | Filename | Focus | Findings |
|---|----------|-------|----------|
| 1 | `pass1-architecture-integrity.md` | Modularity, coupling, event-driven, offline-first | 7C, 9H, 12M, 6L |
| 2 | `pass2-domain-semantics.md` | Terminology, entity naming, taxonomy, KPIs | 5C, 8H, 13M, 8L |
| 3 | `pass3-workflow-integrity.md` | State machines, transitions, race conditions | 6C, 9H, 12M, 7L |
| 4 | `pass4-product-ux.md` | Farmer usability, dealer workflows, low-literacy | 5C, 8H, 11M, 7L |
| 5 | `holistic-review-report.md` | Consolidated strengths/weaknesses, roadmap | — |
| 6 | `correlated-dual-ai-review.md` | Kiro vs AI-1 correlation analysis | — |

## Resolution Status

All 133 findings have been addressed through:
- 9 Architecture Decision Records (ADRs) in `docs/reconciliation/adrs/`
- Behavioral contracts in `docs/reconciliation/contracts/`
- Operational governance in `docs/reconciliation/operations/`
