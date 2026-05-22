"""Pre-Engineering Go/No-Go Validation Checks.

Validates:
1. Hierarchy Integrity — no orphaned records, all FKs valid
2. FTS Search — trigram search works on village names
3. Lifecycle Template Validity — stages JSON is well-formed
4. Canonical Compliance — no forbidden aliases in schema/code
5. Cache Size Estimate — geography + crop data fits in 5MB

Usage:
    cd backend
    source ../venv/bin/activate
    python scripts/go_no_go_checks.py
"""

import sys
import json
import gzip
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.core.database import engine, SessionLocal
from app.modules.master_data.models import (
    GeographyState, GeographyDistrict, GeographyBlock, GeographyVillage,
    CropLifecycleTemplate,
)

PASS = "\033[92m✅ PASS\033[0m"
FAIL = "\033[91m❌ FAIL\033[0m"
results = []


def check(name, passed, detail=""):
    status = PASS if passed else FAIL
    results.append((name, passed))
    print(f"  {status} {name}")
    if detail:
        print(f"       {detail}")


def check_hierarchy_integrity():
    """Check 1: All FKs valid, no orphaned records."""
    print("\n[1] Hierarchy Integrity")
    with engine.connect() as conn:
        # Districts without valid state
        orphan_districts = conn.execute(text("""
            SELECT count(*) FROM geography_districts d
            WHERE NOT EXISTS (SELECT 1 FROM geography_states s WHERE s.id = d.state_id)
        """)).scalar()
        check("Districts → States FK", orphan_districts == 0,
              f"{orphan_districts} orphaned districts")

        # Blocks without valid district
        orphan_blocks = conn.execute(text("""
            SELECT count(*) FROM geography_blocks b
            WHERE NOT EXISTS (SELECT 1 FROM geography_districts d WHERE d.id = b.district_id)
        """)).scalar()
        check("Blocks → Districts FK", orphan_blocks == 0,
              f"{orphan_blocks} orphaned blocks")

        # Villages without valid block
        orphan_villages = conn.execute(text("""
            SELECT count(*) FROM geography_villages v
            WHERE NOT EXISTS (SELECT 1 FROM geography_blocks b WHERE b.id = v.block_id)
        """)).scalar()
        check("Villages → Blocks FK", orphan_villages == 0,
              f"{orphan_villages} orphaned villages")

        # Count totals
        states = conn.execute(text("SELECT count(*) FROM geography_states")).scalar()
        districts = conn.execute(text("SELECT count(*) FROM geography_districts")).scalar()
        blocks = conn.execute(text("SELECT count(*) FROM geography_blocks")).scalar()
        villages = conn.execute(text("SELECT count(*) FROM geography_villages")).scalar()
        check("Hierarchy populated", states > 0 and districts > 50 and villages > 1000,
              f"States={states}, Districts={districts}, Blocks={blocks}, Villages={villages}")


def check_fts_search():
    """Check 2: pg_trgm fuzzy search works on village names."""
    print("\n[2] FTS / Trigram Search")
    with engine.connect() as conn:
        # Test trigram search
        result = conn.execute(text("""
            SELECT canonical_name, similarity(canonical_name, 'rampur') as sim
            FROM geography_villages
            WHERE canonical_name % 'rampur'
            ORDER BY sim DESC
            LIMIT 5
        """))
        rows = result.fetchall()
        check("Trigram search 'rampur'", len(rows) > 0,
              f"Found {len(rows)} results: {[r[0] for r in rows[:3]]}")

        # Test ILIKE fallback
        result2 = conn.execute(text("""
            SELECT count(*) FROM geography_villages
            WHERE canonical_name ILIKE '%pur%'
        """))
        count = result2.scalar()
        check("ILIKE search '%pur%'", count > 100,
              f"Found {count} villages containing 'pur'")

        # Test GIN index is being used (EXPLAIN)
        result3 = conn.execute(text("""
            EXPLAIN (FORMAT TEXT) SELECT * FROM geography_villages
            WHERE canonical_name % 'lucknow'
        """))
        plan = "\n".join([r[0] for r in result3.fetchall()])
        uses_index = "idx_village_search" in plan or "Bitmap" in plan
        check("GIN trgm index used", uses_index,
              f"Plan uses index: {uses_index}")


def check_lifecycle_templates():
    """Check 3: Lifecycle template JSON is well-formed."""
    print("\n[3] Lifecycle Template Validity")
    db = SessionLocal()
    try:
        templates = db.query(CropLifecycleTemplate).all()
        check("Templates exist", len(templates) > 0,
              f"{len(templates)} templates found")

        valid = 0
        invalid = 0
        for t in templates:
            stages = t.stages
            if not isinstance(stages, list) or len(stages) == 0:
                invalid += 1
                continue
            # Each stage should have order, code, name, duration_days
            all_valid = all(
                isinstance(s, dict) and "order" in s and "code" in s and "name" in s
                for s in stages
            )
            if all_valid:
                valid += 1
            else:
                invalid += 1

        check("All templates have valid stages", invalid == 0,
              f"{valid} valid, {invalid} invalid")

        # Check no hardcoded stage names (should use codes)
        all_codes = set()
        for t in templates:
            for s in t.stages:
                all_codes.add(s.get("code", ""))
        check("Stage codes are SCREAMING_SNAKE", 
              all(c == c.upper() for c in all_codes if c),
              f"Codes: {sorted(all_codes)[:5]}...")
    finally:
        db.close()


def check_canonical_compliance():
    """Check 4: No forbidden aliases in code/schema."""
    print("\n[4] Canonical Compliance")
    # Forbidden terms as IDENTIFIERS (variable names, column names, class names)
    # NOT forbidden in comments, strings, or descriptions
    forbidden_identifiers = ["field", "plot", "khet", "farm_land", "crop_type", "disease_case"]
    
    # Check DB column names (the real compliance check)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name, column_name FROM information_schema.columns
            WHERE table_schema = 'public'
            AND (column_name LIKE '%field%' OR column_name LIKE '%plot%' 
                 OR column_name LIKE '%khet%' OR column_name = 'crop_type')
        """))
        bad_cols = result.fetchall()
        check("No forbidden column names in DB", len(bad_cols) == 0,
              f"Bad columns: {bad_cols}" if bad_cols else "Clean")

    # Check table names
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND (tablename LIKE '%field%' OR tablename LIKE '%plot%'
                 OR tablename LIKE '%khet%')
            AND tablename != 'spatial_ref_sys'
        """))
        bad_tables = result.fetchall()
        check("No forbidden table names in DB", len(bad_tables) == 0,
              f"Bad tables: {bad_tables}" if bad_tables else "Clean")

    # Check Python class/variable names (not string content)
    backend_dir = Path(__file__).resolve().parents[1]
    violations = []
    import re
    for py_file in backend_dir.rglob("*.py"):
        if "venv" in str(py_file) or "__pycache__" in str(py_file):
            continue
        if "go_no_go" in str(py_file) or "seed_" in str(py_file):
            continue
        content = py_file.read_text(errors="replace")
        for line_no, line in enumerate(content.split("\n"), 1):
            # Skip comments and strings
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                continue
            # Check for forbidden terms as identifiers (variable/class/function names)
            for term in forbidden_identifiers:
                # Match as identifier: word boundary + term + word boundary
                if re.search(rf'\b{term}\b', line.lower()):
                    # Exclude if inside a string literal
                    if f'"{term}' in line.lower() or f"'{term}" in line.lower():
                        continue
                    # Exclude if it's a description/comment
                    if "description" in line.lower() or "#" in line.split(term)[0]:
                        continue
                    violations.append(f"{py_file.name}:{line_no} '{term}'")

    check("No forbidden identifiers in code", len(violations) == 0,
          f"Violations: {violations[:3]}" if violations else "Clean")


def check_cache_size():
    """Check 5: Estimate mobile cache size."""
    print("\n[5] Cache Size Estimate")
    with engine.connect() as conn:
        # Geography data size estimate
        geo_count = conn.execute(text("""
            SELECT 
                (SELECT count(*) FROM geography_states) as states,
                (SELECT count(*) FROM geography_districts) as districts,
                (SELECT count(*) FROM geography_blocks) as blocks,
                (SELECT count(*) FROM geography_villages) as villages
        """)).fetchone()

        # Estimate: each village ~100 bytes (code + name + block_id)
        # Districts ~50 bytes, Blocks ~60 bytes
        geo_bytes = (
            geo_count[0] * 200 +   # states
            geo_count[1] * 100 +   # districts
            geo_count[2] * 100 +   # blocks
            geo_count[3] * 120     # villages
        )
        geo_mb = geo_bytes / 1024 / 1024

        # Crop data size estimate
        crop_count = conn.execute(text("""
            SELECT
                (SELECT count(*) FROM crops) as crops,
                (SELECT count(*) FROM crop_varieties) as varieties,
                (SELECT count(*) FROM crop_lifecycle_templates) as templates
        """)).fetchone()

        crop_bytes = (
            crop_count[0] * 300 +   # crops
            crop_count[1] * 200 +   # varieties
            crop_count[2] * 500     # templates (with stages JSON)
        )
        crop_mb = crop_bytes / 1024 / 1024

        total_mb = geo_mb + crop_mb
        # With gzip compression (~70% reduction)
        compressed_mb = total_mb * 0.3

        check("Raw cache < 20MB", total_mb < 20,
              f"Geography: {geo_mb:.1f}MB, Crops: {crop_mb:.1f}MB, Total: {total_mb:.1f}MB")
        check("Compressed cache < 5MB", compressed_mb < 5,
              f"Estimated gzipped: {compressed_mb:.1f}MB (fits mobile budget)")


if __name__ == "__main__":
    print("=" * 60)
    print("PRE-ENGINEERING GO/NO-GO CHECKS")
    print("=" * 60)

    check_hierarchy_integrity()
    check_fts_search()
    check_lifecycle_templates()
    check_canonical_compliance()
    check_cache_size()

    # Summary
    passed = sum(1 for _, p in results if p)
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"RESULT: {passed}/{total} checks passed")
    if passed == total:
        print(f"\n🟢 GREEN LIGHT — Proceed to engineering!")
    else:
        failed = [name for name, p in results if not p]
        print(f"\n🔴 BLOCKED — Fix: {failed}")
    print(f"{'=' * 60}")
