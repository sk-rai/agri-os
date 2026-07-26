#!/usr/bin/env python3
"""Build Pass 0 company/product source scrape plan.

This script does not scrape company websites.

It reads existing manufacturers and company discovery candidates, then writes a
review queue under data/staged/company_product_sources/<timestamp>/ so admins can
review official website/product-page search targets before any automated scrape.

Source policy:
- Screener/TNAU/local lists are company-discovery sources only.
- Official company sites, product labels, and regulators are product truth sources.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.farmer.models import CompanyDiscoveryCandidate
from app.modules.master_data.models import Manufacturer


SCHEMA_VERSION = "company_product_scrape_plan.v1"

SOURCE_ROLE_BY_NAME = {
    "SCREENER_FERTILIZERS_AGROCHEMICALS": "COMPANY_DISCOVERY_ONLY",
    "TNAU_SEED_INDUSTRIES_INDIA_PDF": "COMPANY_DISCOVERY_ONLY",
    "LOCAL_EXISTING_CATALOG": "LOCAL_BOOTSTRAP_REFERENCE",
    "CURATED_STARTER_PRODUCT_MAPPING": "DEMO_REFERENCE_ONLY",
}

SEGMENT_SEARCH_HINTS = {
    "FERTILIZER": [
        "fertilizer products",
        "NPK DAP urea product catalogue",
        "micronutrient fertilizer product label",
        "water soluble fertilizer catalogue",
    ],
    "CROP_PROTECTION": [
        "crop protection products",
        "insecticide fungicide herbicide catalogue",
        "product label crop pest dosage",
        "CIBRC registration label claim",
    ],
    "SEED": [
        "seed products",
        "hybrid seed varieties",
        "crop seed catalogue",
        "seed variety maturity duration",
    ],
    "BIO_INPUT": [
        "biofertilizer products",
        "biopesticide products",
        "Trichoderma PSB Azospirillum product catalogue",
        "biostimulant product label",
    ],
    "ORGANIC": [
        "organic input products",
        "organic fertilizer product catalogue",
        "organic certification input evidence",
    ],
    "NATURAL": [
        "natural farming inputs",
        "Jeevamrit Beejamrit Panchagavya preparation",
        "low external input agriculture products",
    ],
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def codeish(value: str) -> str:
    value = clean(value).upper()
    value = re.sub(r"[^A-Z0-9]+", "_", value)
    return value.strip("_") or "UNKNOWN"


def source_role(source: str | None) -> str:
    return SOURCE_ROLE_BY_NAME.get(clean(source), "REVIEW_SOURCE_ROLE")


def source_ref_from_alias(alias: dict[str, Any]) -> dict[str, Any] | None:
    name = clean(alias.get("name"))
    source = clean(alias.get("source"))
    if not name and not source:
        return None
    source = source or "MANUFACTURER_ALIAS"
    return {
        "source": source,
        "source_role": source_role(source),
        "name": name,
    }


def source_refs_from_discovery(row: CompanyDiscoveryCandidate) -> list[dict[str, Any]]:
    refs = []
    for ref in row.source_references or []:
        if isinstance(ref, dict):
            source = clean(ref.get("source")) or clean(row.source)
            refs.append({
                **ref,
                "source_role": source_role(source),
            })
    if not refs:
        refs.append({
            "source": row.source,
            "source_role": source_role(row.source),
        })
    return refs


def infer_segments(manufacturer: Manufacturer | None, discovery_rows: list[CompanyDiscoveryCandidate]) -> list[str]:
    segments: set[str] = set()

    for row in discovery_rows:
        metadata = row.metadata_ or {}
        for item in metadata.get("segments") or []:
            if clean(item):
                segments.add(codeish(item))
        company_type = codeish(row.company_type or "")
        if "SEED" in company_type:
            segments.add("SEED")
        if "FERTILIZER" in company_type:
            segments.add("FERTILIZER")
        if "PESTICIDE" in company_type or "CROP_PROTECTION" in company_type:
            segments.add("CROP_PROTECTION")
        if "BIO" in company_type:
            segments.add("BIO_INPUT")
        if "ORGANIC" in company_type:
            segments.add("ORGANIC")

    aliases = manufacturer.aliases if manufacturer else []
    for alias in aliases or []:
        source = codeish(alias.get("source") if isinstance(alias, dict) else "")
        if "TNAU" in source or "SEED" in source:
            segments.add("SEED")
        if "SCREENER" in source:
            segments.update(["FERTILIZER", "CROP_PROTECTION"])

    metadata = manufacturer.metadata_ if manufacturer and hasattr(manufacturer, "metadata_") else None
    if isinstance(metadata, dict):
        for item in metadata.get("segments") or []:
            if clean(item):
                segments.add(codeish(item))

    return sorted(segments) or ["REVIEW"]


def suggested_queries(company_name: str, segments: list[str]) -> list[str]:
    queries: list[str] = []
    base = clean(company_name)
    if not base:
        return queries

    queries.append(f'{base} official website agriculture products')
    queries.append(f'{base} product catalogue PDF')
    queries.append(f'{base} product label dosage')

    for segment in segments:
        for hint in SEGMENT_SEARCH_HINTS.get(segment, []):
            queries.append(f'{base} {hint}')

    # Keep stable, deduped, and bounded for review.
    seen = set()
    deduped = []
    for q in queries:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)
    return deduped[:12]


def build_plan(tenant_id: str | None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        manufacturers = {
            row.code: row
            for row in db.query(Manufacturer).filter(Manufacturer.is_active == True).order_by(Manufacturer.code).all()
        }

        discovery_query = db.query(CompanyDiscoveryCandidate).order_by(CompanyDiscoveryCandidate.candidate_name)
        if tenant_id:
            discovery_query = discovery_query.filter(CompanyDiscoveryCandidate.tenant_id == tenant_id)
        discovery_rows = discovery_query.all()

        discovery_by_code: dict[str, list[CompanyDiscoveryCandidate]] = defaultdict(list)
        unmatched_discovery: list[CompanyDiscoveryCandidate] = []

        for row in discovery_rows:
            metadata = row.metadata_ or {}
            manufacturer_code = codeish(metadata.get("manufacturer_code") or "")
            if manufacturer_code and manufacturer_code in manufacturers:
                discovery_by_code[manufacturer_code].append(row)
            else:
                matched = None
                row_name = clean(row.candidate_name).lower()
                for code, manufacturer in manufacturers.items():
                    names = [manufacturer.canonical_name, manufacturer.short_name, code]
                    aliases = manufacturer.aliases or []
                    names.extend(alias.get("name") for alias in aliases if isinstance(alias, dict))
                    if any(clean(name).lower() and clean(name).lower() == row_name for name in names):
                        matched = code
                        break
                if matched:
                    discovery_by_code[matched].append(row)
                else:
                    unmatched_discovery.append(row)

        companies = []

        for code, manufacturer in sorted(manufacturers.items()):
            rows = discovery_by_code.get(code, [])
            segments = infer_segments(manufacturer, rows)
            source_refs = []
            for alias in manufacturer.aliases or []:
                if isinstance(alias, dict):
                    alias_ref = source_ref_from_alias(alias)
                    if alias_ref:
                        source_refs.append(alias_ref)
            for row in rows:
                source_refs.extend(source_refs_from_discovery(row))

            companies.append({
                "company_code": code,
                "company_name": manufacturer.canonical_name,
                "short_name": manufacturer.short_name,
                "segments": segments,
                "source_list_references": source_refs,
                "suggested_search_queries": suggested_queries(manufacturer.canonical_name, segments),
                "official_website_url": None,
                "official_website_confidence": None,
                "official_website_reason": None,
                "product_index_urls": [],
                "label_or_catalog_urls": [],
                "review_status": "NEEDS_OFFICIAL_WEBSITE_REVIEW",
                "notes": "Pass 0 only. Do not scrape products until official website is reviewed.",
            })

        for row in unmatched_discovery:
            segments = infer_segments(None, [row])
            code = codeish((row.metadata_ or {}).get("manufacturer_code") or row.candidate_name)
            companies.append({
                "company_code": code,
                "company_name": row.candidate_name,
                "short_name": None,
                "segments": segments,
                "source_list_references": source_refs_from_discovery(row),
                "suggested_search_queries": suggested_queries(row.candidate_name, segments),
                "official_website_url": None,
                "official_website_confidence": None,
                "official_website_reason": None,
                "product_index_urls": [],
                "label_or_catalog_urls": [],
                "review_status": "UNMATCHED_DISCOVERY_CANDIDATE",
                "notes": "Discovery candidate is not matched to an active manufacturer row yet.",
            })

        companies.sort(key=lambda item: (item["company_name"] or "").lower())

        source_role_counts = defaultdict(int)
        segment_counts = defaultdict(int)
        for company in companies:
            for segment in company["segments"]:
                segment_counts[segment] += 1
            for ref in company["source_list_references"]:
                source_role_counts[ref.get("source_role") or "UNKNOWN"] += 1

        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id,
            "mode": "PASS_0_COMPANY_QUEUE_ONLY",
            "source_policy": {
                "screener": "Company discovery only; not a product/dosage/label source.",
                "tnau_seed_pdf": "Seed-company discovery only; not a product/dosage/label source.",
                "company_site": "Preferred source for product existence, catalogs, labels, and source text.",
                "regulator": "Preferred source for legal label claims, registration, dosage, and certification where available.",
            },
            "summary": {
                "active_manufacturer_count": len(manufacturers),
                "discovery_candidate_count": len(discovery_rows),
                "unmatched_discovery_candidate_count": len(unmatched_discovery),
                "company_queue_count": len(companies),
                "segment_counts": dict(sorted(segment_counts.items())),
                "source_role_counts": dict(sorted(source_role_counts.items())),
            },
            "next_actions": [
                "Review official website candidates manually or with a constrained search pass.",
                "Do not scrape product details until official website URLs are reviewed.",
                "Capture official website confidence and reason before Pass 2 product-index discovery.",
                "Keep regulator/product-label evidence above marketing-page evidence for dosage and legal claims.",
            ],
            "companies": companies,
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Pass 0 company product source scrape plan.")
    parser.add_argument("--tenant-id", default="default", help="Tenant scope for company discovery candidates. Use empty string for all tenants.")
    parser.add_argument("--output-root", default="../../data/staged/company_product_sources")
    args = parser.parse_args()

    tenant_id = args.tenant_id or None
    plan = build_plan(tenant_id)

    script_dir = Path(__file__).resolve().parent
    output_root = (script_dir / args.output_root).resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = output_root / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    plan_path = output_dir / "company_scrape_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "schema_version": "company_product_scrape_plan_write_result.v1",
        "plan_path": str(plan_path),
        "summary": plan["summary"],
        "next_actions": plan["next_actions"],
    }, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
