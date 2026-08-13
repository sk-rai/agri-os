# Broadcast media attachment smoke

Purpose: prove a backend-triggered broadcast/advisory can include an uploaded media attachment that is visible to Android through the farmer broadcast feed and to admins through `/broadcasts`, while preserving text fallback if media cannot load.

## Fixture

- Tenant: `android-fpo-multi-village-test`
- Project: `0f7e0a6b-8472-5d6d-8a14-a9d000002001`
- Selected farmer: `0f7e0a6b-8472-5d6d-8a14-a9d000002106` / `+919900002106`
- Campaign: `0f7e0a6b-8472-5d6d-8a14-a9d000002960`
- Media asset: `0f7e0a6b-8472-5d6d-8a14-a9d000002961`
- Attachment: `0f7e0a6b-8472-5d6d-8a14-a9d000002962`

The smoke creates a single `ADVISORY` campaign targeted by `FARMER` audience rule, attaches one `PHOTO` / `image/jpeg` asset to the English broadcast content as `entity_type=ADVISORY`, `purpose=ADVISORY_ATTACHMENT`, publishes the campaign, and generates one pending delivery.

## Backend verifier

```bash
cd ~/projects/farmint/backend

../venv/bin/python scripts/prepare_android_fpo_multi_village_workflow.py --reset --apply \
  > /tmp/fpo-multi-village-prepare.json \
  2>&1

../venv/bin/python scripts/verify_broadcast_media_attachment_delivery.py --reset --apply \
  > /tmp/broadcast-media-attachment-verify.raw \
  2>&1

echo "broadcast_media_verify_exit=$?"
tail -180 /tmp/broadcast-media-attachment-verify.raw
```

Expected backend evidence:

- campaign status is `PUBLISHED`;
- delivery summary total is `1`;
- admin campaign detail has one `media_attachments[]` item;
- farmer feed has one broadcast for the selected farmer;
- feed content has one `media_attachments[]` item;
- media type is `PHOTO`;
- MIME type is `image/jpeg`;
- upload status is `UPLOADED`;
- text fallback body is still present.

## Web smoke

```bash
cd ~/projects/farmint

set -a
source /tmp/web-smoke-env.sh
set +a

WEB_BASE_URL=http://localhost:3000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
node web/smoke/broadcast_media_attachment_smoke.mjs \
  > /tmp/broadcast-media-attachment-web-smoke.json \
  2>&1

cat /tmp/broadcast-media-attachment-web-smoke.json
```

Expected web evidence:

- campaign is visible under `/broadcasts`;
- delivery total is `1`;
- admin detail renders `Media attachments`;
- admin detail renders `PHOTO / image/jpeg`;
- admin detail renders `UPLOADED`;
- admin detail renders the caption and storage URL;
- API cross-check confirms farmer feed carries the same attachment.

## Cleanup

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/verify_broadcast_media_attachment_delivery.py --cleanup
```

## Android handoff

Android should consume the existing farmer broadcast feed:

```http
GET /api/v1/broadcasts/farmers/{farmer_id}/broadcasts?language_code=en&include_read=true
X-Tenant-ID: android-fpo-multi-village-test
```

For the media campaign, assert:

- `campaign.metadata.android_contract=broadcast_media_attachment.v1`;
- `campaign.metadata.event_type=MEDIA_ADVISORY_WITH_ATTACHMENT`;
- `content.title=Pest scouting photo advisory`;
- `content.body_text` is present and rendered as fallback;
- `content.media_attachments[0].media_type=PHOTO`;
- `content.media_attachments[0].mime_type=image/jpeg`;
- `content.media_attachments[0].upload_status=UPLOADED`;
- `content.media_attachments[0].storage_url` is non-empty;
- `content.media_attachments[0].thumbnail_url` is non-empty;
- `content.media_attachments[0].attachment.purpose=ADVISORY_ATTACHMENT`;
- `content.media_attachments[0].attachment.caption=Pest scouting reference photo`;
- no local media URL construction is required by Android.