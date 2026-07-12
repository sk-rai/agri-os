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
