#!/usr/bin/env python3
"""Probe whether CoRE/LGD overlay inputs can be acquired automatically.

Safe/read-only by default:

- no downloads;
- no Google Earth Engine export tasks;
- no portal scraping;
- no database writes.

The goal is to tell the operator whether automation is plausible from the
current WSL environment, or whether manual portal/GEE export is still required.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
CORE_EXPORT_DIR = ROOT / "data/staged/core_stack/exports"
BOUNDARY_DIR = ROOT / "data/staged/boundaries"
MANIFEST_PATH = ROOT / "data/staged/core_stack/core_stack_climate_layer_manifest.json"

SOURCE_URLS = {
    "aikosh_core_stack_dataset": "https://aikosh.indiaai.gov.in/web/datasets/details/agro_ecological_climatic_and_biogeographic_zone.html",
    "core_stack_dataset_directory": "https://core-stack.org/datasets-contents/",
    "core_stack_gee_directory_app": "https://ee-corestackdev.projects.earthengine.app",
    "core_stack_technical_manual": "https://core-stack.org/core-stack-technical-manual-v2/",
    "survey_of_india_abdb": "https://surveyofindia.gov.in/pages/administrative-boundary-data-base-abdb-",
    "india_maps_products": "https://indiamaps.gov.in/product",
    "lgd_directory_download": "https://lgdirectory.gov.in/demo/downloadDirectory.do",
    "ogd_admin_boundaries": "https://www.data.gov.in/catalog/admin-boundaries",
}

EXPECTED_CORE_EXPORTS = [
    "Agro_Ecological_Zones.geojson",
    "Agro_Climatic_Zones.geojson",
    "Biogeographic_Zone_pan_india.geojson",
]

GEE_ASSETS = [
    "projects/ext-datasets/assets/datasets/Agro_Ecological_Zones",
    "projects/ext-datasets/assets/datasets/Agro_Climatic_Zones",
    "projects/ext-datasets/assets/datasets/Biogeographic_Zone_pan_india",
]


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def run_version(command: list[str]) -> dict:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:  # noqa: BLE001 - probe should report all failures
        return {"available": False, "error": str(exc)}
    return {
        "available": completed.returncode == 0,
        "return_code": completed.returncode,
        "stdout": completed.stdout.strip()[:500],
        "stderr": completed.stderr.strip()[:500],
    }


def probe_url(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "farmint-core-lgd-source-probe/1.0"})
    try:
        with urlopen(request, timeout=12) as response:  # noqa: S310 - explicit source probe
            return {
                "reachable": 200 <= response.status < 400,
                "status": response.status,
                "content_type": response.headers.get("content-type"),
                "final_url": response.geturl(),
            }
    except URLError as exc:
        return {"reachable": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - probe should report all failures
        return {"reachable": False, "error": str(exc)}


def existing_files() -> dict:
    return {
        "core_export_dir_exists": CORE_EXPORT_DIR.exists(),
        "expected_core_exports": [
            {
                "filename": filename,
                "path": str(CORE_EXPORT_DIR / filename),
                "exists": (CORE_EXPORT_DIR / filename).exists(),
            }
            for filename in EXPECTED_CORE_EXPORTS
        ],
        "boundary_dir_exists": BOUNDARY_DIR.exists(),
        "boundary_candidate_count": len(list(BOUNDARY_DIR.rglob("*"))) if BOUNDARY_DIR.exists() else 0,
        "manifest_exists": MANIFEST_PATH.exists(),
        "manifest_path": str(MANIFEST_PATH),
    }


def main() -> int:
    earthengine_present = command_exists("earthengine")
    gcloud_present = command_exists("gcloud")
    aikosh_present = command_exists("aikosh")

    result = {
        "schema_version": "core_lgd_download_source_probe.v1",
        "mode": "PROBE_ONLY_READ_ONLY",
        "external_downloads_made": False,
        "gee_exports_started": False,
        "portal_scraping_attempted": False,
        "db_writes_made": False,
        "local_files": existing_files(),
        "source_urls": SOURCE_URLS,
        "gee_assets": GEE_ASSETS,
        "tooling": {
            "earthengine_cli_present": earthengine_present,
            "earthengine_cli_version": run_version(["earthengine", "--version"]) if earthengine_present else None,
            "gcloud_cli_present": gcloud_present,
            "gcloud_cli_version": run_version(["gcloud", "--version"]) if gcloud_present else None,
            "aikosh_cli_present": aikosh_present,
            "aikosh_cli_probe": run_version(["aikosh", "--help"]) if aikosh_present else None,
        },
        "url_reachability": {name: probe_url(url) for name, url in SOURCE_URLS.items()},
        "automation_assessment": {
            "core_exports_automatic_possible": earthengine_present or aikosh_present,
            "core_exports_recommended_path": (
                "Use authenticated Earth Engine export or Aikosh/direct-download tooling if dataset files are discoverable."
                if earthengine_present or aikosh_present
                else "Manual GEE export is likely required from this environment unless direct GeoJSON URLs are found."
            ),
            "boundary_download_automatic_possible": False,
            "boundary_download_recommended_path": "Treat Survey of India/India Maps as manual/portal-mediated until access, license, and download flow are reviewed. OGD can be probed separately if an API/zip URL is confirmed.",
        },
        "next_actions": [
            "If you have Earth Engine access, authenticate/configure earthengine CLI and export the three FeatureCollections.",
            "If Aikosh exposes direct dataset files, capture dataset/file identifiers before attempting scripted download.",
            "For Survey of India/India Maps, use the portal manually unless a reviewed direct download URL is available.",
            "Place CoRE GeoJSON exports under data/staged/core_stack/exports/.",
            "Place reviewed boundary candidates under data/staged/boundaries/.",
            "Rerun backend/scripts/validate_core_lgd_overlay_inputs.py after staging files.",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
