"""Inspect and extract the LGD zip file downloaded from lgdirectory.gov.in.

Usage:
    cd backend
    source ../venv/bin/activate
    python scripts/acquire_master_data/inspect_and_extract_zip.py
"""

import sys
import csv
import zipfile
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
ZIP_FILE = DATA_DIR / "downloadDir2026_05_22_17_30_28_683.zip"
RAW_DIR = DATA_DIR / "raw" / "lgd"
RAW_DIR.mkdir(parents=True, exist_ok=True)

if not ZIP_FILE.exists():
    print(f"ERROR: {ZIP_FILE} not found")
    sys.exit(1)

print(f"Zip file: {ZIP_FILE}")
print(f"Size: {ZIP_FILE.stat().st_size / 1024 / 1024:.1f} MB")
print()

# List contents
with zipfile.ZipFile(ZIP_FILE) as z:
    print(f"Files in archive ({len(z.infolist())}):")
    for info in z.infolist():
        print(f"  {info.filename} ({info.file_size / 1024:.1f} KB)")

    # Extract all files
    print(f"\nExtracting to: {RAW_DIR}")
    z.extractall(RAW_DIR)
    print("Done extracting.")

# Now inspect the extracted files
print("\n--- Inspecting extracted files ---")
for f in sorted(RAW_DIR.iterdir()):
    if f.is_file() and f.suffix in (".csv", ".txt", ".xls", ".xlsx"):
        print(f"\nFile: {f.name} ({f.stat().st_size / 1024:.1f} KB)")
        # Try to read first few lines
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()[:5]
                for line in lines:
                    print(f"  {line.rstrip()[:150]}")
                print(f"  ... ({len(open(f, 'r', encoding='utf-8', errors='replace').readlines())} total lines)")
        except Exception as e:
            print(f"  Could not read: {e}")
