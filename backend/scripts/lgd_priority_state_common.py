#!/usr/bin/env python3
"""Shared deterministic helpers for priority-state LGD reconciliation."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]

RAW_VILLAGE_DIR = (
    ROOT
    / "data/raw/lgd_national_villages/20260925/downloads"
)
RAW_HIERARCHY_DIR = (
    ROOT
    / "data/raw/lgd_national_geography/20260925/downloads"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data/staged/core_stack/promotion_review"
    / "20260925-lgd-priority-state-reconciliation-v1"
)

PRIORITY_STATE_CODES = {
    "1", "2", "3", "5", "6", "7", "8", "37",
}

EXPECTED_SOURCE_HASHES = {
    "01_jammu_and_kashmir.csv":
        "51d46f2545d4492a884d3a97f79591df7917430989781182a6bdad5ab1a62606",
    "02_himachal_pradesh.csv":
        "38bd6b5beda7a8b3edc2557087a07ea0b75db85a66ee61273a98dbd5bdf6a54e",
    "03_punjab.csv":
        "4ebaf2bb94303cb269ca14947d9f67cb2ec96d6a9305ca368e3fb78683f30d4c",
    "05_uttarakhand.csv":
        "f8e1d778cd1b3437259dee7bf9188c6acd2c2875b6f1ebfa769ecb2e895d5ea1",
    "06_haryana.csv":
        "06859ea234aca7747355d800b60fd0e171e8cbf3594dbe734320e8200338341c",
    "07_delhi.csv":
        "645fbb3f5922c58e31c52354af88540289a73b194568c4c5e0a22095187dbefd",
    "08_rajasthan.csv":
        "92ef187d08c7111f94d4311be5bdd382cbc4bfe2f8b90aeba1383a9c68150878",
    "37_ladakh.csv":
        "1fcc5bf7e61330f892d8ce73817042126e196c21c595082f23dcaa4e02e38a25",
    "all_india_districts.csv":
        "b8901c98350a4057d3371ce14228181e4bb12cc447f847490efee599a0e38b59",
    "all_india_subdistricts.csv":
        "a5ffe900bea3c802b698a7a8c7a7125acffc273daa7c6e05482be83c4162c9e5",
}

EXPECTED_CURRENT_VILLAGE_ROWS = 119_490


def normalize_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(text))
    except ValueError:
        return text


def parse_date(value: str) -> tuple[int, int, int]:
    text = str(value or "").strip()
    for pattern in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(text, pattern)
            return parsed.year, parsed.month, parsed.day
        except ValueError:
            continue
    raise ValueError(f"INVALID_UPDATE_DATE:{text}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_checksum(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_write_jsonl(
    path: Path,
    rows: Iterable[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".writing")
    with temporary.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ) + "\n"
            )
    temporary.replace(path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return [
            dict(row)
            for row in csv.DictReader(handle)
        ]


def pick(row: dict[str, str], *names: str) -> str:
    lower = {
        key.lower(): value
        for key, value in row.items()
    }
    for name in names:
        if name in row:
            return str(row[name] or "").strip()
        if name.lower() in lower:
            return str(lower[name.lower()] or "").strip()
    return ""


def validate_source(
    path: Path,
    expected_name: str | None = None,
) -> str:
    name = expected_name or path.name
    expected = EXPECTED_SOURCE_HASHES.get(name)
    if expected is None:
        raise ValueError(f"UNPINNED_SOURCE:{name}")
    if not path.is_file():
        raise ValueError(f"SOURCE_NOT_FOUND:{path}")

    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"SOURCE_HASH_MISMATCH:{name}:{actual}:{expected}"
        )
    return actual


def load_current_villages(
    directory: Path = RAW_VILLAGE_DIR,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    selected: dict[
        tuple[str, str],
        dict[str, str],
    ] = {}
    pins: dict[str, str] = {}

    paths = sorted(directory.glob("*.csv"))
    if len(paths) != 8:
        raise ValueError(
            f"EXPECTED_EIGHT_STATE_FILES:{len(paths)}"
        )

    for path in paths:
        pins[path.name] = validate_source(path)

        for raw in read_csv(path):
            state_code = normalize_code(
                pick(raw, "stateCode", "state_code")
            )
            village_code = normalize_code(
                pick(raw, "villageCode", "village_code")
            )
            if (
                state_code not in PRIORITY_STATE_CODES
                or not village_code
            ):
                continue

            row = {
                "state_code": state_code,
                "state_name": pick(
                    raw,
                    "stateNameEnglish",
                    "state_name_english",
                ),
                "district_code": normalize_code(
                    pick(raw, "districtCode", "district_code")
                ),
                "district_name": pick(
                    raw,
                    "districtNameEnglish",
                    "district_name_english",
                ),
                "subdistrict_code": normalize_code(
                    pick(
                        raw,
                        "subdistrictCode",
                        "subdistrict_code",
                    )
                ),
                "subdistrict_name": pick(
                    raw,
                    "subdistrictNameEnglish",
                    "subdistrict_name_english",
                ),
                "village_code": village_code,
                "village_name": pick(
                    raw,
                    "villageNameEnglish",
                    "village_name_english",
                ),
                "village_census_2011_code": normalize_code(
                    pick(
                        raw,
                        "villageCensus2011Code",
                        "village_census2011_code",
                    )
                ),
                "data_gov_update_date": pick(
                    raw,
                    "data_gov_update_date",
                    "last_updated",
                ),
            }

            identity = (state_code, village_code)
            existing = selected.get(identity)

            if existing is None:
                selected[identity] = row
                continue

            row_date = parse_date(
                row["data_gov_update_date"]
            )
            existing_date = parse_date(
                existing["data_gov_update_date"]
            )

            if row_date > existing_date:
                selected[identity] = row
            elif row_date == existing_date and row != existing:
                raise ValueError(
                    "LATEST_DATE_IDENTITY_CONFLICT:"
                    f"{state_code}:{village_code}"
                )

    rows = sorted(
        selected.values(),
        key=lambda row: (
            int(row["state_code"]),
            int(row["village_code"]),
        ),
    )

    if len(rows) != EXPECTED_CURRENT_VILLAGE_ROWS:
        raise ValueError(
            "CURRENT_VILLAGE_ROW_COUNT_MISMATCH:"
            f"{len(rows)}:"
            f"{EXPECTED_CURRENT_VILLAGE_ROWS}"
        )

    return rows, pins


def load_authoritative_hierarchy(
    directory: Path = RAW_HIERARCHY_DIR,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
    dict[str, str],
]:
    district_path = directory / "all_india_districts.csv"
    subdistrict_path = (
        directory / "all_india_subdistricts.csv"
    )

    pins = {
        district_path.name: validate_source(district_path),
        subdistrict_path.name: validate_source(
            subdistrict_path
        ),
    }

    districts: dict[str, dict[str, str]] = {}
    for raw in read_csv(district_path):
        code = normalize_code(
            pick(raw, "district_code")
        )
        if not code:
            raise ValueError(
                "EMPTY_AUTHORITATIVE_DISTRICT_CODE"
            )
        if code in districts:
            raise ValueError(
                f"DUPLICATE_AUTHORITATIVE_DISTRICT:{code}"
            )
        districts[code] = {
            "state_code": normalize_code(
                pick(raw, "state_code")
            ),
            "district_code": code,
            "district_name": pick(
                raw,
                "district_name_english",
            ),
            "district_census_2011_code": normalize_code(
                pick(raw, "district_census2011_code")
            ),
        }

    subdistricts: dict[str, dict[str, str]] = {}
    for raw in read_csv(subdistrict_path):
        code = normalize_code(
            pick(raw, "subdistrict_code")
        )
        if not code:
            raise ValueError(
                "EMPTY_AUTHORITATIVE_SUBDISTRICT_CODE"
            )
        if code in subdistricts:
            raise ValueError(
                f"DUPLICATE_AUTHORITATIVE_SUBDISTRICT:{code}"
            )

        district_code = normalize_code(
            pick(raw, "district_code")
        )
        district = districts.get(district_code)
        if district is None:
            raise ValueError(
                "AUTHORITATIVE_SUBDISTRICT_DISTRICT_MISSING:"
                f"{code}:{district_code}"
            )

        state_code = normalize_code(
            pick(raw, "state_code")
        )
        if district["state_code"] != state_code:
            raise ValueError(
                "AUTHORITATIVE_HIERARCHY_STATE_MISMATCH:"
                f"{code}:{state_code}:"
                f"{district['state_code']}"
            )

        subdistricts[code] = {
            "state_code": state_code,
            "district_code": district_code,
            "subdistrict_code": code,
            "subdistrict_name": pick(
                raw,
                "subdistrict_name_english",
            ),
            "subdistrict_census_2011_code":
                normalize_code(
                    pick(
                        raw,
                        "subdistrict_census2011_code",
                    )
                ),
        }

    return districts, subdistricts, pins
