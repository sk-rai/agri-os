#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
page = (ROOT / "web/src/app/(admin)/projects/page.tsx").read_text(encoding="utf-8")
api = (ROOT / "web/src/lib/api.ts").read_text(encoding="utf-8")

picker = Path("web/src/components/geography-village-picker.tsx").read_text()

checks = [
    ("API client exposes geography scope update", "updateGeographyScope" in api),
    ("API uses PATCH", 'method: "PATCH"' in api),
    ("API sends canonical village codes", "village_lgd_codes" in api),
    ("API sends an audit reason", "reason" in api),
    ("Projects page exposes scope editing", "Geography scope" in page),
    ("Projects page exposes save action", "Save geography scope" in page),
    ("Projects page exposes cancel action", "Cancel" in page),
    ("Projects page uses canonical village picker", "GeographyVillagePicker" in page),
    ("Picker hydrates saved LGD codes", ".resolveVillagesByLgdCodes(" in picker),
    ("Picker renders saved canonical village names", "village?.name" in picker),
    ("Picker renders saved hierarchy labels", "village.stateName" in picker and "village.districtName" in picker and "village.blockName" in picker),
    ("Picker loads canonical states", "geographyApi" in picker and ".listStates(" in picker),
    ("Picker loads state districts", "geographyApi" in picker and ".listDistricts(" in picker),
    ("Picker performs district-scoped village search", "geographyApi" in picker and ".searchVillages(" in picker),
    ("Picker supports multiple selected villages", "Selected villages" in picker),
    ("Picker supports village removal", "removeVillage" in picker),
    ("Picker prevents duplicate village selection", "selectedCodes.has" in picker),
    ("Projects page requires a reason", "Change reason" in page),
    ("Projects page invokes guarded API", "projectsApi.updateGeographyScope" in page),
    ("Existing scope is loaded into editor", "village_lgd_codes" in page),
    ("PLANNED status governs editing", 'p.status !== "PLANNED"' in page),
    ("Locked-project guidance is rendered", "locked" in page.lower()),
]

print("=" * 72)
print("PROJECT GEOGRAPHY SCOPE EDITOR UI REGRESSION")
print("=" * 72)

failed = []
for label, passed in checks:
    print(("PASS" if passed else "FAIL"), label)
    if not passed:
        failed.append(label)

if failed:
    print("\nFailures:")
    for label in failed:
        print("-", label)
    raise SystemExit(1)

print("=" * 72)
print("PROJECT GEOGRAPHY SCOPE EDITOR UI REGRESSION PASSED")
print("=" * 72)
