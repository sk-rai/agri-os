# Admin UX checklist

This checklist captures the current Agri-OS admin UI conventions. Use it when adding or changing admin screens so the experience stays consistent as the backend-driven configuration system grows.

## Page structure

- Start each page with a clear title, one-sentence purpose, and the main action or related navigation on the right.
- Keep reporting and traceability screens readable for `VIEW` users.
- Show mutation controls only when useful, and disable or hide them based on permissions and lifecycle locks.
- Prefer small, explicit status panels over hidden magic. Admin users should know why a row appears in a queue.

## Permissions and read-only states

- Backend authorization is the source of truth; UI guards are convenience only.
- Load admin access with `useAdminProfile()` and check permissions via `hasAdminPermission(...)`.
- For read-only users, show a short banner explaining what they can still inspect.
- For failed mutations, render `PermissionErrorCard` when the API returns permission denial details.
- Pair permission checks with domain locks such as safe-edit lifecycle. Permission does not override locked projects or published workflow immutability.

## Shared admin components

Prefer the shared admin UI components before creating one-off markup:

- `PermissionErrorCard` for backend `ADMIN_PERMISSION_DENIED` responses.
- `DrilldownBanner` for dashboard-filtered pages with a clear reset link.
- `CopyLinkButton` for shareable dashboard, lookup, trace, and filtered report URLs.

When adding new shared components:

- Keep them small and behavior-focused.
- Put them under `web/src/components/`.
- Use page-specific labels through props rather than duplicating the component.
- Update this checklist when the component becomes part of the admin convention.

## Dashboard conventions

- The dashboard is the admin command center, not a dense analytics page.
- Command Center cards should have:
  - a concise domain name,
  - one operational description,
  - one metric badge,
  - a friendly destination hint such as `Open Workflow catalog ->`.
- Attention Queue cards should show:
  - the queue count,
  - why the queue matters,
  - the exact drill-down target, for example `Opens /inputs?filter=review`.
- Dashboard drill-down links should land on a filtered page whenever possible.

## Drill-down screens

- Filtered pages opened from the dashboard should show a blue drill-down banner.
- Use `DrilldownBanner` for the shared banner pattern.
- Every drill-down banner should include:
  - the active context,
  - what is currently filtered,
  - a `Clear drill-down` link back to the unfiltered page.
- Query parameters should be readable and stable enough for sharing during testing.

## Tables and detail panels

- Prefer links from list rows into trace/detail pages instead of duplicating all detail inline.
- Show IDs when they help traceability, but pair them with farmer/parcel/project/crop labels when available.
- For audit views, prefer before/after summaries over raw JSON first; keep payload JSON available for deep debugging.
- For queue lists, show the action needed next, not only the raw status.

## Forms and mutation flows

- Avoid surprise writes. Mutations should have a visible button, reason field where governance matters, and clear success/failure feedback.
- Draft/edit/publish flows should show validation or publish impact before irreversible activation.
- CSV imports should distinguish upload, validation, pending apply, applied, and rejected states.
- Project-scoped assignments should expose lifecycle lock reasons before the admin tries to save.

## Empty, loading, and error states

- Loading text should name the thing being loaded.
- Empty states should explain whether there is no data or the current filter is too narrow.
- Error states should preserve the page context and avoid blank screens.
- Permission errors should tell the user which role/permission is missing when the backend provides it.

## Regression expectation

- Run the Next.js production build after admin UI changes:

```bash
cd web
npm run build
```

- Run backend permission regressions when changing admin roles, guarded endpoints, or permission error contracts:

```bash
cd backend
../venv/bin/python scripts/run_admin_permission_regressions.py
```

## Manual admin testing checklist

Use this quick pass after admin UI changes, especially when a screen participates in dashboard drill-downs or permission-gated mutations.

1. Dashboard entry
   - Open `/dashboard`.
   - Confirm the Command Center cards render and link to the expected admin areas.
   - Confirm Attention Queue cards show count, reason, and the exact target route.

2. Filtered drill-down
   - Open at least one dashboard queue link, such as `/inputs?filter=review` or `/sync-health?status=FAILED`.
   - Confirm the destination page shows the blue drill-down banner.
   - Click `Clear drill-down` and confirm the unfiltered page loads.

3. Read-only role behavior
   - Test with a `VIEW`-only admin when possible.
   - Confirm browse, search, trace, preview, and export actions still work.
   - Confirm mutation controls are hidden or disabled with helpful read-only messaging.

4. Permission denial behavior
   - Attempt one protected mutation with insufficient permissions when practical.
   - Confirm the page stays usable and renders `PermissionErrorCard` if the backend returns permission details.

5. Mutation happy path
   - For the changed screen, complete one valid mutation using an admin role with the required permission.
   - Confirm success feedback, list refresh, audit/trace visibility, and no stale UI state.

6. Empty and error states
   - Test one narrow filter that returns zero rows.
   - Confirm the empty state explains the filter/no-data situation.
   - If an API call fails during development, confirm the page shows a recoverable error instead of going blank.

7. Regression command
   - Run `npm run build` from `web/` before committing UI changes.
   - If permissions or guarded endpoints changed, also run the backend admin permission regression suite.

