# Web UI Exploratory Test Plan

## Goal

Build a layered browser-driven test suite for the web/admin UI that starts read-only, captures screenshots, logs browser/runtime issues, and later adds positive/negative create/edit workflows page by page.

## Iteration 1: read-only smoke screenshot sweep

Script: `web/scripts/admin_smoke_screenshot_sweep.mjs`

Behavior:

- Visits every known admin/static route.
- Captures full-page screenshots.
- Logs console errors, page errors, failed network requests, and HTTP error responses.
- Continues after route failures.
- Exits 0 by default so exploratory trial runs do not fail the whole suite.
- Supports `--fail-on-error` for stricter later CI usage.

## Later iterations

1. Add route-specific assertions for expected headings/tables/cards.
2. Add safe negative tests for validation errors and unauthorized/admin-only mutations.
3. Add positive create/edit tests only for disposable regression tenants/projects/data.
4. Add screenshot comparisons or reviewer summaries once layouts stabilize.
5. Add full end-to-end suite after piecemeal scripts are stable.

## Commands

Install browser automation dependencies once:

```bash
cd ~/projects/farmint/web
npm install -D playwright
npx playwright install chromium
```

Run backend and web in separate terminals, then run:

```bash
cd ~/projects/farmint/web
node scripts/admin_smoke_screenshot_sweep.mjs --base-url=http://127.0.0.1:3000
```

