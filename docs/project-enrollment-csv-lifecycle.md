# Project enrollment CSV lifecycle

Project enrollment CSV is the bulk path for assigning farmers to projects. It supports company-led enrollment where an FPO, input company, insurer, dealer network, or agronomy team needs to load farmer memberships before Android users hydrate or sync their local profile.

The principle is the same as other Agri-OS imports: validate first, persist the reviewable batch, apply only explicit validated changes, and surface unresolved batches in admin readiness.

## Golden path

1. Filter to one project
   - Admin opens `/project-enrollments`.
   - Set the `Project ID` filter and apply filters.
   - CSV imports are intentionally project-scoped so a file cannot accidentally enroll farmers into the wrong project.

2. Download template
   - Use `Download template` from the Bulk enrollment CSV panel.
   - Keep backend IDs where known.
   - Use mobile number and farmer details for matching or creating farmers.
   - Include parcel linkage columns when the project enrollment should be tied to specific parcels.

3. Validate CSV
   - Validation is non-mutating.
   - Backend stores an import batch with status `VALIDATED` or `INVALID`.
   - The report shows planned create/update actions, row warnings, and row errors.
   - Invalid batches stay visible for operator follow-up.

4. Review validation output
   - Fix any row errors before applying.
   - Warnings should be reviewed because they often indicate duplicate farmer matching, missing optional references, or incomplete linkage.
   - Download a fresh template if the file shape is stale.

5. Apply validated batch
   - Only `VALIDATED` batches can be applied.
   - Admin must provide an apply reason.
   - Apply creates or updates project memberships and preserves backend identifiers for hydration, sync, and traceability.
   - The same batch cannot be applied twice.

6. Confirm visibility
   - The Project Enrollments report should show new or updated memberships.
   - Farmer launch context should route enrolled farmers to the correct project experience.
   - Dashboard attention queues and System Readiness surface pending/invalid enrollment import batches.

## Batch status contract

| Status | Meaning | Operator action |
| --- | --- | --- |
| `VALIDATED` | CSV passed validation and can be applied | Review summary, enter reason, apply |
| `INVALID` | CSV has blocking row or file errors | Fix CSV and validate again |
| `APPLIED` | Batch was applied successfully | No further action |
| `EXPIRED` | Batch is too old to trust | Revalidate current CSV |
| `STALE` | Referenced project/farmer/parcel state changed after validation | Revalidate before applying |

## Safety rules

- Project enrollment CSV apply is project-scoped.
- Validation never mutates farmer, parcel, or membership records.
- Apply must be explicit and reasoned.
- Applied batches remain auditable.
- Dashboard readiness reports invalid and pending enrollment imports so onboarding cannot quietly stall.
- Android should not parse enrollment CSV. Android consumes hydrated farmer/project membership contracts after login/sync.

## Regression commands

Run the focused project-enrollment suite before committing enrollment CSV, membership sync, launch context, or enrollment report changes:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/run_project_enrollment_regressions.py
```

For deeper dashboard/readiness coverage after changing admin reports:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/run_admin_report_regressions.py
```

For admin UI changes:

```bash
cd ~/projects/farmint/web
npm run build
```
