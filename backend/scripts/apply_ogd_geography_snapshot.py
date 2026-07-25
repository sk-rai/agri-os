#!/usr/bin/env python3
"""Dry-run/apply OGD all-India geography snapshot into modular geography tables.

Default is dry-run. Use --apply for writes.

The loader keeps LGD as canonical identity, stores postal references separately,
stores village-PIN links separately, and maintains geography_villages.pin_codes
as a compatibility cache for Android.

Refresh modes:
- INITIAL_FULL_LOAD: first source snapshot load.
- INCREMENTAL_REFRESH: upsert only; no expiry.
- ANNUAL_FULL_REFRESH: upsert plus optional --expire-missing.

Census remains a separate future enrichment layer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
import uuid
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.master_data.models import (
    GeographyBlock,
    GeographyDistrict,
    GeographyImportBatch,
    GeographyPostalReference,
    GeographyState,
    GeographyVillage,
    GeographyVillagePinLink,
)

VALID_REFRESH_MODES = {"INITIAL_FULL_LOAD", "INCREMENTAL_REFRESH", "ANNUAL_FULL_REFRESH"}
PIN_SOURCE_POSTAL = "OGD_ALL_INDIA_PINCODE_DIRECTORY"
PIN_SOURCE_LGD = "OGD_LGD_VILLAGES_PIN_CODES"


def now():
    return datetime.now(timezone.utc)


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def latest_staged_dir(root: Path) -> Path:
    dirs = sorted([p for p in root.glob("*") if p.is_dir()])
    if not dirs:
        raise SystemExit(f"No staged OGD geography directories found under {root}")
    return dirs[-1]


def decimal_or_none(value: Any):
    text = clean(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def normalize_name_for_search(name: str) -> str:
    return " ".join(clean(name).lower().replace("-", " ").split())


def alias_payload(existing: Any, *, lang: str = "en") -> dict[str, Any]:
    if isinstance(existing, dict):
        payload = dict(existing)
    elif isinstance(existing, list):
        payload = {lang: []}
        for item in existing:
            if isinstance(item, dict):
                item_lang = clean(item.get("lang") or item.get("locale") or lang) or lang
                item_name = clean(item.get("name") or item.get("value"))
                if item_name:
                    payload.setdefault(item_lang, []).append(item_name)
            elif clean(item):
                payload.setdefault(lang, []).append(clean(item))
    else:
        payload = {lang: []}

    payload.setdefault(lang, [])
    payload.setdefault("source_variants", [])
    payload.setdefault("normalized_tokens", [])
    return payload


def add_alias(entity, value: str, *, source_system: str, field: str, lang: str = "en") -> bool:
    value = clean(value)
    if not value:
        return False

    canonical = clean(getattr(entity, "canonical_name", ""))
    aliases = alias_payload(getattr(entity, "aliases", None), lang=lang)

    names = {normalize_name_for_search(canonical)}
    names.update(normalize_name_for_search(v) for v in aliases.get(lang, []) if clean(v))

    normalized = normalize_name_for_search(value)
    changed = False

    if normalized and normalized not in names:
        aliases.setdefault(lang, []).append(value)
        changed = True

    source_variant = {"source_system": source_system, "field": field, "value": value}
    if source_variant not in aliases.get("source_variants", []):
        aliases.setdefault("source_variants", []).append(source_variant)
        changed = True

    for token in {normalized, normalized.replace(" ", "")}:
        if token and token not in aliases.get("normalized_tokens", []):
            aliases.setdefault("normalized_tokens", []).append(token)
            changed = True

    if changed:
        entity.aliases = aliases
    return changed


def _variant_summary(variant_sets: dict[tuple[str, ...], set[str]], *, limit: int = 25) -> dict[str, Any]:
    variants = {key: sorted(values) for key, values in variant_sets.items() if len(values) > 1}
    return {
        "count": len(variants),
        "examples": [
            {"context": key, "names": values}
            for key, values in list(sorted(variants.items()))[:limit]
        ],
    }


def dedupe_lgd(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    duplicate_count = 0
    state_names: dict[tuple[str], set[str]] = defaultdict(set)
    district_names: dict[tuple[str, str], set[str]] = defaultdict(set)
    subdistrict_names: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    village_names: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)

    for row in rows:
        state_code = clean(row.get("state_lgd_code"))
        district_code = clean(row.get("district_lgd_code"))
        subdistrict_code = clean(row.get("subdistrict_lgd_code"))
        village_code = clean(row.get("village_lgd_code"))
        pin = clean(row.get("pin_code"))

        key = (state_code, district_code, subdistrict_code, village_code, pin)
        if not all(key):
            continue
        if key in by_key:
            duplicate_count += 1
        else:
            by_key[key] = row

        if clean(row.get("state_name")):
            state_names[(state_code,)].add(clean(row.get("state_name")))
        if clean(row.get("district_name")):
            district_names[(state_code, district_code)].add(clean(row.get("district_name")))
        if clean(row.get("subdistrict_name")):
            subdistrict_names[(state_code, district_code, subdistrict_code)].add(clean(row.get("subdistrict_name")))
        if clean(row.get("village_name")):
            village_names[(state_code, district_code, subdistrict_code, village_code)].add(clean(row.get("village_name")))

    variant_summary = {
        "states": _variant_summary(state_names),
        "districts": _variant_summary(district_names),
        "subdistricts": _variant_summary(subdistrict_names),
        "villages": _variant_summary(village_names),
    }

    return list(by_key.values()), {
        "input_rows": len(rows),
        "deduped_rows": len(by_key),
        "duplicate_rows": duplicate_count,
        "name_variant_context_count": sum(item["count"] for item in variant_summary.values()),
        "name_variant_summary": variant_summary,
    }


def postal_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        clean(row.get("pin_code")),
        clean(row.get("office_name")).upper(),
        clean(row.get("office_type")).upper(),
        clean(row.get("postal_state_name")).upper(),
        clean(row.get("postal_district_name")).upper(),
    )


def dedupe_postal(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    duplicate_count = 0
    for row in rows:
        key = postal_key(row)
        if not all(key[:2]):
            continue
        if key in by_key:
            duplicate_count += 1
        else:
            by_key[key] = row
    return list(by_key.values()), {
        "input_rows": len(rows),
        "deduped_rows": len(by_key),
        "duplicate_rows": duplicate_count,
    }


def load_inputs(staged_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    validation_path = staged_dir / "validation_report.json"
    lgd_path = staged_dir / "lgd_village_pin_links.jsonl"
    postal_path = staged_dir / "postal_references.jsonl"

    if not validation_path.exists():
        raise SystemExit(f"Missing {validation_path}")
    if not lgd_path.exists():
        raise SystemExit(f"Missing {lgd_path}")
    if not postal_path.exists():
        raise SystemExit(f"Missing {postal_path}")

    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    lgd_raw = list(read_jsonl(lgd_path))
    postal_raw = list(read_jsonl(postal_path))

    lgd, lgd_dedupe = dedupe_lgd(lgd_raw)
    postal, postal_dedupe = dedupe_postal(postal_raw)
    return lgd, postal, {"validation": validation, "lgd_dedupe": lgd_dedupe, "postal_dedupe": postal_dedupe}


def existing_context_maps(db):
    states = {str(row.lgd_code): row for row in db.query(GeographyState).all()}
    districts = {str(row.lgd_code): row for row in db.query(GeographyDistrict).all()}

    blocks = {}
    for block, district in db.query(GeographyBlock, GeographyDistrict).join(GeographyDistrict, GeographyDistrict.id == GeographyBlock.district_id).all():
        blocks[(str(district.lgd_code), str(block.lgd_code))] = block

    villages = {}
    for village, block, district in (
        db.query(GeographyVillage, GeographyBlock, GeographyDistrict)
        .join(GeographyBlock, GeographyBlock.id == GeographyVillage.block_id)
        .join(GeographyDistrict, GeographyDistrict.id == GeographyVillage.district_id)
        .all()
    ):
        villages[(str(district.lgd_code), str(block.lgd_code), str(village.lgd_code))] = village

    return states, districts, blocks, villages


def build_diff(db, lgd_rows: list[dict[str, Any]], postal_rows: list[dict[str, Any]]) -> dict[str, Any]:
    states, districts, blocks, villages = existing_context_maps(db)

    staged_states = {}
    staged_districts = {}
    staged_blocks = {}
    staged_villages = {}
    staged_links = set()

    for row in lgd_rows:
        state_code = clean(row.get("state_lgd_code"))
        district_code = clean(row.get("district_lgd_code"))
        block_code = clean(row.get("subdistrict_lgd_code"))
        village_code = clean(row.get("village_lgd_code"))
        pin = clean(row.get("pin_code"))

        staged_states[state_code] = clean(row.get("state_name"))
        staged_districts[district_code] = (state_code, clean(row.get("district_name")))
        staged_blocks[(district_code, block_code)] = clean(row.get("subdistrict_name"))
        staged_villages[(district_code, block_code, village_code)] = clean(row.get("village_name"))
        staged_links.add((state_code, district_code, block_code, village_code, pin))

    postal_keys = {postal_key(row) for row in postal_rows}

    db_postal_keys = {
        (
            clean(row.pin_code),
            clean(row.office_name).upper(),
            clean(row.office_type).upper(),
            clean(row.postal_state_name).upper(),
            clean(row.postal_district_name).upper(),
        )
        for row in db.query(GeographyPostalReference).filter(GeographyPostalReference.is_active == True).all()
    }
    db_link_keys = {
        (
            clean(row.state_lgd_code),
            clean(row.district_lgd_code),
            clean(row.subdistrict_lgd_code),
            clean(row.village_lgd_code),
            clean(row.pin_code),
        )
        for row in db.query(GeographyVillagePinLink).filter(GeographyVillagePinLink.is_active == True).all()
    }

    return {
        "states": {
            "staged": len(staged_states),
            "db_existing": len(states),
            "new": sum(1 for code in staged_states if code not in states),
        },
        "districts": {
            "staged": len(staged_districts),
            "db_existing": len(districts),
            "new": sum(1 for code in staged_districts if code not in districts),
        },
        "blocks": {
            "staged": len(staged_blocks),
            "db_existing": len(blocks),
            "new": sum(1 for key in staged_blocks if key not in blocks),
        },
        "villages": {
            "staged": len(staged_villages),
            "db_existing": len(villages),
            "new": sum(1 for key in staged_villages if key not in villages),
        },
        "postal_references": {
            "staged": len(postal_keys),
            "db_existing_active": len(db_postal_keys),
            "new": len(postal_keys - db_postal_keys),
            "missing_from_staged": len(db_postal_keys - postal_keys),
        },
        "village_pin_links": {
            "staged": len(staged_links),
            "db_existing_active": len(db_link_keys),
            "new": len(staged_links - db_link_keys),
            "missing_from_staged": len(db_link_keys - staged_links),
        },
    }


def get_or_create_batch(db, *, staged_dir: Path, validation: dict[str, Any], refresh_mode: str, apply: bool, actor_id: str | None, reason: str | None, diff_summary: dict[str, Any], row_counts: dict[str, int]):
    status = "APPLIED" if apply else "DRY_RUN"
    batch = GeographyImportBatch(
        id=uuid.uuid4(),
        source_system="OGD_GEOGRAPHY",
        source_resource_id="f17a1608-5f10-4610-bb50-a63c80d83974+5c2f62fe-5afa-4119-a499-fec9d604d5bd",
        source_label="OGD LGD Villages with PIN Codes + All India Pincode Directory",
        source_url="https://api.data.gov.in/resource",
        license="Government Open Data License - India",
        raw_manifest_path=validation.get("manifest"),
        validation_report_path=str(staged_dir / "validation_report.json"),
        refresh_mode=refresh_mode,
        status=status,
        snapshot_status=validation.get("snapshot_status"),
        retrieved_at=None,
        validated_at=now(),
        applied_at=now() if apply else None,
        actor_id=actor_id,
        reason=reason,
        row_counts=row_counts,
        checksums={},
        validation_summary={
            "schema_version": validation.get("schema_version"),
            "ready_for_apply_design": validation.get("ready_for_apply_design"),
            "pin_overlap": validation.get("pin_overlap"),
            "lgd": {
                "row_count": validation.get("lgd_villages_pin_codes", {}).get("row_count"),
                "invalid_pin_count": validation.get("lgd_villages_pin_codes", {}).get("invalid_pin_count"),
                "duplicate_village_pin_count": validation.get("lgd_villages_pin_codes", {}).get("duplicate_village_pin_count"),
            },
            "postal": {
                "row_count": validation.get("all_india_pincode_directory", {}).get("row_count"),
                "invalid_pin_count": validation.get("all_india_pincode_directory", {}).get("invalid_pin_count"),
                "duplicate_pin_office_count": validation.get("all_india_pincode_directory", {}).get("duplicate_pin_office_count"),
            },
        },
        diff_summary=diff_summary,
    )
    if apply:
        db.add(batch)
        db.flush()
    return batch


def apply_rows(db, *, batch, lgd_rows: list[dict[str, Any]], postal_rows: list[dict[str, Any]], refresh_mode: str, expire_missing: bool) -> dict[str, Any]:
    timestamp = now()
    counters = Counter()
    states, districts, blocks, villages = existing_context_maps(db)

    for row in lgd_rows:
        state_code = clean(row.get("state_lgd_code"))
        state_name = clean(row.get("state_name"))
        district_code = clean(row.get("district_lgd_code"))
        district_name = clean(row.get("district_name"))
        block_code = clean(row.get("subdistrict_lgd_code"))
        block_name = clean(row.get("subdistrict_name"))
        village_code = clean(row.get("village_lgd_code"))
        village_name = clean(row.get("village_name"))

        state = states.get(state_code)
        if not state:
            state = GeographyState(id=uuid.uuid4(), lgd_code=state_code, canonical_name=state_name, aliases=[], created_at=timestamp, updated_at=timestamp)
            db.add(state)
            db.flush()
            states[state_code] = state
            counters["states_created"] += 1
        else:
            if state_name and normalize_name_for_search(state_name) != normalize_name_for_search(state.canonical_name):
                if add_alias(state, state_name, source_system=PIN_SOURCE_LGD, field="stateNameEnglish"):
                    counters["state_aliases_added"] += 1

        district = districts.get(district_code)
        if not district:
            district = GeographyDistrict(id=uuid.uuid4(), lgd_code=district_code, state_id=state.id, canonical_name=district_name, census_name=None, aliases=[], created_at=timestamp, updated_at=timestamp)
            db.add(district)
            db.flush()
            districts[district_code] = district
            counters["districts_created"] += 1
        else:
            if district_name and normalize_name_for_search(district_name) != normalize_name_for_search(district.canonical_name):
                if add_alias(district, district_name, source_system=PIN_SOURCE_LGD, field="districtNameEnglish"):
                    counters["district_aliases_added"] += 1

        block_key = (district_code, block_code)
        block = blocks.get(block_key)
        if not block:
            block = GeographyBlock(id=uuid.uuid4(), lgd_code=block_code, district_id=district.id, canonical_name=block_name, aliases=[], created_at=timestamp, updated_at=timestamp)
            db.add(block)
            db.flush()
            blocks[block_key] = block
            counters["blocks_created"] += 1
        else:
            if block_name and normalize_name_for_search(block_name) != normalize_name_for_search(block.canonical_name):
                if add_alias(block, block_name, source_system=PIN_SOURCE_LGD, field="subdistrictNameEnglish"):
                    counters["block_aliases_added"] += 1

        village_key = (district_code, block_code, village_code)
        village = villages.get(village_key)
        if not village:
            village = GeographyVillage(
                id=uuid.uuid4(),
                lgd_code=village_code,
                block_id=block.id,
                district_id=district.id,
                canonical_name=village_name,
                census_name=None,
                census_village_code=None,
                pin_codes=[],
                aliases=[],
                created_at=timestamp,
                updated_at=timestamp,
            )
            db.add(village)
            db.flush()
            villages[village_key] = village
            counters["villages_created"] += 1
        else:
            if village_name and normalize_name_for_search(village_name) != normalize_name_for_search(village.canonical_name):
                if add_alias(village, village_name, source_system=PIN_SOURCE_LGD, field="villageNameEnglish"):
                    counters["village_aliases_added"] += 1

    db.flush()

    postal_seen = set()
    for row in postal_rows:
        key = postal_key(row)
        postal_seen.add(key)
        existing = (
            db.query(GeographyPostalReference)
            .filter(
                GeographyPostalReference.pin_code == key[0],
                GeographyPostalReference.office_name == clean(row.get("office_name")),
                GeographyPostalReference.office_type == clean(row.get("office_type")),
                GeographyPostalReference.postal_state_name == clean(row.get("postal_state_name")),
                GeographyPostalReference.postal_district_name == clean(row.get("postal_district_name")),
            )
            .first()
        )
        if not existing:
            existing = GeographyPostalReference(
                id=uuid.uuid4(),
                import_batch_id=batch.id,
                pin_code=key[0],
                office_name=clean(row.get("office_name")),
                office_type=clean(row.get("office_type")),
                delivery_status=clean(row.get("delivery_status")),
                circle_name=clean(row.get("circle_name")),
                region_name=clean(row.get("region_name")),
                division_name=clean(row.get("division_name")),
                postal_district_name=clean(row.get("postal_district_name")),
                postal_state_name=clean(row.get("postal_state_name")),
                latitude=decimal_or_none(row.get("latitude")),
                longitude=decimal_or_none(row.get("longitude")),
                source_system=PIN_SOURCE_POSTAL,
                source_row_hash=sha256_obj(row.get("source_row") or row),
                first_seen_at=timestamp,
                last_seen_at=timestamp,
                metadata_={"source_row": row.get("source_row")},
                created_at=timestamp,
                updated_at=timestamp,
                is_active=True,
            )
            db.add(existing)
            counters["postal_references_created"] += 1
        else:
            existing.import_batch_id = batch.id
            existing.last_seen_at = timestamp
            existing.expired_at = None
            existing.is_active = True
            existing.delivery_status = clean(row.get("delivery_status"))
            existing.latitude = decimal_or_none(row.get("latitude"))
            existing.longitude = decimal_or_none(row.get("longitude"))
            existing.source_row_hash = sha256_obj(row.get("source_row") or row)
            existing.updated_at = timestamp
            counters["postal_references_updated"] += 1

    link_seen = set()
    village_pin_cache = defaultdict(set)

    for row in lgd_rows:
        state_code = clean(row.get("state_lgd_code"))
        district_code = clean(row.get("district_lgd_code"))
        block_code = clean(row.get("subdistrict_lgd_code"))
        village_code = clean(row.get("village_lgd_code"))
        pin = clean(row.get("pin_code"))
        key = (state_code, district_code, block_code, village_code, pin)
        link_seen.add(key)

        village = villages.get((district_code, block_code, village_code))
        if village:
            village_pin_cache[village.id].add(pin)

        existing = (
            db.query(GeographyVillagePinLink)
            .filter(
                GeographyVillagePinLink.state_lgd_code == state_code,
                GeographyVillagePinLink.district_lgd_code == district_code,
                GeographyVillagePinLink.subdistrict_lgd_code == block_code,
                GeographyVillagePinLink.village_lgd_code == village_code,
                GeographyVillagePinLink.pin_code == pin,
            )
            .first()
        )
        if not existing:
            existing = GeographyVillagePinLink(
                id=uuid.uuid4(),
                import_batch_id=batch.id,
                geography_village_id=village.id if village else None,
                pin_code=pin,
                state_lgd_code=state_code,
                state_name=clean(row.get("state_name")),
                district_lgd_code=district_code,
                district_name=clean(row.get("district_name")),
                subdistrict_lgd_code=block_code,
                subdistrict_name=clean(row.get("subdistrict_name")),
                village_lgd_code=village_code,
                village_name=clean(row.get("village_name")),
                source_system=PIN_SOURCE_LGD,
                source_row_hash=sha256_obj(row.get("source_row") or row),
                match_status="MATCHED" if village else "UNMATCHED",
                first_seen_at=timestamp,
                last_seen_at=timestamp,
                metadata_={"source_row": row.get("source_row")},
                created_at=timestamp,
                updated_at=timestamp,
                is_active=True,
            )
            db.add(existing)
            counters["village_pin_links_created"] += 1
        else:
            existing.import_batch_id = batch.id
            existing.geography_village_id = village.id if village else None
            existing.match_status = "MATCHED" if village else "UNMATCHED"
            existing.last_seen_at = timestamp
            existing.expired_at = None
            existing.is_active = True
            existing.source_row_hash = sha256_obj(row.get("source_row") or row)
            existing.updated_at = timestamp
            counters["village_pin_links_updated"] += 1

    for village_id, pins in village_pin_cache.items():
        village = db.get(GeographyVillage, village_id)
        if village:
            current = set(village.pin_codes or [])
            merged = sorted(current | pins)
            if merged != (village.pin_codes or []):
                village.pin_codes = merged
                village.updated_at = timestamp
                counters["village_pin_cache_updated"] += 1

    if expire_missing:
        active_postal = db.query(GeographyPostalReference).filter(GeographyPostalReference.is_active == True).all()
        for row in active_postal:
            key = (
                clean(row.pin_code),
                clean(row.office_name).upper(),
                clean(row.office_type).upper(),
                clean(row.postal_state_name).upper(),
                clean(row.postal_district_name).upper(),
            )
            if key not in postal_seen:
                row.is_active = False
                row.expired_at = timestamp
                row.updated_at = timestamp
                counters["postal_references_expired"] += 1

        active_links = db.query(GeographyVillagePinLink).filter(GeographyVillagePinLink.is_active == True).all()
        for row in active_links:
            key = (
                clean(row.state_lgd_code),
                clean(row.district_lgd_code),
                clean(row.subdistrict_lgd_code),
                clean(row.village_lgd_code),
                clean(row.pin_code),
            )
            if key not in link_seen:
                row.is_active = False
                row.expired_at = timestamp
                row.updated_at = timestamp
                counters["village_pin_links_expired"] += 1

    batch.diff_summary = dict(counters)
    batch.updated_at = timestamp
    return dict(counters)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run/apply OGD all-India geography snapshot.")
    parser.add_argument("--staged-dir", help="Validated staged OGD geography directory. Defaults to latest under ../data/staged/ogd_geography.")
    parser.add_argument("--staged-root", default="../data/staged/ogd_geography")
    parser.add_argument("--refresh-mode", default="INITIAL_FULL_LOAD", choices=sorted(VALID_REFRESH_MODES))
    parser.add_argument("--apply", action="store_true", help="Write DB changes. Default is dry-run.")
    parser.add_argument("--expire-missing", action="store_true", help="Mark source-missing postal/link rows inactive. Only allowed with ANNUAL_FULL_REFRESH and --apply.")
    parser.add_argument("--actor-id")
    parser.add_argument("--reason")
    args = parser.parse_args()

    if args.expire_missing and (args.refresh_mode != "ANNUAL_FULL_REFRESH" or not args.apply):
        raise SystemExit("--expire-missing is allowed only with --apply --refresh-mode ANNUAL_FULL_REFRESH")

    script_dir = Path(__file__).resolve().parent
    staged_dir = Path(args.staged_dir).resolve() if args.staged_dir else latest_staged_dir((script_dir.parent / args.staged_root).resolve())

    lgd_rows, postal_rows, metadata = load_inputs(staged_dir)
    validation = metadata["validation"]

    db = SessionLocal()
    try:
        diff = build_diff(db, lgd_rows, postal_rows)
        row_counts = {
            "lgd_rows": len(lgd_rows),
            "postal_rows": len(postal_rows),
            "lgd_input_rows": metadata["lgd_dedupe"]["input_rows"],
            "postal_input_rows": metadata["postal_dedupe"]["input_rows"],
        }
        batch = get_or_create_batch(
            db,
            staged_dir=staged_dir,
            validation=validation,
            refresh_mode=args.refresh_mode,
            apply=args.apply,
            actor_id=args.actor_id,
            reason=args.reason,
            diff_summary=diff,
            row_counts=row_counts,
        )

        apply_summary = {}
        if args.apply:
            apply_summary = apply_rows(
                db,
                batch=batch,
                lgd_rows=lgd_rows,
                postal_rows=postal_rows,
                refresh_mode=args.refresh_mode,
                expire_missing=args.expire_missing,
            )
            db.commit()
        else:
            db.rollback()

        result = {
            "schema_version": "ogd_geography_apply_result.v1",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "refresh_mode": args.refresh_mode,
            "expire_missing": args.expire_missing,
            "staged_dir": str(staged_dir),
            "validation_ready": validation.get("ready_for_apply_design"),
            "dedupe": {
                "lgd": metadata["lgd_dedupe"],
                "postal": metadata["postal_dedupe"],
            },
            "diff": diff,
            "apply_summary": apply_summary,
            "batch_id": str(batch.id) if args.apply else None,
            "next_actions": [
                "Review dry-run counts before --apply.",
                "Use INCREMENTAL_REFRESH for periodic update checks.",
                "Use ANNUAL_FULL_REFRESH with --expire-missing only after full-source review.",
                "Keep Census as a separate enrichment/crosswalk source when available.",
            ],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
