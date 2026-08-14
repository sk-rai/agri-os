# Broadcast language fallback smoke

Purpose: prove backend-owned language selection for farmer broadcasts. Android should render the `content` object returned by the farmer feed and should not merge languages locally.

## Fixture

- Tenant: `android-fpo-multi-village-test`
- Project: `0f7e0a6b-8472-5d6d-8a14-a9d000002001`
- Selected farmer: `0f7e0a6b-8472-5d6d-8a14-a9d000002106` / `+919900002106`
- Campaign: `0f7e0a6b-8472-5d6d-8a14-a9d000002970`
- Media asset: `0f7e0a6b-8472-5d6d-8a14-a9d000002971`
- Attachment: `0f7e0a6b-8472-5d6d-8a14-a9d000002972`

The smoke creates a single `ADVISORY` campaign targeted by `FARMER` audience rule. The campaign has English and Hindi content. The English fallback content carries one `PHOTO` / `image/jpeg` media attachment.

## Backend verifier

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/fpo-multi-village-prepare.json \
  2>&1

../venv/bin/python scripts/verify_broadcast_language_fallback_delivery.py --reset --apply \
  > /tmp/broadcast-language-fallback-verify.raw \
  2>&1

echo "broadcast_language_verify_exit=$?"
tail -180 /tmp/broadcast-language-fallback-verify.raw
```

Expected backend evidence:

- campaign status is `PUBLISHED`;
- delivery summary total is `1`;
- admin detail exposes content languages `en` and `hi`;
- farmer feed with `language_code=hi` returns Hindi content;
- farmer feed with `language_code=kn` falls back to English content;
- farmer feed with no `language_code` defaults to English content;
- English fallback content preserves its media attachment;
- Android language selection is backend-owned.

## Web smoke

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/broadcast_language_fallback_smoke.mjs \
  > /tmp/broadcast-language-fallback-web-smoke.json \
  2>&1

cat /tmp/broadcast-language-fallback-web-smoke.json
```

Expected web evidence:

- campaign is visible under `/broadcasts`;
- admin detail renders English and Hindi content rows;
- admin detail renders the fallback media attachment;
- API cross-check confirms Hindi selection and unsupported-language English fallback.

## Cleanup

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_broadcast_language_fallback_delivery.py --cleanup
```

## Android handoff

Android should call the existing farmer broadcast feed:

```http
GET /api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code={device_or_profile_language}&include_read=true
X-Tenant-ID: android-fpo-multi-village-test
```

For this campaign, assert:

- `campaign.metadata.android_contract=broadcast_language_fallback.v1`;
- `campaign.metadata.event_type=LANGUAGE_FALLBACK_ADVISORY`;
- `campaign.metadata.language_selection_backend_owned=true`;
- `language_code=hi` returns `content.language_code=hi` and `content.title=कीट फोटो सलाह`;
- unsupported `language_code=kn` returns `content.language_code=en` and `content.title=Pest scouting language fallback advisory`;
- omitted `language_code` returns English;
- fallback English content keeps `media_attachments[0].media_type=PHOTO`;
- Android renders returned `content.language_code` and does not perform local language merge/fallback.