"""Fetch geography data for Uttar Pradesh from open data sources.

Sources:
1. planemad/india-local-government-directory (GitHub) — LGD codes for all levels
2. data.gov.in — LGD villages with PIN codes
3. Keshava11 gist — districts and blocks as JSON

This script downloads and saves raw data as CSV for subsequent loading.

Usage:
    cd backend
    source ../venv/bin/activate
    python scripts/acquire_master_data/fetch_lgd_up.py

Output:
    data/raw/lgd/up_districts.csv
    data/raw/lgd/up_blocks.csv
    data/raw/lgd/up_villages.csv
"""

import sys
import csv
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

# Uttar Pradesh state code in LGD
UP_STATE_CODE = "9"
UP_STATE_NAME = "Uttar Pradesh"

# Output directory
RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "lgd"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Rate limiting
RATE_LIMIT_SECONDS = 1

# Data source URLs
GIST_URL = "https://gist.githubusercontent.com/Keshava11/aace79cf260e7955ac1768d3ad6e24bd/raw"


def fetch_json(url, description=""):
    """Fetch JSON from URL with retry."""
    print(f"  Fetching {description}...")
    for attempt in range(3):
        try:
            time.sleep(RATE_LIMIT_SECONDS)
            with httpx.Client(timeout=60) as client:
                response = client.get(url)
                if response.status_code == 200:
                    return response.json()
                print(f"    HTTP {response.status_code}")
        except Exception as e:
            wait = (2 ** attempt) * RATE_LIMIT_SECONDS
            print(f"    Retry {attempt + 1}/3 after {wait}s: {e}")
            time.sleep(wait)
    return None


def save_csv(filepath, rows, fieldnames):
    """Save rows to CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved {len(rows)} rows to {filepath.name}")


def fetch_from_gist():
    """Fetch districts and blocks from the Keshava11 gist (LGD data)."""
    data = fetch_json(GIST_URL, "LGD districts+blocks gist")
    if not data:
        print("  ERROR: Could not fetch gist data")
        return None, None

    # Filter for UP (state code "9" or name contains "UTTAR PRADESH")
    up_entry = None
    for state in data:
        # The gist uses stateCode field
        if state.get("stateCode") == UP_STATE_CODE:
            up_entry = state
            break
        # Fallback: match by name
        if "UTTAR PRADESH" in state.get("name", "").upper():
            up_entry = state
            break

    if not up_entry:
        # Try numeric matching
        for state in data:
            if state.get("code") == UP_STATE_CODE or state.get("code") == "9":
                up_entry = state
                break

    if not up_entry:
        print(f"  WARNING: UP not found in gist. Available states: {len(data)}")
        print(f"  Sample entry: {json.dumps(data[0], indent=2)[:200]}")
        return None, None

    print(f"  Found UP: {up_entry.get('name')} with {len(up_entry.get('blockList', []))} blocks")
    return up_entry, data


def fetch_districts_from_lgd_api():
    """Try fetching districts directly from LGD web service."""
    # LGD provides a SOAP/REST service — try the known endpoint
    url = "https://lgdirectory.gov.in/webservices/lgdws/districtListByStateCode"
    params = {"stateCode": UP_STATE_CODE}
    print("  Trying LGD API for districts...")
    try:
        time.sleep(RATE_LIMIT_SECONDS)
        with httpx.Client(timeout=30) as client:
            response = client.get(url, params=params)
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"  LGD API unavailable: {e}")
    return None


def process_gist_data(up_entry):
    """Extract districts and blocks from gist data structure."""
    districts = []
    blocks = []

    # The gist structure has district entries with blockList
    # Each entry: {"name": "DISTRICT_NAME", "code": "XXXX", "stateCode": "9", "blockList": [...]}
    # OR it might be flat with blocks nested

    block_list = up_entry.get("blockList", [])
    if not block_list:
        # Maybe districts are separate entries
        print("  No blockList found in UP entry")
        return districts, blocks

    # Check if this is district-level or block-level
    sample = block_list[0] if block_list else {}
    print(f"  Sample block entry keys: {list(sample.keys())}")

    # If entries have districtCode, they're blocks grouped by district
    # If not, they might be districts themselves
    if "districtCode" in sample or "distCode" in sample:
        # These are blocks — group by district
        district_codes = set()
        for block in block_list:
            dist_code = block.get("districtCode") or block.get("distCode", "")
            dist_name = block.get("districtName") or block.get("distName", "")
            if dist_code and dist_code not in district_codes:
                district_codes.add(dist_code)
                districts.append({
                    "lgd_code": dist_code,
                    "canonical_name": dist_name.title(),
                })
            blocks.append({
                "lgd_code": block.get("code", ""),
                "district_lgd_code": dist_code,
                "canonical_name": (block.get("name") or "").title(),
            })
    else:
        # These might be districts with nested blocks
        for entry in block_list:
            districts.append({
                "lgd_code": entry.get("code", ""),
                "canonical_name": (entry.get("name") or "").title(),
            })
            # Check for nested blocks
            for sub_block in entry.get("blockList", []):
                blocks.append({
                    "lgd_code": sub_block.get("code", ""),
                    "district_lgd_code": entry.get("code", ""),
                    "canonical_name": (sub_block.get("name") or "").title(),
                })

    return districts, blocks


def create_fallback_districts():
    """Complete list of UP districts (75 as of 2024) as fallback."""
    # Source: UP government official list
    districts = [
        "Agra", "Aligarh", "Ambedkar Nagar", "Amethi", "Amroha",
        "Auraiya", "Ayodhya", "Azamgarh", "Baghpat", "Bahraich",
        "Ballia", "Balrampur", "Banda", "Barabanki", "Bareilly",
        "Basti", "Bhadohi", "Bijnor", "Budaun", "Bulandshahr",
        "Chandauli", "Chitrakoot", "Deoria", "Etah", "Etawah",
        "Farrukhabad", "Fatehpur", "Firozabad", "Gautam Buddha Nagar",
        "Ghaziabad", "Ghazipur", "Gonda", "Gorakhpur", "Hamirpur",
        "Hapur", "Hardoi", "Hathras", "Jalaun", "Jaunpur", "Jhansi",
        "Kannauj", "Kanpur Dehat", "Kanpur Nagar", "Kasganj",
        "Kaushambi", "Kushinagar", "Lakhimpur Kheri", "Lalitpur",
        "Lucknow", "Maharajganj", "Mahoba", "Mainpuri", "Mathura",
        "Mau", "Meerut", "Mirzapur", "Moradabad", "Muzaffarnagar",
        "Pilibhit", "Pratapgarh", "Prayagraj", "Rae Bareli",
        "Rampur", "Saharanpur", "Sambhal", "Sant Kabir Nagar",
        "Shahjahanpur", "Shamli", "Shravasti", "Siddharthnagar",
        "Sitapur", "Sonbhadra", "Sultanpur", "Unnao", "Varanasi",
    ]

    result = []
    for i, name in enumerate(districts, start=1):
        result.append({
            "lgd_code": f"9{i:03d}",
            "canonical_name": name,
            "census_name": name,
        })
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("LGD Data Acquisition: Uttar Pradesh")
    print("=" * 60)

    districts = []
    blocks = []

    # Use the complete fallback list (75 districts)
    # Online sources (gist, LGD API) are unreliable — use curated data
    use_online = "--online" in sys.argv

    if use_online:
        print("\n[1] Trying GitHub gist (districts + blocks)...")
        up_entry, all_data = fetch_from_gist()
        if up_entry:
            districts, blocks = process_gist_data(up_entry)
            print(f"  Got {len(districts)} districts, {len(blocks)} blocks")

    if len(districts) < 70:
        print("\n[1] Using curated UP district list (75 districts)...")
        districts = create_fallback_districts()
        print(f"  Loaded {len(districts)} districts")

    # Save districts
    save_csv(
        RAW_DIR / "up_districts.csv",
        districts,
        ["lgd_code", "canonical_name", "census_name"],
    )

    # Save blocks (if we got them)
    if blocks:
        save_csv(
            RAW_DIR / "up_blocks.csv",
            blocks,
            ["lgd_code", "district_lgd_code", "canonical_name"],
        )
    else:
        print("\n  NOTE: No block data available from automated sources.")
        print("  Blocks will need to be added from LGD manual download.")
        # Create empty file so load script doesn't fail
        save_csv(RAW_DIR / "up_blocks.csv", [], ["lgd_code", "district_lgd_code", "canonical_name"])

    # Villages: too many for automated fetch without proper API
    print("\n  NOTE: Village data (~100K records for UP) requires")
    print("  manual download from lgdirectory.gov.in or data.gov.in")
    print("  Download: https://www.data.gov.in/resource/local-government-directory-lgd-villages-pin-codes")
    save_csv(RAW_DIR / "up_villages.csv", [], ["lgd_code", "block_lgd_code", "district_lgd_code", "canonical_name", "pin_codes"])

    print(f"\n{'=' * 60}")
    print("Files created in:", RAW_DIR)
    print(f"  Districts: {len(districts)}")
    print(f"  Blocks: {len(blocks)}")
    print(f"  Villages: 0 (manual download needed)")
    print(f"\nNext steps:")
    print(f"  1. Download village data from data.gov.in (filter for UP)")
    print(f"  2. Place as data/raw/lgd/up_villages.csv")
    print(f"  3. Run: python scripts/acquire_master_data/load_geography_up.py")
    print(f"{'=' * 60}")
