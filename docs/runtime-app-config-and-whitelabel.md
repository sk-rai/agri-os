# Runtime app configuration and white-labelling contract

Status: implemented as read-only bootstrap/effective config plus limited project flag editing  
Primary consumers: Android, admin web, future white-labelled tenants/projects

## Purpose

Agri-OS should not require a separate Android APK for every client. Tenant/project branding, language, units, module visibility, and feature rollout should be controlled by backend runtime configuration. Android and web should fetch the effective configuration and render the appropriate experience.

This is also the foundation for India-first but global-ready deployments: India-specific defaults are allowed, but they must be configuration values rather than permanent app assumptions.

## Current endpoints

| Endpoint | Consumer | Purpose |
| --- | --- | --- |
| `GET /api/v1/app-config/bootstrap` | Android/web | Tenant/default runtime config, safe without project context |
| `GET /api/v1/app-config/bootstrap?project_id={project_id}` | Android/web | Project-effective runtime config for one selected project |
| `GET /api/v1/app-config/projects/{project_id}/effective-app-config` | Admin web | Inspect default + tenant + project merged config with section sources |
| `PATCH /api/v1/projects/{project_id}/app-config` | Admin/API | Existing operations endpoint for project config patching with safe-edit checks |
| `PATCH /api/v1/app-config/projects/{project_id}/config` | Admin web | Project config patching with audit events |
| `PATCH /api/v1/tenants/{tenant_id}/app-config` | Enterprise admin/API | Tenant default app config patching |

## Merge order

Effective runtime config is resolved in this order:

1. Platform default config
2. Tenant config
3. Project config

Project values override tenant values, tenant values override platform defaults. Admin inspection includes `section_sources` so operators can see whether a section came from `default`, `tenant`, or `project`.

## Current config sections

### `branding`

Current fields include:

- `app_name`
- `logo_url`
- `primary_color`
- `secondary_color`
- `accent_color`
- `support_email`
- `support_phone`

Android should treat these as runtime display hints. Missing logo/color fields should fall back to bundled Agri-OS defaults.

### `localization`

Current fields include:

- `default_language`
- `supported_languages`
- `country_code`
- `timezone`

Future work should expand this into full server-managed translations and regional field visibility. For now, Android can use it to select default language/locale behavior where supported.

### `units`

Current fields include:

- `area_units`
- `default_area_unit`
- `currency`
- `measurement_system`

Future international deployments should make this country/project configurable rather than hardcoding India-specific land units or INR.

### `enabled_modules`

Current examples include:

- `FARMER_PROFILE`
- `LAND_PARCELS`
- `SOIL_PROFILE`
- `CROP_CYCLES`
- `ACTIVITY_LOGGING`
- `GPS_GEOMETRY`

Android/web should hide or de-emphasize unavailable modules instead of assuming every deployment has every feature enabled.

### `feature_flags`

Current examples include:

- `backend_driven_farmer_forms`
- `backend_driven_parcel_forms`
- `backend_driven_soil_forms`
- `white_label_runtime_branding`
- `project_memberships`
- `media_attachments`
- `broadcast_advisories`
- `farmer_queries`
- `field_event_reporting`
- `economics_summary`

Feature flags allow backend contracts to be shipped safely before Android switches from native screens to backend-rendered flows.

### `self_service`

Current fields include:

- `allow_direct_farmer_registration`
- `default_tenant_id`
- `requires_project_invite`

This supports both modes:

- farmer independently downloads the app and self-registers;
- company/FPO/project enrolls a farmer and Android hydrates the project context.

## Admin visibility

The `/profile-forms` admin page currently shows:

- effective render context
- runtime app configuration
- branding/localization/unit/module/feature flag values
- section source provenance for project-effective config
- profile form feature flag controls for project-scoped rollout
- project app-config audit events
- profile form validation report

This is intentionally read-only for most runtime config sections today, except profile form feature flags already exposed through safe project updates.

## Android expectations

Android should eventually follow this pattern:

1. After login, call profile hydration / launch-context.
2. If project context is selected, call bootstrap with `project_id`.
3. Apply branding and locale/unit defaults from bootstrap.
4. Use `enabled_modules` and `feature_flags` to decide whether to show native screens or backend-rendered flows.
5. Treat unknown config keys as forward-compatible optional metadata.
6. Cache config for offline startup, but refresh when online because admin may change project configuration.

## What is not done yet

- Full admin editor for branding/localization/units/modules.
- Logo/media upload and CDN/storage integration.
- Server-managed translation catalog.
- Per-country legal/identity field packs.
- Android dynamic theming implementation.
- Role-scoped controls around who may edit tenant branding vs project feature flags.

## Regression commands

After backend app-config contract changes:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/run_platform_config_regressions.py
```

After admin app-config UI changes:

```bash
cd ~/projects/farmint/web
npm run build
```
