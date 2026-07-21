#!/usr/bin/env python3
"""Capture repeatable redacted Android sample payloads.

Creates temporary tenant/farmer/parcel/soil data, calls selected Android-allowed
endpoints, writes representative JSON files under docs/samples/android,
then cleans up temporary rows.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import uuid
from datetime import date, datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.farmer.models import Farmer, Parcel, Tenant
from app.modules.farmer.soil_profile import SoilEnrichmentSnapshot, SoilProfile


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs' / 'samples' / 'android'
client = TestClient(app)


def write_json(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, default=str, sort_keys=True) + '\n', encoding='utf-8')
    print(f'wrote {path.relative_to(ROOT)}')


def redact(payload):
    if isinstance(payload, dict):
        redacted = {}
        for key, value in payload.items():
            if key in {'mobile_number', 'support_phone'} and value:
                redacted[key] = '+91XXXXXXXXXX'
            elif key in {'Authorization'}:
                redacted[key] = 'Bearer <redacted>'
            else:
                redacted[key] = redact(value)
        return redacted
    if isinstance(payload, list):
        return [redact(item) for item in payload]
    return payload


def assert_ok(label: str, response):
    if response.status_code >= 400:
        raise SystemExit(f'{label} failed: {response.status_code} {response.text[:500]}')
    return response.json()


def main() -> int:
    tenant_id = f'android-sample-{uuid.uuid4().hex[:8]}'
    headers = {'X-Tenant-ID': tenant_id, 'X-Actor-ID': str(uuid.uuid4())}
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name='Android Sample Tenant', type='ENTERPRISE', created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
        db.commit()

        form = assert_ok('farmer form', client.get('/api/v1/forms/farmer_registration', headers=headers))
        write_json('02-form-farmer-registration.json', redact(form))

        options = assert_ok('form options', client.get('/api/v1/forms/options', headers=headers))
        write_json('03-form-options.json', redact(options))

        farmer = assert_ok('create farmer', client.post('/api/v1/farmers', headers=headers, json={
            'id': str(farmer_id),
            'mobile_number': '+919800000000',
            'display_name': 'Android Sample Farmer',
            'pin_code': '560001',
            'village_name_manual': 'Android Sample Village',
            'preferred_language': 'hi',
            'assistance_mode': 'FIELD_AGENT_ASSISTED',
        }))
        write_json('04-farmer-create-response.json', redact(farmer))

        farmer_id = uuid.UUID(str(farmer['id']))

        parcel = assert_ok('create parcel', client.post('/api/v1/parcels', headers=headers, json={
            'id': str(parcel_id),
            'farmer_id': str(farmer_id),
            'reported_area': 1.25,
            'area_unit': 'ACRE',
            'ownership_type': 'OWNED',
            'pin_code': '560001',
            'village_name_manual': 'Android Sample Village',
            'location_scope': {'type': 'SINGLE_VILLAGE'},
            'geometry_source': 'PIN_DROP',
            'centroid_lat': 25.82,
            'centroid_lng': 82.97,
        }))
        write_json('05-parcel-create-response.json', redact(parcel))

        parcel_id = uuid.UUID(str(parcel['id']))

        soil = assert_ok('create soil profile', client.post('/api/v1/soil-profiles', headers=headers, json={
            'farmer_id': str(farmer_id),
            'parcel_id': str(parcel_id),
            'data_source': 'LAB_REPORT',
            'test_date': str(date.today()),
            'lab_name': 'Android Sample Lab',
            'ph': 7.2,
            'organic_carbon_oc': 0.55,
            'nitrogen_n': 163,
            'phosphorus_p': 9,
            'potassium_k': 213,
            'boron_b': 0.35,
        }))
        write_json('06-soil-profile-create-response.json', redact(soil))

        readiness = assert_ok('profile readiness', client.get(f'/api/v1/farmers/profile-readiness?status=ACTIVE&limit=5', headers=headers))
        write_json('07-profile-readiness.json', redact(readiness))

        summary = assert_ok('soil enrichment summary', client.get(f'/api/v1/soil-profiles/enrichments/summary?parcel_id={parcel_id}', headers=headers))
        write_json('08-soil-enrichment-summary.json', redact(summary))

        latest_soil = client.get(f'/api/v1/soil-profiles/enrichments/latest?parcel_id={parcel_id}', headers=headers)
        write_json('09-soil-enrichment-latest-or-error.json', redact(latest_soil.json()))

        readme = OUT / 'README.md'
        readme.write_text('\n'.join([
            '# Android Sample Payloads',
            '',
            f'Generated from temporary tenant `{tenant_id}`.',
            '',
            'These payloads are representative and redacted. Regenerate with:',
            '',
            '```bash',
            'cd ~/projects/farmint/backend',
            '../venv/bin/python scripts/capture_android_sample_payloads.py',
            '```',
            '',
        ]) + '\n', encoding='utf-8')
        print(f'wrote {readme.relative_to(ROOT)}')

    finally:
        db.query(SoilProfile).filter(SoilProfile.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(SoilEnrichmentSnapshot).filter(SoilEnrichmentSnapshot.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        db.close()

    print('=' * 72)
    print('Android sample payload capture complete')
    print('=' * 72)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
