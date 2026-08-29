# Agri-OS Web

This is the Next.js web app for Agri-OS.

It includes:

- the admin web application;
- the public AgriFabric landing-page draft at `/agrifabric`;
- Playwright smoke scripts under `web/smoke`;
- landing-page SVG assets under `web/public/landing-assets`.

## Run locally

From repo root:

- `cd web`
- `NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev -- --port 3000`

Open:

- Admin login: `http://localhost:3000/login`
- AgriFabric landing page: `http://localhost:3000/agrifabric`

Important behavior:

- `/` still redirects to `/login`.
- `/agrifabric` is public and does not require admin authentication.

## Build

From `web/`:

- `npm run build`

A warning about `<img>` usage on the AgriFabric landing page is currently acceptable because the page uses committed static SVG assets. It can be revisited later if we decide to move those assets to `next/image`.

## Landing smoke

From repo root while the web server is running:

- `WEB_BASE_URL=http://localhost:3000 node web/smoke/agrifabric_landing_smoke.mjs`
- `node web/smoke/agrifabric_static_demo_readiness_check.mjs`
- `node web/smoke/agrifabric_static_demo_clip_manifest_check.mjs`

The smoke verifies:

- `/agrifabric` loads;
- all six tabs render;
- static landing assets are present;
- roadmap claim boundary text is visible;
- mobile viewport rendering works.

## Landing capture helper

From repo root:

- `WEB_BASE_URL=http://localhost:3000 AGRIFABRIC_TAB=product AGRIFABRIC_VIEWPORT=thumbnail node web/smoke/agrifabric_landing_capture_helper.mjs`

Useful environment variables:

- `AGRIFABRIC_TAB=overview|product|graph|operations|geography|roadmap`
- `AGRIFABRIC_VIEWPORT=desktop|thumbnail|mobile`
- `AGRIFABRIC_OUTPUT=custom-name.png`
- `AGRIFABRIC_FULL_PAGE=true`

Generated captures go under `web/smoke/screenshots/agrifabric/` and should remain untracked unless a final selected asset is intentionally versioned.
