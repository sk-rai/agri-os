# Admin import and configuration roadmap

This roadmap defines how Agri-OS should move from seeded backend data to admin-configurable crop, workflow, recommendation, and input catalogs without turning Android into a rule engine.

The principle: backend owns configuration, validation, versioning, and client/project-specific enablement. Android renders the active published contract for the farmer/project/crop cycle.

## Goals

- Let tenant/project admins configure crops, stages, recommendations, inputs, products, and rules safely.
- Support both CSV import and visual admin editing.
- Keep Android stable as a renderer of backend contracts.
- Preserve auditability: validate before apply, record who changed what, and keep published versions immutable for existing crop cycles.
- Allow project/client-specific visibility, overrides, and custom additions without forking the mobile app.

## Configuration domains

| Domain | Examples | Admin operation | Runtime consumer |
| --- | --- | --- | --- |
| Crop taxonomy | crop type, group, family, economic class, propagation type | import/edit/publish taxonomy | crop-cycle creation, workflow catalog |
| Workflow template | stages, durations, stage order, stage descriptions | draft/edit/validate/publish | Android crop timeline |
| Recommendations | activity type, input, offset, quantity, cost, criticality | draft/edit/import/override | Android stage activities |
| Input catalog | seeds, fertilizer, pesticides, herbicides, labor, machinery | CSV validate/apply/review/publish | activity logging, recommendations |
| Product catalog | manufacturers, brands, packages, approvals | import/edit/approve | product/package traceability |
| Input rules | crop-stage-product dosage rules | import/edit/project assign | variance and compliance reports |
| Project assignments | enabled workflows, visible inputs/products, overrides | project-scoped edit with safe lifecycle | project-specific Android rendering |

## Import lifecycle

Every bulk import should follow the same state machine:

1. `UPLOAD`
   - Admin uploads CSV/XLSX or uses a template.
   - Backend stores batch metadata and raw file reference if supported.

2. `VALIDATE`
   - Backend parses rows.
   - No operational data is changed.
   - Response includes row-level errors, warnings, duplicate detection, and planned changes.

3. `PENDING_APPLY`
   - Validated batch is reviewable in admin.
   - Admin can download validation report.
   - Admin must provide reason/change note before applying.

4. `APPLY`
   - Backend applies changes transactionally where possible.
   - Creates audit events.
   - For workflow changes, creates or modifies DRAFT versions, not published versions directly.

5. `PUBLISHED` or `APPLIED`
   - Master/reference data may become active after apply.
   - Workflow data must still pass validation and publish separately.

6. `REJECTED` or `ARCHIVED`
   - Admin can reject stale/failed imports.
   - Rejected imports remain auditable.

## CSV/import targets by priority

### Phase 1: Low-risk reference data

Start here because these mostly feed dropdowns and filters.

- Crop taxonomy
- Propagation types
- Crop groups/classes
- Seasons
- Activity/input categories

Expected validation:

- required code/name fields;
- duplicate code detection;
- parent/reference existence;
- active/inactive state;
- no breaking deletes while referenced.

### Phase 2: Input and product catalog

This is already partially implemented for input CSV import. Extend the pattern.

- Canonical inputs
- Manufacturers
- Products/brands
- Packages/SKUs
- Project product approvals

Expected validation:

- input category exists;
- compatible crop codes exist;
- manufacturer/product uniqueness;
- package unit normalization;
- product approval project exists;
- custom Android-submitted inputs can be reviewed/deduped.

### Phase 3: Workflow templates and recommendations

This is more sensitive because it affects Android crop-cycle UX.

- Workflow metadata
- Stage list
- Stage duration/order
- Recommendation rows
- Stage/recommendation descriptions/actions/observations
- Recommendation input links and typical quantities

Expected behavior:

- imports create or update DRAFT workflow versions only;
- publish remains explicit;
- existing crop cycles stay pinned to original version;
- validation blocks publish on broken stage order, missing recommendations, invalid offsets, duplicate codes, or incompatible inputs;
- project overrides remain separate from source template changes.

### Phase 4: Input dosage/rule mapping

This powers compliance and variance analytics.

- Crop-stage input rules
- Product/package allowed lists
- Dosage and area units
- Project-specific rule activation

Expected validation:

- workflow stage exists for crop/season;
- input exists and is compatible;
- product is approved or explicitly allowed;
- dosage units are normalized;
- conflicting active rules are flagged.

## Visual builder relationship to CSV

CSV and visual builder should use the same backend validation/apply services.

- CSV is efficient for bulk setup and client onboarding.
- Visual builder is better for reviewing, small edits, and non-technical admins.
- Both should produce drafts, validation reports, audit events, and publish impact summaries.

The visual builder should not bypass versioning or safe-edit lifecycle.

## Android contract expectation

Android should continue to consume published backend contracts:

- profile hydration;
- crop-cycle templates/catalog;
- project-enabled workflows;
- recommended activities;
- dynamic forms;
- input/product dropdowns where applicable;
- trace IDs for synced activities.

Android should not hardcode crop stage names, recommendation dates, input catalogs, or project-specific visibility rules.

## Admin UI surfaces

Near-term screens:

- Taxonomy catalog: read-only first, then import.
- Workflow import: upload -> validate -> preview draft -> publish.
- Recommendation import: tied to a workflow draft.
- Input/product import: extend existing input CSV queue.
- Rule import: validate against workflow stage and input/product catalogs.
- Import history/audit: active, applied, rejected, failed batches.

## Safety rules

- Published workflow versions are immutable for existing crop cycles.
- Existing crop cycles remain pinned to the version used at creation time.
- Project assignment changes are blocked or constrained by safe-edit lifecycle when farmers/cycles exist.
- Bulk import must never silently delete referenced data.
- Deletes should be soft-delete/archive unless a row is unreferenced and explicitly purged.
- Every apply/publish action should capture actor, reason, before/after, and timestamp.

## Regression expectation

Before adding or changing import/configuration flows:

```bash
cd backend
../venv/bin/python scripts/run_workflow_admin_regressions.py
../venv/bin/python scripts/run_admin_report_regressions.py
```

For permission changes:

```bash
cd backend
../venv/bin/python scripts/run_admin_permission_regressions.py
```

For admin UI changes:

```bash
cd web
npm run build
```

## Recommended next implementation order

1. Add read-only crop taxonomy admin screen.
2. Add taxonomy import validation endpoint.
3. Add taxonomy import apply endpoint with audit.
4. Add workflow CSV template/export endpoint.
5. Add workflow import validation into DRAFT version.
6. Add admin preview of workflow import validation errors.
7. Extend product/package CSV import.
8. Add rule import validation and apply.
