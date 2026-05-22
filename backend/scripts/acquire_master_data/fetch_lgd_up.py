"""LGD Data Acquisition: Uttar Pradesh

AUTHORITATIVE SOURCE: https://lgdirectory.gov.in
This is the official Local Government Directory maintained by
the Ministry of Panchayati Raj, Government of India.

DO NOT use GitHub repos, random CSVs, or scraped data.
LGD is updated when administrative units change (new districts,
block reorganization, village mergers, etc.).

DOWNLOAD INSTRUCTIONS:
1. Go to https://lgdirectory.gov.in
2. Navigate to: Reports → Download Directory
3. Select State: Uttar Pradesh
4. Download at each level:
   - District list (all districts in UP)
   - Block/Sub-district list (all blocks in UP)
   - Village list (all villages in UP)
5. Save downloaded files to: data/raw/lgd/
6. Run: python scripts/acquire_master_data/load_geography_up.py

EXPECTED FILES (place in data/raw/lgd/):
- up_districts.csv (or .xlsx)
- up_blocks.csv (or .xlsx)
- up_villages.csv (or .xlsx)

The loader script (load_geography_up.py) will auto-detect column
names from LGD format and map them to our schema.

COLUMN MAPPING (typical LGD format):
  LGD Column              → Our Column
  ─────────────────────────────────────
  State Code              → (filter only, not stored)
  District Code           → lgd_code (for districts)
  District Name (English) → canonical_name
  Block Code              → lgd_code (for blocks)
  Block Name (English)    → canonical_name
  Village Code            → lgd_code (for villages)
  Village Name (English)  → canonical_name
  Village Name (Local)    → aliases[0]
  PIN Code                → pin_codes

IDEMPOTENT: Re-running the loader with updated LGD data will:
- Skip existing records (matched by lgd_code)
- Use --reset flag to clear and reload all data
"""

import sys
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "lgd"


if __name__ == "__main__":
    print("=" * 60)
    print("LGD Data Acquisition: Uttar Pradesh")
    print("=" * 60)
    print()
    print("This script documents the data acquisition process.")
    print("LGD data must be downloaded manually from the official source.")
    print()
    print("Source: https://lgdirectory.gov.in")
    print(f"Target: {RAW_DIR}/")
    print()
    print("Steps:")
    print("  1. Download district/block/village data from LGD website")
    print("  2. Save files to data/raw/lgd/ as CSV or Excel")
    print("  3. Run: python scripts/acquire_master_data/load_geography_up.py")
    print()

    # Check if files exist
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    found = list(RAW_DIR.glob("*"))
    if found:
        print("Files found in data/raw/lgd/:")
        for f in sorted(found):
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name} ({size_kb:.1f} KB)")
        print()
        print("Ready to load. Run:")
        print("  python scripts/acquire_master_data/load_geography_up.py --reset")
    else:
        print("No files found yet. Please download from LGD.")
        print()
        print("Quick test with minimal data:")
        print("  python scripts/acquire_master_data/load_geography_up.py")
        print("  (will use whatever CSV files are available)")
