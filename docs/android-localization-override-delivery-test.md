# Android Localization Override Delivery Smoke

This smoke proves Android consumes backend-published admin localization overrides from runtime form/bootstrap payloads, instead of hardcoding labels or performing local translation.

## Backend prepare

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/seed_admin_localization_content_keys.py --apply \
  > /tmp/localization-content-key-seed.json \
  2>&1

../venv/bin/python scripts/prepare_android_localization_override_delivery.py --reset --apply \
  > /tmp/android-localization-override-prepare.raw \
  2>&1

echo "localization_override_prepare_exit=$?"
tail -180 /tmp/android-localization-override-prepare.raw
```

## Canonical contract

- `schema_version=android_localization_override_delivery.v1`
- `tenant_id=android-fpo-multi-village-test`
- `project_id=0f7e0a6b-8472-5d6d-8a14-a9d000002001`
- `language_code=kn`
- form content key: `profile_form.activity_log.title`
- option content key: `profile_option_set.languages.option.kn.label`

Expected override values:

- activity-log title: `ಚಟುವಟಿಕೆ ದಾಖಲಿಸಿ - Android override smoke`
- Kannada language option label: `ಕನ್ನಡ - Android override smoke`

## Android pass criteria

Android should verify:

- `localization_override_contract=android_localization_override_delivery.v1`
- `localization_override_language=kn`
- `localization_override_form_key=profile_form.activity_log.title`
- `localization_override_form_title=ಚಟುವಟಿಕೆ ದಾಖಲಿಸಿ - Android override smoke`
- `localization_override_option_key=profile_option_set.languages.option.kn.label`
- `localization_override_option_label=ಕನ್ನಡ - Android override smoke`
- `localization_override_bootstrap_visible=true`
- `localization_override_form_payload_visible=true`
- `localization_override_option_payload_visible=true`
- `android_backend_label_resolution=true`
- `android_hardcoded_translation=false`
- `android_raw_label_json_visible=false`
- `android_blank_label_visible=false`

## Useful Android-visible probes

```bash
curl -sS \
  -H "X-Tenant-ID: android-fpo-multi-village-test" \
  "http://localhost:8000/api/v1/app-config/bootstrap?project_id=0f7e0a6b-8472-5d6d-8a14-a9d000002001" \
  | python3 -m json.tool | grep -A12 '"form_id": "activity_log"'

curl -sS \
  -H "X-Tenant-ID: android-fpo-multi-village-test" \
  "http://localhost:8000/api/v1/forms/activity_log" \
  | python3 -m json.tool | head -80

curl -sS \
  -H "X-Tenant-ID: android-fpo-multi-village-test" \
  "http://localhost:8000/api/v1/forms/options/languages" \
  | python3 -m json.tool | grep -A8 '"value": "kn"'
```

## Cleanup

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_localization_override_delivery.py --cleanup
```

Cleanup deactivates only overrides tagged with `android_localization_override_delivery.v1` for the FPO tenant.
