# Workflow CSV lifecycle

Workflow CSV is the bulk-edit path for crop stages and recommendations. It is intentionally draft-first: Android only sees published workflow versions, while admins can safely export, edit, validate, apply, validate again, and publish.

## Golden path

1. Export a workflow CSV
   - Admin opens `/workflows` or a workflow draft preview.
   - Download a template or export an existing workflow version.
   - Prefer exporting the current published version when creating a new draft from a known-good baseline.

2. Create or open a DRAFT workflow version
   - Published workflow versions are immutable for runtime safety.
   - Use `Clone draft` from a published version or restore an archived version to draft.
   - Existing crop cycles remain pinned to the version used at cycle creation.

3. Edit the CSV offline
   - Keep one row per recommendation.
   - Repeat identical stage fields for all rows belonging to the same `stage_code`.
   - Leave recommendation fields blank only when a stage has no recommendations.
   - Use catalog `input_code` when known; blank input codes are treated as custom/unmapped and show warnings.

4. Validate CSV against the draft
   - Endpoint: `POST /api/v1/workflow-catalog/csv/workflows/drafts/{version_id}/validate`
   - Admin UI: draft preview ? Workflow CSV Validation panel.
   - Validation is non-mutating.
   - Errors block apply. Warnings are visible but do not block apply.

5. Apply CSV to draft
   - Endpoint: `POST /api/v1/workflow-catalog/csv/workflows/drafts/{version_id}/apply`
   - Requires admin `EDIT` and an audit `reason`.
   - Apply validates again server-side before mutating.
   - If clean, the uploaded CSV replaces the draft stages and recommendations.
   - Apply records `APPLY_WORKFLOW_CSV` audit with file name, row counts, before/after stage counts, before/after recommendation counts, actor, reason, and timestamp.

6. Review draft preview
   - Confirm rendered stages, durations, recommendations, critical flags, quantities, and input links.
   - Use the visual builder for small fixes if needed.
   - Check the Workflow Audit Trail panel and filter by `APPLY_WORKFLOW_CSV` for traceability.

7. Run draft validation
   - Endpoint: `GET /api/v1/workflow-catalog/drafts/{version_id}/validation`
   - Admin UI: draft preview ? Draft Validation / Publish Readiness.
   - This is separate from CSV validation and is the publish gate.
   - Any draft edit or CSV apply makes prior publish validation stale.

8. Publish draft
   - Publish only when draft validation passes and publish impact is acceptable.
   - Publishing makes this version eligible for new Android crop-cycle creation.
   - Existing crop cycles remain pinned/read-only to their original workflow version.

## Safety rules

- CSV apply never writes directly to a published workflow.
- CSV apply replaces the DRAFT version contents, not project overrides.
- Invalid CSV apply returns a validation report and does not mutate the draft.
- Admin must supply a reason before apply.
- Audit JSON remains available, but admin screens should show readable summaries first.
- After apply, run draft validation before publishing.

## Common validation failures

| Code | Meaning | Fix |
| --- | --- | --- |
| `MISSING_COLUMNS` | Required CSV headers are absent | Start from backend template/export |
| `TEMPLATE_MISMATCH` | CSV template code does not match the draft | Use the matching export/draft |
| `CROP_MISMATCH` / `SEASON_MISMATCH` | CSV targets a different crop/season | Apply to the correct draft or fix CSV metadata |
| `INVALID_STAGE_CODE` | Stage code has invalid characters/length | Use uppercase letters, numbers, and underscores |
| `CONFLICTING_STAGE_DEFINITION` | Same stage code has different repeated stage fields | Make repeated stage fields identical |
| `DUPLICATE_STAGE_ORDER` | Two stage codes use the same stage order | Assign unique stage order values |
| `DUPLICATE_RECOMMENDATION_ORDER` | Two recommendations in a stage use same sort order | Assign unique recommendation sort order within each stage |
| `UNKNOWN_INPUT_CODE` | Input code is not a published catalog input | Correct code, publish input, or leave blank for custom/unmapped |
| `INPUT_NOT_APPLICABLE_TO_CROP` | Input exists but is not scoped to the workflow crop | Fix input crop scope or choose another input |
| `INVALID_JSON` / `INVALID_JSON_TYPE` | JSON columns are malformed or wrong type | Use valid JSON arrays/objects as required |

## Regression commands

Run before committing workflow CSV changes:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/test_workflow_csv_validation.py
../venv/bin/python scripts/run_workflow_admin_regressions.py
```

For admin UI changes:

```bash
cd ~/projects/farmint/web
npm run build
```

## Android expectation

Android does not consume DRAFT workflow versions or CSV imports. Android should keep consuming published workflow/catalog endpoints and pinned cycle responses. Once a draft is published, new crop cycles receive the published version selected by backend catalog/project assignment rules.
