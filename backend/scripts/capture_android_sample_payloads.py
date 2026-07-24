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
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import AgentProfile, User
from app.modules.auth.service import create_jwt
from app.modules.farmer.models import Farmer, Parcel, Project, Tenant
from app.modules.media.models import BroadcastAudienceRule, BroadcastAuditEvent, BroadcastCampaign, BroadcastContent, BroadcastDelivery, WeatherProviderConfig, WeatherSnapshot
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
    if isinstance(payload, str):
        import re
        return re.sub(r"\+91\d{10}", "+91XXXXXXXXXX", payload)
    return payload


def assert_ok(label: str, response):
    if response.status_code >= 400:
        raise SystemExit(f'{label} failed: {response.status_code} {response.text[:500]}')
    return response.json()


def bearer(user: User) -> str:
    token, _ = create_jwt(user, 'android-sample-payloads')
    return f'Bearer {token}'


def main() -> int:
    tenant_id = f'android-sample-{uuid.uuid4().hex[:8]}'
    headers = {'X-Tenant-ID': tenant_id, 'X-Actor-ID': str(uuid.uuid4())}
    actor_id = uuid.uuid4()
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    farmer_id = uuid.uuid4()
    parcel_id = uuid.uuid4()
    weather_provider_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    delivery_id = uuid.uuid4()

    db = SessionLocal()
    try:
        now_ts = datetime.now(timezone.utc)
        db.add(Tenant(id=tenant_id, name='Android Sample Tenant', type='ENTERPRISE', created_at=now_ts, updated_at=now_ts))
        db.add(Project(
            id=project_id,
            tenant_id=tenant_id,
            name='Android Sample Project',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            status='ACTIVE',
            geography_scope={'village_names': ['Android Sample Village']},
            crop_scope=['RICE'],
            config={
                'feature_flags': {
                    'backend_driven_farmer_forms': True,
                    'backend_driven_parcel_forms': True,
                    'backend_driven_soil_forms': True,
                    'broadcast_advisories': True,
                    'weather_snapshots': True,
                    'soil_enrichment_snapshots': True,
                }
            },
            created_at=now_ts,
            updated_at=now_ts,
        ))
        sample_user = User(id=user_id, mobile_number='+919811111111', role='FARMER', tenant_id=tenant_id, display_name='Android Sample User', language_preference='hi', created_at=now_ts, updated_at=now_ts)
        db.add(sample_user)
        db.commit()

        mode_bootstrap = assert_ok('mode bootstrap', client.get('/api/v1/auth/mode-bootstrap', headers={'Authorization': bearer(sample_user), 'X-Tenant-ID': tenant_id}))
        write_json('01-mode-bootstrap.json', redact(mode_bootstrap))

        app_bootstrap = assert_ok('app config bootstrap', client.get(f'/api/v1/app-config/bootstrap?project_id={project_id}', headers=headers))
        write_json('02-app-config-bootstrap.json', redact(app_bootstrap))

        pin_villages = assert_ok('PIN code village candidates', client.get('/api/v1/master-data/geography/villages/by-pin-code?pin_code=560001', headers=headers))
        write_json('03-pin-code-villages.json', redact(pin_villages))

        farmer_form = assert_ok('farmer form', client.get('/api/v1/forms/farmer_registration', headers=headers))
        write_json('04-form-farmer-registration.json', redact(farmer_form))

        parcel_form = assert_ok('parcel form', client.get('/api/v1/forms/parcel_registration', headers=headers))
        write_json('05-form-parcel-registration.json', redact(parcel_form))

        soil_form = assert_ok('soil form', client.get('/api/v1/forms/soil_profile', headers=headers))
        write_json('06-form-soil-profile.json', redact(soil_form))

        options = assert_ok('form options', client.get(f'/api/v1/forms/options?project_id={project_id}', headers=headers))
        write_json('07-form-options.json', redact(options))

        profile_contract = assert_ok('profile contract', client.get(f'/api/v1/forms/profile-contract?project_id={project_id}', headers=headers))
        write_json('08-profile-contract.json', redact(profile_contract))

        farmer = assert_ok('create farmer', client.post('/api/v1/farmers', headers=headers, json={
            'id': str(farmer_id),
            'mobile_number': '+919800000000',
            'user_id': str(user_id),
            'project_id': str(project_id),
            'display_name': 'Android Sample Farmer',
            'pin_code': '560001',
            'village_name_manual': 'Android Sample Village',
            'preferred_language': 'hi',
            'assistance_mode': 'FIELD_AGENT_ASSISTED',
        }))
        write_json('09-farmer-create-response.json', redact(farmer))

        farmer_id = uuid.UUID(str(farmer['id']))

        parcel = assert_ok('create parcel', client.post('/api/v1/parcels', headers=headers, json={
            'id': str(parcel_id),
            'farmer_id': str(farmer_id),
            'reported_area': 1.25,
            'area_unit': 'ACRE',
            'ownership_type': 'OWNED',
            'pin_code': '560001',
            'village_name_manual': 'Android Sample Village',
            'location_scope': {'type': 'SAME_AS_HOME', 'same_as_home_location': True, 'source': 'farmer_confirmation'},
            'geometry_source': 'PIN_DROP',
            'centroid_lat': 25.82,
            'centroid_lng': 82.97,
        }))
        write_json('10-parcel-create-response.json', redact(parcel))

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
        write_json('11-soil-profile-create-response.json', redact(soil))

        db.add(WeatherProviderConfig(id=weather_provider_id, tenant_id=tenant_id, provider_code='android_sample_manual', display_name='Android Sample Manual Weather', provider_type='MANUAL', refresh_interval_hours=6, is_enabled=True, config={}, metadata_={}, created_at=now_ts, updated_at=now_ts))
        db.add(WeatherSnapshot(id=uuid.uuid4(), tenant_id=tenant_id, provider_id=weather_provider_id, parcel_id=parcel_id, location_scope='VILLAGE', location_key='Android Sample Village', fetched_at=now_ts, forecast_valid_from=now_ts, forecast_valid_to=now_ts + timedelta(hours=24), expires_at=now_ts + timedelta(hours=6), summary='Light rain expected', condition_code='RAIN', rainfall_probability_percent=70, rainfall_mm='6.5', temperature_min_c='23', temperature_max_c='31', humidity_percent=82, wind_speed_kmph='12', risk_flags=['RAIN_NEXT_24H'], source_payload={'sample': True}, metadata_={'capture': 'android_sample_payloads'}, created_at=now_ts, updated_at=now_ts))
        db.add(BroadcastCampaign(id=campaign_id, tenant_id=tenant_id, project_id=project_id, title='Android Sample Rain Advisory', category='WEATHER', priority='HIGH', status='PUBLISHED', starts_at=now_ts, expires_at=now_ts + timedelta(days=2), metadata_={'targeting_mode': 'SAMPLE'}, is_active=True, created_at=now_ts, updated_at=now_ts))
        db.add(BroadcastContent(id=uuid.uuid4(), tenant_id=tenant_id, campaign_id=campaign_id, language_code='hi', title='Rain advisory', body_text='Light rain is expected. Review irrigation plans before applying inputs.', cta_label='View details', deeplink_url='agrios://broadcasts/rain-advisory', metadata_={}, created_at=now_ts, updated_at=now_ts))
        db.add(BroadcastAudienceRule(id=uuid.uuid4(), tenant_id=tenant_id, campaign_id=campaign_id, rule_type='FARMER', operator='IN', values=[str(farmer_id)], metadata_={}, created_at=now_ts))
        db.add(BroadcastDelivery(id=delivery_id, tenant_id=tenant_id, campaign_id=campaign_id, farmer_id=farmer_id, user_id=user_id, delivery_status='PENDING', metadata_={}, created_at=now_ts, updated_at=now_ts))
        db.commit()

        readiness = assert_ok('profile readiness', client.get(f'/api/v1/farmers/profile-readiness?status=ACTIVE&limit=5&project_id={project_id}', headers=headers))
        write_json('12-profile-readiness.json', redact(readiness))

        summary = assert_ok('soil enrichment summary', client.get(f'/api/v1/soil-profiles/enrichments/summary?parcel_id={parcel_id}', headers=headers))
        write_json('13-soil-enrichment-summary.json', redact(summary))

        latest_soil = client.get(f'/api/v1/soil-profiles/enrichments/latest?parcel_id={parcel_id}', headers=headers)
        write_json('14-soil-enrichment-latest-or-error.json', redact(latest_soil.json()))

        latest_weather = assert_ok('latest weather snapshot', client.get('/api/v1/weather/snapshots/latest?location_scope=VILLAGE&location_key=Android%20Sample%20Village', headers=headers))
        write_json('15-weather-latest-snapshot.json', redact(latest_weather))

        farmer_broadcasts = assert_ok('farmer broadcasts', client.get(f'/api/v1/broadcasts/farmers/{farmer_id}/broadcasts', headers=headers))
        write_json('16-broadcast-feed.json', redact(farmer_broadcasts))

        broadcast_detail = assert_ok('broadcast detail', client.get(f'/api/v1/broadcasts/{campaign_id}', headers=headers))
        write_json('17-broadcast-detail.json', redact(broadcast_detail))

        broadcast_read = assert_ok('broadcast read', client.post(f'/api/v1/broadcasts/deliveries/{delivery_id}/read', headers=headers))
        write_json('18-broadcast-read-response.json', redact(broadcast_read))

        broadcast_ack = assert_ok('broadcast acknowledge', client.post(f'/api/v1/broadcasts/deliveries/{delivery_id}/acknowledge', headers=headers))
        write_json('19-broadcast-ack-response.json', redact(broadcast_ack))

        crop_template = assert_ok('rice crop template', client.get('/api/v1/crop-cycles/templates/RICE', headers=headers))
        write_json('20-crop-template-rice.json', redact(crop_template))

        enabled_workflows = assert_ok('enabled crop workflows', client.get(f'/api/v1/workflow-catalog/enabled-crop-workflows?project_id={project_id}', headers=headers))
        write_json('21-enabled-crop-workflows.json', redact(enabled_workflows))

        sync_error = assert_ok('sync dependency error sample', client.post('/api/v1/sync/events', headers=headers, json={'events': [{'event_id': str(uuid.uuid4()), 'entity_type': 'parcel', 'operation': 'CREATE', 'payload': {'area': 1.0, 'farmer_id': str(farmer_id)}, 'version': 1, 'dependency_ids': [str(uuid.uuid4())]}]}))
        write_json('22-sync-dependency-error.json', redact(sync_error))

        readme = OUT / 'README.md'
        readme.write_text('\n'.join([
            '# Android Sample Payloads',
            '',
            f'Generated from temporary tenant `{tenant_id}` and temporary project `{project_id}`.',
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
        db.query(BroadcastAuditEvent).filter(BroadcastAuditEvent.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastDelivery).filter(BroadcastDelivery.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastAudienceRule).filter(BroadcastAudienceRule.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastContent).filter(BroadcastContent.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(BroadcastCampaign).filter(BroadcastCampaign.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(WeatherSnapshot).filter(WeatherSnapshot.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(WeatherProviderConfig).filter(WeatherProviderConfig.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(SoilProfile).filter(SoilProfile.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(SoilEnrichmentSnapshot).filter(SoilEnrichmentSnapshot.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Parcel).filter(Parcel.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Farmer).filter(Farmer.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(AgentProfile).filter(AgentProfile.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(User).filter(User.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        db.close()

    print('=' * 72)
    print('Android sample payload capture complete')
    print('=' * 72)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
