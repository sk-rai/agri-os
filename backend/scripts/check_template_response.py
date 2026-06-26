"""Check if recommended_activities is in the template API response."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
r = client.get("/api/v1/crop-cycles/templates/RICE?season=KHARIF")
d = r.json()

print(f"Status: {r.status_code}")
if r.status_code != 200:
    print(f"Error: {d}")
    # Try with headers
    r = client.get("/api/v1/crop-cycles/templates/RICE?season=KHARIF", headers={"X-Tenant-ID": "default", "X-Actor-ID": "test"})
    d = r.json()
    print(f"With headers - Status: {r.status_code}")
    if r.status_code != 200:
        print(f"Error: {d}")
        sys.exit(1)

print(f"Stages: {len(d.get('stages', []))}")

for i, stage in enumerate(d.get("stages", [])):
    ra = stage.get("recommended_activities")
    if ra:
        print(f"\nStage {i+1} ({stage['code']}): {len(ra)} recommended activities")
        for a in ra[:3]:
            print(f"  Day {a['day_offset']}: {a['input_name']} ({a['activity_type']})")
        if len(ra) > 3:
            print(f"  ... and {len(ra)-3} more")
    else:
        print(f"\nStage {i+1} ({stage['code']}): NO recommended_activities")
