"""Regression for backend-owned weather provider configs and snapshots."""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.database import SessionLocal, engine
from app.main import app
from app.modules.media.provider_runtime_policy import provider_failure_metadata, provider_runtime_policy_from_config
from app.modules.media.weather_provider_adapters import normalize_provider_http_error, normalize_open_meteo_forecast
from scripts.admin_auth_test_utils import create_test_admin, delete_test_admin
from app.modules.farmer.models import Tenant
from app.modules.media.models import WeatherProviderConfig, WeatherSnapshot
from app.modules.media import weather_service
from app.modules.media.weather_service import run_weather_provider_adapter


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
    runtime_policy = provider_runtime_policy_from_config({"timeout_seconds": 999, "max_retries": 3, "demo_payload": {"ok": True}})
    check(runtime_policy.timeout_seconds == 120, "Provider runtime policy clamps timeout")
    check(runtime_policy.max_retries == 3, "Provider runtime policy preserves retry count")
    check(runtime_policy.demo_mode is True, "Provider runtime policy detects demo mode")
    failure_meta = provider_failure_metadata(error=normalize_provider_http_error(provider="OPEN_METEO", status_code=429), policy=runtime_policy)
    check(failure_meta["retryable"] is True, "Provider failure metadata preserves retryable flag")
    check(failure_meta["runtime_policy"]["timeout_seconds"] == 120, "Provider failure metadata includes runtime policy")
    retryable_error = normalize_provider_http_error(provider="OPEN_METEO", status_code=429, message="rate limited")
    check(retryable_error.retryable is True, "Provider HTTP 429 is retryable")
    check(retryable_error.error_code == "PROVIDER_RETRYABLE_HTTP_ERROR", "Provider retryable error code stable")
    non_retryable_error = normalize_provider_http_error(provider="OPEN_METEO", status_code=401, message="unauthorized")
    check(non_retryable_error.retryable is False, "Provider HTTP 401 is non-retryable")
    print("=" * 72)
    print("WEATHER SNAPSHOT FOUNDATION REGRESSION")
    normalized = normalize_open_meteo_forecast(
        {
            "latitude": 25.82,
            "longitude": 82.97,
            "timezone": "Asia/Kolkata",
            "daily": {
                "time": ["2026-07-20"],
                "weather_code": [61],
                "temperature_2m_min": [24.5],
                "temperature_2m_max": [33.8],
                "precipitation_probability_max": [75],
                "precipitation_sum": [18.2],
                "wind_speed_10m_max": [21.0],
            },
            "hourly": {
                "time": ["2026-07-20T09:00"],
                "relative_humidity_2m": [86],
            },
        },
        provider_id=uuid.uuid4(),
        location_scope="VILLAGE",
        location_key="Adapter Village",
        fetched_at=datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc),
        refresh_interval_hours=6,
    )
    check(normalized["condition_code"] == "RAIN", "Open-Meteo adapter normalizes rain forecast")
    check(normalized["rainfall_probability_percent"] == 75, "Open-Meteo adapter maps rain probability")
    check("FUNGAL_RISK" in normalized["risk_flags"], "Open-Meteo adapter derives fungal risk")
    check(normalized["metadata"]["schema_version"] == "open_meteo_weather_adapter.v1", "Open-Meteo adapter metadata schema stable")

    print("=" * 72)

    WeatherProviderConfig.__table__.create(bind=engine, checkfirst=True)
    WeatherSnapshot.__table__.create(bind=engine, checkfirst=True)

    tenant_id = f"weather-test-{uuid.uuid4().hex[:8]}"
    headers = {"X-Tenant-ID": tenant_id}
    client = TestClient(app)

    db = SessionLocal()
    admin = None
    try:
        db.add(Tenant(id=tenant_id, name="Weather Test Tenant", type="ENTERPRISE", created_at=now(), updated_at=now()))
        db.commit()
        admin, admin_headers = create_test_admin(db, tenant_id=tenant_id)
    finally:
        db.close()

    provider_id = uuid.uuid4()
    provider = client.post("/api/v1/weather/providers", headers=admin_headers, json={
        "id": str(provider_id),
        "provider_code": "open-meteo-test",
        "display_name": "Open Meteo Test",
        "provider_type": "EXTERNAL_API",
        "refresh_interval_hours": 6,
        "config": {
            "base_url": "https://api.open-meteo.example",
            "demo_location_scope": "VILLAGE",
            "demo_location_key": "Adapter Worker Village",
            "demo_payload": {
                "latitude": 25.82,
                "longitude": 82.97,
                "timezone": "Asia/Kolkata",
                "daily": {
                    "time": ["2026-07-20"],
                    "weather_code": [61],
                    "temperature_2m_min": [24.5],
                    "temperature_2m_max": [33.8],
                    "precipitation_probability_max": [75],
                    "precipitation_sum": [18.2],
                    "wind_speed_10m_max": [21.0]
                },
                "hourly": {
                    "time": ["2026-07-20T09:00"],
                    "relative_humidity_2m": [86]
                }
            }
        },
        "metadata": {"purpose": "regression"},
    })
    check(provider.status_code == 201, "Create weather provider returns 201", provider.text)
    provider_body = provider.json()
    check(provider_body["refresh_interval_hours"] == 6, "Provider stores 6 hour refresh interval")
    check(provider_body["next_refresh_at"] is not None, "Provider computes next refresh timestamp")

    providers = client.get("/api/v1/weather/providers?enabled=true", headers=admin_headers)
    check(providers.status_code == 200, "List weather providers returns 200", providers.text)
    check(providers.json()["count"] == 1, "Enabled provider list returns seeded provider")

    refresh_plan = client.get("/api/v1/weather/providers/refresh-plan", headers=admin_headers)
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

    manual_refresh = client.post(f"/api/v1/weather/providers/{provider_id}/refresh", headers=admin_headers, json={
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

    adapter_run = client.post(f"/api/v1/weather/providers/{provider_id}/run-adapter", headers=admin_headers)
    check(adapter_run.status_code == 200, "Run weather provider adapter stub returns 200", adapter_run.text)
    adapter_body = adapter_run.json()
    check(adapter_body["schema_version"] == "weather_provider_adapter_run.v1", "Adapter run schema stable")
    check(adapter_body["status"] == "SKIPPED", "Unimplemented external adapter is safely skipped")

    db_adapter = SessionLocal()
    try:
        provider_row = db_adapter.query(WeatherProviderConfig).filter(WeatherProviderConfig.id == provider_id).first()
        direct_result = run_weather_provider_adapter(provider_row)
        check(direct_result.status == "SKIPPED", "Weather adapter service exposes stable skipped result")
    finally:
        db_adapter.close()

    open_meteo_provider_id = uuid.uuid4()
    open_meteo_provider = client.post("/api/v1/weather/providers", headers=admin_headers, json={
        "id": str(open_meteo_provider_id),
        "provider_code": "open_meteo_sample",
        "display_name": "Open-Meteo Sample",
        "provider_type": "EXTERNAL_API",
        "refresh_interval_hours": 6,
        "config": {
            "adapter": "open_meteo",
            "locations": [{"location_scope": "VILLAGE", "location_key": "Broadcast Village", "lat": "12.9716", "lng": "77.5946"}],
            "sample_payload": {
                "fetched_at": fetched_at.isoformat(),
                "current": {"time": fetched_at.isoformat(), "temperature_2m": 29.4, "relative_humidity_2m": 88, "rain": 22.5, "weather_code": 63, "wind_speed_10m": 18},
                "hourly": {"precipitation_probability": [86], "rain": [22.5]},
            },
        },
    })
    check(open_meteo_provider.status_code == 201, "Create Open-Meteo sample provider returns 201", open_meteo_provider.text)
    open_meteo_run = client.post(f"/api/v1/weather/providers/{open_meteo_provider_id}/run-adapter", headers=admin_headers)
    check(open_meteo_run.status_code == 200, "Run Open-Meteo sample adapter returns 200", open_meteo_run.text)
    open_meteo_body = open_meteo_run.json()
    check(open_meteo_body["status"] == "SUCCESS", "Open-Meteo sample adapter succeeds offline")
    check(open_meteo_body["created_snapshot_count"] == 1, "Open-Meteo sample adapter creates snapshot")
    check(open_meteo_body["snapshots"][0]["condition_code"] == "HEAVY_RAIN", "Open-Meteo sample adapter normalizes condition")
    check("HEAVY_RAIN_NEXT_24H" in open_meteo_body["snapshots"][0]["risk_flags"], "Open-Meteo sample adapter derives heavy rain risk")
    check(open_meteo_body["provider"]["metadata"]["risk_thresholds"]["heavy_rain_mm"] == 20, "Open-Meteo adapter records default thresholds")

    strict_provider_id = uuid.uuid4()
    strict_provider = client.post("/api/v1/weather/providers", headers=admin_headers, json={
        "id": str(strict_provider_id),
        "provider_code": "open_meteo_strict",
        "display_name": "Open-Meteo Strict",
        "provider_type": "EXTERNAL_API",
        "refresh_interval_hours": 6,
        "config": {
            "adapter": "open_meteo",
            "risk_thresholds": {"heavy_rain_mm": 50, "heavy_rain_probability_percent": 95, "fungal_humidity_percent": 95},
            "locations": [{"location_scope": "VILLAGE", "location_key": "Broadcast Village", "lat": "12.9716", "lng": "77.5946"}],
            "sample_payload": {
                "fetched_at": fetched_at.isoformat(),
                "current": {"time": fetched_at.isoformat(), "temperature_2m": 29.4, "relative_humidity_2m": 88, "rain": 22.5, "weather_code": 63, "wind_speed_10m": 18},
                "hourly": {"precipitation_probability": [86], "rain": [22.5]},
            },
        },
    })
    check(strict_provider.status_code == 201, "Create Open-Meteo strict-threshold provider returns 201", strict_provider.text)
    strict_run = client.post(f"/api/v1/weather/providers/{strict_provider_id}/run-adapter", headers=admin_headers)
    check(strict_run.status_code == 200, "Run Open-Meteo strict-threshold adapter returns 200", strict_run.text)
    strict_body = strict_run.json()
    check(strict_body["snapshots"][0]["condition_code"] == "RAIN", "Custom heavy-rain thresholds can downgrade condition")
    check("HEAVY_RAIN_NEXT_24H" not in strict_body["snapshots"][0]["risk_flags"], "Custom thresholds can suppress heavy-rain risk")

    live_provider_id = uuid.uuid4()
    live_provider = client.post("/api/v1/weather/providers", headers=admin_headers, json={
        "id": str(live_provider_id),
        "provider_code": "open_meteo_live",
        "display_name": "Open-Meteo Live",
        "provider_type": "EXTERNAL_API",
        "refresh_interval_hours": 6,
        "config": {
            "adapter": "open_meteo",
            "live_fetch_enabled": True,
            "base_url": "https://api.open-meteo.example/v1/forecast",
            "locations": [{"location_scope": "VILLAGE", "location_key": "Live Weather Village", "lat": "13.0", "lng": "77.0"}],
        },
    })
    check(live_provider.status_code == 201, "Create Open-Meteo live provider returns 201", live_provider.text)

    original_fetch = weather_service._fetch_open_meteo_payload
    try:
        def fake_fetch(config, location):
            check(config["base_url"] == "https://api.open-meteo.example/v1/forecast", "Live fetch receives configured base URL")
            check(location["location_key"] == "Live Weather Village", "Live fetch receives configured location")
            return {
                "fetched_at": fetched_at.isoformat(),
                "current": {"time": fetched_at.isoformat(), "temperature_2m": 41.2, "relative_humidity_2m": 55, "rain": 0, "weather_code": 0, "wind_speed_10m": 18},
                "daily": {"temperature_2m_max": [41.2], "temperature_2m_min": [27.0], "time": [fetched_at.date().isoformat()]},
            }
        weather_service._fetch_open_meteo_payload = fake_fetch
        live_run = client.post(f"/api/v1/weather/providers/{live_provider_id}/run-adapter", headers=admin_headers)
    finally:
        weather_service._fetch_open_meteo_payload = original_fetch
    check(live_run.status_code == 200, "Run Open-Meteo live adapter returns 200", live_run.text)
    live_body = live_run.json()
    check(live_body["status"] == "SUCCESS", "Open-Meteo live adapter succeeds with mocked fetch")
    check(live_body["provider"]["metadata"]["mode"] == "live_fetch", "Open-Meteo live adapter records live mode")
    check(live_body["snapshots"][0]["location_key"] == "Live Weather Village", "Open-Meteo live adapter preserves location")
    check("HEAT_STRESS_NEXT_48H" in live_body["snapshots"][0]["risk_flags"], "Open-Meteo live adapter derives heat risk")

    due_provider_id = uuid.uuid4()
    due_provider = client.post("/api/v1/weather/providers", headers=admin_headers, json={
        "id": str(due_provider_id),
        "provider_code": "open_meteo_due",
        "display_name": "Open-Meteo Due",
        "provider_type": "EXTERNAL_API",
        "refresh_interval_hours": 6,
        "config": {
            "adapter": "open_meteo",
            "locations": [{"location_scope": "VILLAGE", "location_key": "Due Weather Village", "lat": "14.0", "lng": "78.0"}],
            "sample_payload": {
                "fetched_at": fetched_at.isoformat(),
                "current": {"time": fetched_at.isoformat(), "temperature_2m": 30.0, "relative_humidity_2m": 90, "rain": 25.0, "weather_code": 63, "wind_speed_10m": 22},
                "hourly": {"precipitation_probability": [88], "rain": [25.0]},
            },
        },
    })
    check(due_provider.status_code == 201, "Create due Open-Meteo provider returns 201", due_provider.text)
    db_due = SessionLocal()
    try:
        due_row = db_due.query(WeatherProviderConfig).filter(WeatherProviderConfig.id == due_provider_id).first()
        due_row.next_refresh_at = fetched_at - timedelta(minutes=1)
        db_due.commit()
    finally:
        db_due.close()

    due_dry_run = client.post("/api/v1/weather/providers/run-due?dry_run=true", headers=admin_headers)
    check(due_dry_run.status_code == 200, "Due weather provider dry-run returns 200", due_dry_run.text)
    due_dry_body = due_dry_run.json()
    check(due_dry_body["schema_version"] == "weather_provider_due_run.v1", "Due weather run schema stable")
    check(due_dry_body["dry_run"] is True, "Due weather dry-run does not process providers")
    check(any(row["provider_code"] == "open_meteo_due" for row in due_dry_body["providers"]), "Due weather dry-run lists due provider")

    weather_health_before = client.get("/api/v1/weather/operations/health", headers=admin_headers)
    check(weather_health_before.status_code == 200, "Weather operations health returns 200", weather_health_before.text)
    weather_health_before_body = weather_health_before.json()
    check(weather_health_before_body["schema_version"] == "weather_operations_health.v1", "Weather operations health schema stable")
    check(weather_health_before_body["summary"]["enabled_provider_count"] >= 1, "Weather operations health counts enabled providers")
    check(any(row["provider_code"] == "open_meteo_due" and row["due"] is True for row in weather_health_before_body["providers"]), "Weather operations health flags due provider")

    due_run = client.post("/api/v1/weather/providers/run-due", headers=admin_headers)
    check(due_run.status_code == 200, "Due weather provider run returns 200", due_run.text)
    due_body = due_run.json()
    check(due_body["dry_run"] is False, "Due weather run processes providers")
    check(due_body["processed_count"] >= 1, "Due weather run processes at least one provider")
    due_result = next(row for row in due_body["providers"] if row["provider_code"] == "open_meteo_due")
    check(due_result["status"] == "SUCCESS", "Due weather run records provider success")
    check(due_result["created_snapshot_count"] == 1, "Due weather run creates snapshot")
    check(due_result["snapshots"][0]["location_key"] == "Due Weather Village", "Due weather run preserves snapshot location")

    weather_health_after = client.get("/api/v1/weather/operations/health", headers=admin_headers)
    check(weather_health_after.status_code == 200, "Weather operations health returns 200 after due run", weather_health_after.text)
    weather_health_after_body = weather_health_after.json()
    check(weather_health_after_body["summary"]["fresh_snapshot_count"] >= 1, "Weather operations health counts fresh snapshots")
    check(any(row["provider_code"] == "open_meteo_due" and row["due"] is False for row in weather_health_after_body["providers"]), "Weather operations health clears due provider after run")


    listed = client.get("/api/v1/weather/snapshots?location_scope=VILLAGE&location_key=Broadcast%20Village", headers=headers)
    check(listed.status_code == 200, "List weather snapshots returns 200", listed.text)
    check(listed.json()["count"] == 4, "List returns active snapshots")

    db_due = SessionLocal()
    try:
        provider_row = db_due.query(WeatherProviderConfig).filter(WeatherProviderConfig.id == provider_id).first()
        provider_row.next_refresh_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_due.commit()
        check(True, "Forced provider due for worker demo payload")
    finally:
        db_due.close()
    worker_dry_run = client.post("/api/v1/weather/refresh-worker/run-due?dry_run=true", headers=admin_headers)
    check(worker_dry_run.status_code == 200, "Weather refresh worker dry run returns 200", worker_dry_run.text)
    worker_dry_body = worker_dry_run.json()
    check(worker_dry_body["schema_version"] == "weather_refresh_worker.v1", "Weather refresh worker schema stable")
    check(worker_dry_body["dry_run"] is True, "Weather refresh worker preserves dry run flag")
    check(worker_dry_body["provider_count"] >= 1, "Weather refresh worker sees configured provider")

    worker_run = client.post("/api/v1/weather/refresh-worker/run-due?dry_run=false", headers=admin_headers)
    check(worker_run.status_code == 200, "Weather refresh worker stub run returns 200", worker_run.text)
    worker_run_body = worker_run.json()
    check(worker_run_body["dry_run"] is False, "Weather refresh worker run preserves execution flag")
    check(worker_run_body["schema_version"] == "weather_refresh_worker.v1", "Weather refresh worker run schema stable")
    check(worker_run_body["refreshed_count"] >= 1, "Weather refresh worker demo payload refreshes provider")
    check(any(row.get("created_snapshot_id") for row in worker_run_body["providers"]), "Weather refresh worker demo payload creates snapshot")

    latest = client.get("/api/v1/weather/snapshots/latest?location_scope=VILLAGE&location_key=Broadcast%20Village", headers=headers)
    check(latest.status_code == 200, "Latest weather snapshot returns 200", latest.text)
    check(latest.json()["summary"] == "Manual refresh weather snapshot", "Latest returns newest non-expired snapshot")

    isolated = client.get("/api/v1/weather/snapshots/latest?location_scope=VILLAGE&location_key=Broadcast%20Village", headers={"X-Tenant-ID": "default"})
    check(isolated.status_code == 404, "Latest weather snapshot is tenant isolated", isolated.text)

    db = SessionLocal()
    try:
        db.query(WeatherSnapshot).filter(WeatherSnapshot.tenant_id == tenant_id).delete(synchronize_session=False)
        db.query(WeatherProviderConfig).filter(WeatherProviderConfig.tenant_id == tenant_id).delete(synchronize_session=False)
        if admin:
            delete_test_admin(db, admin.id)
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
