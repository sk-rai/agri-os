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

## Current implemented import foundation

The master-data import foundation now includes these safe CSV lifecycles:

| Area | Backend lifecycle | Admin UI | Apply behavior |
| --- | --- | --- | --- |
| Crop taxonomy | template/export/validate/history/apply | available on Crop Taxonomy screen | creates/updates taxonomy nodes and parent edges |
| Crop propagation types | template/export/validate/history/apply | available on Crop Taxonomy screen | creates/updates propagation establishment types |
| Crop catalog | template/export/validate/history/apply | available on Crop Taxonomy screen | creates/updates crops, taxonomy assignments, and propagation options |
| Input catalog | template/export/validate/history/apply plus review/publish lifecycle | available on Inputs screen | creates/updates canonical inputs and keeps lifecycle states auditable |

Recommended order for crop onboarding:

See also:

- [Workflow CSV lifecycle](workflow-csv-lifecycle.md) for the current export/edit/validate/apply/publish operator flow.
- [Project enrollment CSV lifecycle](project-enrollment-csv-lifecycle.md) for company/FPO/insurer/dealer-led farmer onboarding into projects.

1. Import/apply taxonomy nodes first.
2. Import/apply propagation types next.
3. Import/apply crop catalog rows after their reference codes exist.
4. Create or import workflow templates as drafts.
5. Validate and publish workflow versions.
6. Assign published workflows and input/product visibility to projects.

Crop catalog CSV rows deliberately fail validation when referenced category, taxonomy, or propagation codes are missing. That keeps admin uploads explicit and prevents Android from receiving partially linked crop metadata.

The admin dashboard now includes `CROP_SETUP` in System Readiness. It links to `/crop-taxonomy` and reports taxonomy nodes, propagation types, crop rows, and invalid crop import batches so tenant setup gaps are visible before workflow publishing.

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

Current product catalog CSV lifecycle:

- export/template download is available from Products admin;
- validation persists an import batch with `VALIDATED` or `INVALID` status;
- only `VALIDATED` batches can be applied before expiry;
- apply creates/updates manufacturers, branded products, and package SKUs;
- repeat apply is blocked after the batch becomes `APPLIED`;
- apply result summary records manufacturer/product/package created, updated, and unchanged counts;
- product CSV apply writes audit events for manufacturer, product, and package changes.

Batch status contract:

- `VALIDATED`: ready to apply before expiry;
- `INVALID`: fix CSV and upload again;
- `APPLIED`: already imported and cannot be applied again;
- `EXPIRED`: validate again before applying;
- `STALE`: referenced catalog data changed after validation, so revalidate.

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

- Taxonomy catalog: read-only plus CSV template/export/validate/history/apply.
- Crop catalog: CSV template/export/validate/history/apply for crops linked to taxonomy and propagation.
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

1. Add workflow CSV template/export endpoint.
2. Add workflow import validation into DRAFT versions.
3. Add admin preview of workflow import validation errors.
4. Add workflow import apply/publish handoff.
5. Extend product/package CSV import.
6. Add crop-stage input rule CSV validation and apply.
7. Add import audit/search screen across all batch types.
8. Add downloadable validation reports for failed imports.
