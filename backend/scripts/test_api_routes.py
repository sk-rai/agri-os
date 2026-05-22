"""Verify API routes are registered correctly."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app

print(f"App: {app.title} v{app.version}")
print(f"Total routes: {len(app.routes)}")
print("\nAPI Endpoints:")
for route in app.routes:
    if hasattr(route, "methods"):
        methods = ",".join(route.methods - {"HEAD", "OPTIONS"})
        if methods:
            print(f"  {methods:6s} {route.path}")
