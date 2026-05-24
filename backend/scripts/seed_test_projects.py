"""Seed test projects for web admin demo."""
import sys
import uuid
from datetime import datetime, timezone, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.farmer.models import Tenant, Project

db = SessionLocal()

# Ensure tenants exist
tenants = [
    {"id": "test-agri-corp", "name": "Test Agri Corporation", "type": "ENTERPRISE"},
    {"id": "crop-test-tenant", "name": "Crop Test Corp", "type": "ENTERPRISE"},
]
for t in tenants:
    existing = db.query(Tenant).filter(Tenant.id == t["id"]).first()
    if not existing:
        db.add(Tenant(
            id=t["id"], name=t["name"], type=t["type"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
db.commit()

# Seed projects for both tenants
projects = [
    {
        "tenant_id": "test-agri-corp",
        "name": "Kharif 2026 UP Rice Program",
        "start_date": date(2026, 6, 1),
        "end_date": date(2026, 11, 30),
        "status": "ACTIVE",
        "crop_scope": ["RICE", "MAIZE", "BAJRA"],
        "geography_scope": {"state": "UP", "districts": ["Gorakhpur", "Ayodhya", "Lucknow"]},
    },
    {
        "tenant_id": "test-agri-corp",
        "name": "Rabi 2026 Wheat Monitoring - Western UP",
        "start_date": date(2026, 10, 15),
        "end_date": date(2027, 4, 30),
        "status": "PLANNED",
        "crop_scope": ["WHEAT", "MUSTARD", "GRAM"],
        "geography_scope": {"state": "UP", "districts": ["Meerut", "Agra", "Aligarh"]},
    },
    {
        "tenant_id": "test-agri-corp",
        "name": "Sugarcane Lifecycle Tracking 2025-26",
        "start_date": date(2025, 10, 1),
        "end_date": date(2026, 5, 31),
        "status": "COMPLETED",
        "crop_scope": ["SUGARCANE"],
        "geography_scope": {"state": "UP", "districts": ["Gorakhpur", "Deoria", "Kushinagar"]},
    },
    {
        "tenant_id": "crop-test-tenant",
        "name": "FPO Potato Program - Agra Division",
        "start_date": date(2026, 10, 1),
        "end_date": date(2027, 2, 28),
        "status": "PLANNED",
        "crop_scope": ["POTATO"],
        "geography_scope": {"state": "UP", "districts": ["Agra", "Firozabad", "Mainpuri"]},
    },
]

created = 0
for p in projects:
    # Check if project with same name exists for this tenant
    existing = db.query(Project).filter(
        Project.tenant_id == p["tenant_id"],
        Project.name == p["name"],
    ).first()
    if not existing:
        db.add(Project(
            id=uuid.uuid4(),
            tenant_id=p["tenant_id"],
            name=p["name"],
            start_date=p["start_date"],
            end_date=p["end_date"],
            status=p["status"],
            crop_scope=p["crop_scope"],
            geography_scope=p["geography_scope"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        created += 1

db.commit()
db.close()
print(f"Seeded {created} projects. Total: {created + len(projects) - created} in DB.")
