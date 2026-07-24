# Android Sample Payloads

Generated from temporary tenant/project rows by `backend/scripts/capture_android_sample_payloads.py`.

These payloads are representative and redacted. They are Android integration examples, not production seed data.

Regenerate with:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/capture_android_sample_payloads.py
```

## Payload index

1. `01-mode-bootstrap.json` - post-login farmer/agent mode routing.
2. `02-app-config-bootstrap.json` - project-effective app config, feature flags, branding, and form hints.
3. `03-pin-code-villages.json` - PIN-code village lookup example.
4. `04-form-farmer-registration.json` - backend-driven farmer form schema.
5. `05-form-parcel-registration.json` - backend-driven parcel form schema.
6. `06-form-soil-profile.json` - backend-driven soil profile form schema.
7. `07-form-options.json` - backend-owned option sets.
8. `08-profile-contract.json` - Android profile contract summary.
9. `09-farmer-create-response.json` - farmer create response.
10. `10-parcel-create-response.json` - parcel create response.
11. `11-soil-profile-create-response.json` - soil profile create response.
12. `12-profile-readiness.json` - profile readiness response.
13. `13-soil-enrichment-summary.json` - soil enrichment summary.
14. `14-soil-enrichment-latest-or-error.json` - latest soil enrichment empty/error example.
15. `15-weather-latest-snapshot.json` - latest backend weather snapshot.
16. `16-broadcast-feed.json` - farmer broadcast feed.
17. `17-broadcast-detail.json` - broadcast detail.
18. `18-broadcast-read-response.json` - broadcast delivery read action.
19. `19-broadcast-ack-response.json` - broadcast delivery acknowledgement action.
20. `20-crop-template-rice.json` - rice crop-cycle template.
21. `21-enabled-crop-workflows.json` - enabled workflow catalog for project context.
22. `22-sync-dependency-error.json` - offline sync dependency failure example.
