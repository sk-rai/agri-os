# Android Profile Migration Sample Bundle

Status date: 2026-07-27

This folder contains exact current sample JSON for backend-driven Android profile migration.

## Endpoint samples

1. `01-auth-mode-bootstrap.json` — `GET /api/v1/auth/mode-bootstrap`
2. `02-app-config-bootstrap.json` — current route `GET /api/v1/app-config/bootstrap`
3. `03-forms-profile-contract.json` — `GET /api/v1/forms/profile-contract`
4. `04-form-farmer-registration.json` — `GET /api/v1/forms/farmer_registration`
5. `05-form-parcel-registration.json` — `GET /api/v1/forms/parcel_registration`
6. `06-form-soil-profile.json` — `GET /api/v1/forms/soil_profile`
7. `07-form-options.json` — `GET /api/v1/forms/options`
8. `08-season-land-units.json` — `GET /api/v1/forms/metadata/season-land-units`
9. `09-geography-hierarchy-profile.json` — `GET /api/v1/master-data/geography/hierarchy-profile`
10. `10-geography-pin-code-560001.json` — `GET /api/v1/master-data/geography/villages/by-pin-code?pin_code=560001`

## Submit contracts

See `11-submit-payload-contract.json`.

## Route note

Android requested `GET /api/v1/config/app-bootstrap`; current backend route is `GET /api/v1/app-config/bootstrap`. Use the current backend route unless we add a compatibility alias.

## Feature flags

Use backend-driven profile screens when these effective app-config flags are true:

- `backend_driven_farmer_forms`
- `backend_driven_parcel_forms`
- `backend_driven_soil_forms`
