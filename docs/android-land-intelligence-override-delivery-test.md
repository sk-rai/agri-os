# Android Land-Intelligence Override Delivery Smoke

This smoke verifies Android consumes a backend/admin-published land-intelligence summary override for the FPO project and keeps the card informational-only.

## Backend prepare

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_land_intelligence_override_delivery.py --reset --apply \
  > /tmp/android-land-intelligence-override-prepare.raw \
  2>&1

echo "land_intelligence_override_prepare_exit=$?"
tail -180 /tmp/android-land-intelligence-override-prepare.raw
```

## Canonical contract

- `schema_version=android_land_intelligence_override_delivery.v1`
- `tenant_id=android-fpo-multi-village-test`
- `project_id=0f7e0a6b-8472-5d6d-8a14-a9d000002001`
- `scope_type=PIN`
- `scope_code=560003`
- `season_code=KHARIF`
- `crop_code=MAIZE`
- `language_code=en`

Expected backend-provided summary:

- title: `FPO Maize land intelligence override`
- subtitle: `Backend-published FPO guidance for PIN 560003`
- region card value: `FPO Harohalli maize cluster`
- soil-water card value: `Check irrigation before fertilizer`
- caveat: `Informational only: do not block farmer onboarding.`
- summary source: `PROJECT_OVERRIDE`
- four cards, two main crops, two alternate crops

## Android-visible probe

```bash
curl -sS \
  -H "X-Tenant-ID: android-fpo-multi-village-test" \
  "http://localhost:8000/api/v1/profile/land-intelligence-summary?pin_code=560003&season_code=KHARIF&crop_code=MAIZE&language_code=en&project_id=0f7e0a6b-8472-5d6d-8a14-a9d000002001" \
  | python3 -m json.tool | head -160
```

## Android pass criteria

Android should verify:

- `land_intelligence_override_contract=android_land_intelligence_override_delivery.v1`
- `land_intelligence_override_scope=PIN:560003`
- `land_intelligence_override_project_id=0f7e0a6b-8472-5d6d-8a14-a9d000002001`
- `land_intelligence_override_source=PROJECT_OVERRIDE`
- `land_intelligence_override_title=FPO Maize land intelligence override`
- `land_intelligence_override_region=FPO Harohalli maize cluster`
- `land_intelligence_override_soil_water=Check irrigation before fertilizer`
- `land_intelligence_override_card_count=4`
- `land_intelligence_override_main_crop_count=2`
- `land_intelligence_override_alternate_crop_count=2`
- `land_intelligence_override_selected_crop=MAIZE`
- `land_intelligence_informational_only=true`
- `land_intelligence_do_not_block_onboarding=true`
- `android_hardcoded_land_summary=false`
- `android_raw_summary_json_visible=false`
- `android_blank_land_card_visible=false`

## Cleanup

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_land_intelligence_override_delivery.py --cleanup
```

Cleanup deactivates only overrides tagged with `android_land_intelligence_override_delivery.v1` for the FPO tenant.
