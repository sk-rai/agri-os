"""Regression for backend-owned weather provider configs and snapshots."""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal, engine
from app.main import app
from app.modules.farmer.models import Tenant
from app.modules.media.models import WeatherProviderConfig, WeatherSnapshot


def check(condition, label, detail=None):
    if condition:
        print(f"  PASS {label}")
        if detail is not None:
            print(f"       {detail}")
        return
    print(f"  FAIL {label}")
    if detail is not None:
        print(f"       {detail}")
    raise AssertionError(label)


def now():
    return datetime.now(timezone.utc)


def main():
    print("=" * 72)
    print("WEATHER SNAPSHOT FOUNDATION REGRESSION")
    print("=" * 72)

    WeatherProviderConfig.__table__.create(bind=engine, checkfirst=True)
    WeatherSnapshot.__table__.create(bind=engine, checkfirst=True)

    tenant_id = f"weather-test-{uuid.uuid4().hex[:8]}"
    headers = {"X-Tenant-ID": tenant_id}
    client = TestClient(app)

    db = SessionLocal()
    try:
        db.add(Tenant(id=tenant_id, name="Weather Test Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.commit()
    finally:
        db.close()

    provider_id = uuid.uuid4()
    provider = client.post("/api/v1/weather/providers", headers=headers, json={
        "id": str(provider_id),
        "provider_code": "open-meteo-test",
        "display_name": "Open Meteo Test",
        "provider_type": "EXTERNAL_API",
        "refresh_interval_hours": 6,
        "config": {"base_url": "https://api.open-meteo.example"},
        "metadata": {"purpose": "regression"},
    })
    check(provider.status_code == 201, "Create weather provider returns 201", provider.text)
    provider_body = provider.json()
    check(provider_body["refresh_interval_hours"] == 6, "Provider stores 6 hour refresh interval")
    check(provider_body["next_refresh_at"] is not None, "Provider computes next refresh timestamp")

    providers = client.get("/api/v1/weather/providers?enabled=true", headers=headers)
    check(providers.status_code == 200, "List weather providers returns 200", providers.text)
    check(providers.json()["count"] == 1, "Enabled provider list returns seeded provider")

    refresh_plan = client.get("/api/v1/weather/providers/refresh-plan", headers=headers)
    check(refresh_plan.status_code == 200, "Weather refresh plan returns 200", refresh_plan.text)
    refresh_plan_body = refresh_plan.json()
    check(refresh_plan_body["schema_version"] == "weather_refresh_plan.v1", "Refresh plan schema stable")
    check(refresh_plan_body["count"] == 1, "Refresh plan returns seeded provider")
    check("is_due" in refresh_plan_body["providers"][0], "Refresh plan reports due state")

    fetched_at = now()
    snapshot = client.post("/api/v1/weather/snapshots", headers=headers, json={
        "provider_id": str(provider_id),
        "location_scope": "VILLAGE",
        "location_key": "Broadcast Village",
        "lat": "12.9716",
        "lng": "77.5946",
        "fetched_at": fetched_at.isoformat(),
        "forecast_valid_from": fetched_at.isoformat(),
        "forecast_valid_to": (fetched_at + timedelta(hours=24)).isoformat(),
        "expires_at": (fetched_at + timedelta(hours=6)).isoformat(),
        "summary": "Heavy rainfall likely",
        "condition_code": "HEAVY_RAIN",
        "rainfall_probability_percent": 82,
        "rainfall_mm": "34.5",
        "temperature_min_c": "22.1",
        "temperature_max_c": "29.8",
        "humidity_percent": 88,
        "wind_speed_kmph": "18",
        "risk_flags": ["heavy_rain_next_24h", "fungal_risk"],
        "source_payload": {"provider_record_id": "wx-1"},
        "metadata": {"freshness_policy_hours": 6},
    })
    check(snapshot.status_code == 201, "Create weather snapshot returns 201", snapshot.text)
    snapshot_body = snapshot.json()
    check(snapshot_body["condition_code"] == "HEAVY_RAIN", "Snapshot normalizes condition code")
    check("HEAVY_RAIN_NEXT_24H" in snapshot_body["risk_flags"], "Snapshot normalizes risk flags")

    manual_refresh = client.post(f"/api/v1/weather/providers/{provider_id}/refresh", headers=headers, json={
        "status": "SUCCESS",
        "message": "manual regression refresh",
        "metadata": {"trigger": "regression"},
        "snapshots": [{
            "location_scope": "VILLAGE",
            "location_key": "Broadcast Village",
            "fetched_at": (fetched_at + timedelta(minutes=5)).isoformat(),
            "forecast_valid_from": fetched_at.isoformat(),
            "forecast_valid_to": (fetched_at + timedelta(hours=24)).isoformat(),
            "expires_at": (fetched_at + timedelta(hours=6)).isoformat(),
            "summary": "Manual refresh weather snapshot",
            "condition_code": "RAIN",
            "risk_flags": ["fungal_risk"],
        }],
    })
    check(manual_refresh.status_code == 200, "Record weather provider refresh returns 200", manual_refresh.text)
    refresh_body = manual_refresh.json()
    check(refresh_body["schema_version"] == "weather_provider_refresh.v1", "Refresh response schema stable")
    check(refresh_body["created_snapshot_count"] == 1, "Refresh can create normalized snapshots")
    check(refresh_body["provider"]["refresh_status"] == "SUCCESS", "Refresh records provider status")
    check(refresh_body["provider"]["next_refresh_at"] is not None, "Refresh computes next provider due timestamp")

    listed = client.get("/api/v1/weather/snapshots?location_scope=VILLAGE&location_key=Broadcast%20Village", headers=headers)
    check(listed.status_code == 200, "List weather snapshots returns 200", listed.text)
    check(listed.json()["count"] == 2, "List returns active snapshots")

    latest = client.get("/api/v1/weather/snapshots/latest?location_scope=VILLAGE&location_key=Broadcast%20Village", headers=headers)
    check(latest.status_code == 200, "Latest weather snapshot returns 200", latest.text)
    check(latest.json()["summary"] == "Manual refresh weather snapshot", "Latest returns newest non-expired snapshot")

    isolated = client.get("/api/v1/weather/snapshots/latest?location_scope=VILLAGE&location_key=Broadcast%20Village", headers={"X-Tenant-ID": "default"})
    check(isolated.status_code == 404, "Latest weather snapshot is tenant isolated", isolated.text)

    db = SessionLocal()
    try:
        db.query(WeatherSnapshot).filter(WeatherSnapshot.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(WeatherProviderConfig).filter(WeatherProviderConfig.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        db.commit()
        check(True, "Temporary rows cleaned up")
    finally:
        db.close()

    print("=" * 72)
    print("Weather snapshot foundation validated")
    print("=" * 72)


if __name__ == "__main__":
    main()
