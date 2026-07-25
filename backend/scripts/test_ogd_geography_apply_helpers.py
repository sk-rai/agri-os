#!/usr/bin/env python3
"""Regression checks for OGD geography apply loader helpers."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.apply_ogd_geography_snapshot import add_alias, dedupe_lgd, dedupe_postal, normalize_name_for_search


class Obj:
    def __init__(self, canonical_name, aliases=None):
        self.canonical_name = canonical_name
        self.aliases = aliases if aliases is not None else []


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


def main() -> int:
    print("=" * 72)
    print("OGD GEOGRAPHY APPLY HELPER REGRESSION")
    print("=" * 72)

    check(normalize_name_for_search("Lal-Bahadur   Nagar") == "lal bahadur nagar", "Name normalization handles hyphen and spacing")

    obj = Obj("Lal Bahadur Nagar")
    changed = add_alias(obj, "Lalbahadur Nagar", source_system="TEST", field="name")
    check(changed, "Variant spelling added as alias")
    check("Lalbahadur Nagar" in obj.aliases["en"], "English alias stored")
    check("lalbahadurnagar" in obj.aliases["normalized_tokens"], "Collapsed token stored for search")

    changed_again = add_alias(obj, "Lalbahadur Nagar", source_system="TEST", field="name")
    check(not changed_again, "Duplicate alias is idempotent")

    local_obj = Obj("Karaikal")
    changed_local = add_alias(local_obj, "கரைக்கால்", source_system="TEST", field="name_local", lang="ta")
    check(changed_local, "Local-language alias can be stored")
    check("கரைக்கால்" in local_obj.aliases["ta"], "Tamil alias stored under locale key")

    lgd_rows = [
        {"state_lgd_code": "1", "district_lgd_code": "10", "subdistrict_lgd_code": "100", "village_lgd_code": "1000", "pin_code": "560001", "village_name": "Village A"},
        {"state_lgd_code": "1", "district_lgd_code": "10", "subdistrict_lgd_code": "100", "village_lgd_code": "1000", "pin_code": "560001", "village_name": "Village A"},
        {"state_lgd_code": "1", "district_lgd_code": "10", "subdistrict_lgd_code": "100", "village_lgd_code": "1000", "pin_code": "560002", "village_name": "Village A"},
    ]
    deduped_lgd, lgd_meta = dedupe_lgd(lgd_rows)
    check(len(deduped_lgd) == 2, "LGD village-PIN rows dedupe by full context plus PIN", lgd_meta)
    check(lgd_meta["duplicate_rows"] == 1, "LGD duplicate count reported")

    postal_rows = [
        {"pin_code": "560001", "office_name": "Office A", "office_type": "BO", "postal_state_name": "KARNATAKA", "postal_district_name": "Bengaluru"},
        {"pin_code": "560001", "office_name": "Office A", "office_type": "BO", "postal_state_name": "KARNATAKA", "postal_district_name": "Bengaluru"},
        {"pin_code": "560001", "office_name": "Office B", "office_type": "SO", "postal_state_name": "KARNATAKA", "postal_district_name": "Bengaluru"},
    ]
    deduped_postal, postal_meta = dedupe_postal(postal_rows)
    check(len(deduped_postal) == 2, "Postal rows dedupe by PIN and office context", postal_meta)
    check(postal_meta["duplicate_rows"] == 1, "Postal duplicate count reported")

    print("=" * 72)
    print("OGD geography apply helpers validated")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
