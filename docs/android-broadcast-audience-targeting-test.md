# Android broadcast audience targeting test

Purpose: prove broadcast audience rules deliver to the intended farmer cohorts and do not silently overdeliver. This uses the FPO multi-village fixture with multiple crops, villages, and active crop stages.

## Fixture

Tenant/project:

- `X-Tenant-ID: android-fpo-multi-village-test`
- project `0f7e0a6b-8472-5d6d-8a14-a9d000002001`

Campaigns:

- `crop_rice`: `0f7e0a6b-8472-5d6d-8a14-a9d000002990`, rule `CROP IN [RICE]`
- `location_rampur`: `0f7e0a6b-8472-5d6d-8a14-a9d000002991`, rule `LOCATION IN [FPO Rampur]`
- `stage_active`: `0f7e0a6b-8472-5d6d-8a14-a9d000002992`, rule `STAGE IN [{dynamic active stage code for farmer 06}]`
- `unsupported_role`: `0f7e0a6b-8472-5d6d-8a14-a9d000002993`, rule `ROLE IN [FARMER_LEADER]`

Each campaign has:

- `campaign.metadata.android_contract=broadcast_audience_targeting.v1`
- `campaign.metadata.targeting_backend_owned=true`

## Backend commands

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/fpo-multi-village-prepare.json \
  2>&1

../venv/bin/python scripts/prepare_android_broadcast_audience_targeting.py --reset --apply \
  > /tmp/broadcast-audience-targeting-verify.raw \
  2>&1

echo "broadcast_audience_targeting_verify_exit=$?"
tail -220 /tmp/broadcast-audience-targeting-verify.raw
```

Cleanup:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/prepare_android_broadcast_audience_targeting.py --cleanup
```

## Android endpoints

Use farmer feed for included/excluded farmer checks:

```http
GET /api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code=en&include_read=true
X-Tenant-ID: android-fpo-multi-village-test
```

The verifier output contains exact expected farmer ids for each campaign under `expected`.

## Android expected evidence

Suggested evidence lines:

```text
broadcast_targeting_contract=broadcast_audience_targeting.v1
broadcast_targeting_backend_owned=true
broadcast_targeting_crop_rice_included_visible=true
broadcast_targeting_crop_rice_excluded_visible=false
broadcast_targeting_location_rampur_included_visible=true
broadcast_targeting_location_rampur_excluded_visible=false
broadcast_targeting_stage_active_code=<stage_code_from_backend_output>
broadcast_targeting_stage_included_visible=true
broadcast_targeting_stage_excluded_visible=false
broadcast_targeting_unsupported_role_delivery_count=0
broadcast_targeting_unsupported_role_visible=false
broadcast_targeting_no_silent_overdelivery=true
```

## Product note

This smoke proves broadcast targeting over the FPO demo is backend-owned and precise enough for Android: crop, village/location, and active stage campaigns show only to included farmers. Unsupported targeting rules are accepted as campaign configuration but do not create delivery rows or appear in farmer feeds until backend expansion support exists.