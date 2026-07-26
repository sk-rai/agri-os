#!/usr/bin/env python3
"""Pass 1: discover candidate official company websites.

This script reads a Pass 0 company_scrape_plan.json and writes a reviewable
company_website_candidates.json.

It does not scrape products.

Default mode is offline/review-safe: generate search URLs and blank candidate
slots. Use --search to attempt lightweight DuckDuckGo HTML discovery. Search
engine scraping can fail or be rate-limited, so results are advisory only.

Review rule:
- A candidate URL is not trusted until manually reviewed.
- Product scraping must not start from unreviewed candidates.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


SCHEMA_VERSION = "company_official_website_candidates.v1"

SEARCH_ENGINES = {
    "duckduckgo_html": "https://duckduckgo.com/html/?q={query}",
    "duckduckgo_lite": "https://lite.duckduckgo.com/lite/?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "google": "https://www.google.com/search?q={query}",
}

EXCLUDED_DOMAINS = {
    "screener.in",
    "moneycontrol.com",
    "trendlyne.com",
    "economictimes.indiatimes.com",
    "business-standard.com",
    "livemint.com",
    "wikipedia.org",
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "zaubacorp.com",
    "tofler.in",
    "indiamart.com",
    "tradeindia.com",
    "amazon.in",
    "flipkart.com",
    "groww.in",
    "tickertape.in",
    "marketsmojo.com",
}


@dataclass
class SearchCandidate:
    url: str
    title: str | None
    snippet: str | None
    source_query: str
    discovery_method: str
    confidence: str
    reason: str


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_domain(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def tokenize_company_name(name: str) -> list[str]:
    stop = {
        "india", "indian", "limited", "ltd", "pvt", "private", "company", "co",
        "corporation", "industries", "industry", "chemical", "chemicals",
        "fertilizers", "fertilisers", "agro", "agri", "seed", "seeds", "crop",
        "science", "sciences", "products", "international", "travancore",
    }
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    return [t for t in tokens if len(t) >= 3 and t not in stop]


def search_urls_for_company(company: dict[str, Any]) -> list[dict[str, str]]:
    queries = company.get("suggested_search_queries") or []
    focused = []
    name = clean(company.get("company_name"))
    if name:
        focused.extend([
            f"{name} official website",
            f"{name} agriculture products official",
            f"{name} product catalogue official",
        ])
    focused.extend(queries[:4])

    deduped = []
    seen = set()
    for query in focused:
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(query)

    results = []
    for query in deduped[:6]:
        encoded = quote_plus(query)
        results.append({
            "query": query,
            "duckduckgo_html": SEARCH_ENGINES["duckduckgo_html"].format(query=encoded),
            "duckduckgo_lite": SEARCH_ENGINES["duckduckgo_lite"].format(query=encoded),
            "bing": SEARCH_ENGINES["bing"].format(query=encoded),
            "google": SEARCH_ENGINES["google"].format(query=encoded),
        })
    return results


def unwrap_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        if "uddg" in query:
            return unquote(query["uddg"][0])
    return url


def extract_links_from_html(page: str) -> list[tuple[str, str | None]]:
    links: list[tuple[str, str | None]] = []

    # DuckDuckGo html result links often use class=result__a.
    for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, flags=re.I | re.S):
        url = html.unescape(match.group(1))
        title = re.sub(r"<[^>]+>", " ", match.group(2))
        title = html.unescape(re.sub(r"\s+", " ", title)).strip() or None
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("/"):
            continue
        url = unwrap_duckduckgo_url(url)
        if url.startswith("http"):
            links.append((url, title))
    return links


def score_candidate(url: str, title: str | None, company: dict[str, Any]) -> tuple[str, str]:
    domain = normalize_domain(url)
    name = clean(company.get("company_name"))
    code = clean(company.get("company_code")).lower().replace("_", "")
    tokens = tokenize_company_name(name)

    if not domain:
        return "REJECT", "No domain parsed."
    if any(domain == blocked or domain.endswith("." + blocked) for blocked in EXCLUDED_DOMAINS):
        return "REJECT", f"Excluded directory/news/marketplace domain: {domain}"

    joined_domain = domain.replace("-", "").replace(".", "")
    matching_tokens = [token for token in tokens if token in joined_domain]
    title_text = (title or "").lower()

    if code and len(code) >= 4 and code in joined_domain:
        return "HIGH_REVIEW_REQUIRED", f"Company code appears in domain {domain}; still requires manual official-site review."
    if len(matching_tokens) >= 2:
        return "MEDIUM_REVIEW_REQUIRED", f"Multiple company-name tokens appear in domain {domain}: {matching_tokens}."
    if matching_tokens and ("official" in title_text or "home" in title_text or name.lower() in title_text):
        return "MEDIUM_REVIEW_REQUIRED", f"Company token appears in domain and title suggests official result: {matching_tokens}."
    if matching_tokens:
        return "LOW_REVIEW_REQUIRED", f"One company-name token appears in domain {domain}: {matching_tokens}."

    return "LOW_REVIEW_REQUIRED", f"Candidate from search result, but domain does not strongly match company tokens: {domain}."


def attempt_search(company: dict[str, Any], delay_seconds: float, max_results_per_company: int) -> list[dict[str, Any]]:
    if requests is None:
        return [{
            "url": None,
            "title": None,
            "snippet": None,
            "source_query": None,
            "discovery_method": "SEARCH_DISABLED",
            "confidence": "SEARCH_UNAVAILABLE",
            "reason": "Python requests is not installed.",
        }]

    session = requests.Session()
    session.headers.update({
        "User-Agent": "AgriOSLocalResearchBot/0.1 (+local review; no product scraping)",
    })

    candidates: list[SearchCandidate] = []
    seen_domains = set()

    for search in search_urls_for_company(company)[:3]:
        query = search["query"]
        url = search["duckduckgo_html"]
        try:
            response = session.get(url, timeout=15)
            page = response.text
        except Exception as exc:
            candidates.append(SearchCandidate(
                url="",
                title=None,
                snippet=None,
                source_query=query,
                discovery_method="DUCKDUCKGO_HTML",
                confidence="SEARCH_FAILED",
                reason=f"Search request failed: {exc}",
            ))
            continue

        for result_url, title in extract_links_from_html(page):
            domain = normalize_domain(result_url)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            confidence, reason = score_candidate(result_url, title, company)
            if confidence == "REJECT":
                continue
            candidates.append(SearchCandidate(
                url=result_url,
                title=title,
                snippet=None,
                source_query=query,
                discovery_method="DUCKDUCKGO_HTML",
                confidence=confidence,
                reason=reason,
            ))
            if len(candidates) >= max_results_per_company:
                break

        if len(candidates) >= max_results_per_company:
            break
        time.sleep(delay_seconds)

    return [
        {
            "url": c.url or None,
            "domain": normalize_domain(c.url) if c.url else None,
            "title": c.title,
            "snippet": c.snippet,
            "source_query": c.source_query,
            "discovery_method": c.discovery_method,
            "confidence": c.confidence,
            "reason": c.reason,
            "review_status": "NEEDS_MANUAL_REVIEW",
        }
        for c in candidates[:max_results_per_company]
    ]


def latest_plan_path(root: Path) -> Path:
    plans = sorted(root.glob("*/company_scrape_plan.json"))
    if not plans:
        raise SystemExit(f"No company_scrape_plan.json found under {root}")
    return plans[-1]


def build_candidates(plan: dict[str, Any], *, search: bool, limit: int | None, delay_seconds: float, max_results_per_company: int) -> dict[str, Any]:
    companies = plan.get("companies") or []
    if limit:
        companies = companies[:limit]

    rows = []
    for company in companies:
        search_links = search_urls_for_company(company)
        candidates = attempt_search(company, delay_seconds, max_results_per_company) if search else []
        rows.append({
            "company_code": company.get("company_code"),
            "company_name": company.get("company_name"),
            "segments": company.get("segments") or [],
            "source_list_references": company.get("source_list_references") or [],
            "search_urls": search_links,
            "website_candidates": candidates,
            "selected_official_website_url": None,
            "selected_confidence": None,
            "selected_reason": None,
            "review_status": "NEEDS_OFFICIAL_WEBSITE_REVIEW",
            "notes": "Pass 1 candidate discovery only. Do not scrape products until selected official website is reviewed.",
        })

    with_candidates = sum(1 for row in rows if row["website_candidates"])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_plan_schema_version": plan.get("schema_version"),
        "input_plan_generated_at": plan.get("generated_at"),
        "mode": "PASS_1_OFFICIAL_WEBSITE_CANDIDATES",
        "search_attempted": search,
        "review_policy": {
            "selected_official_website_url": "Must be populated only after manual/admin review.",
            "product_scraping": "Blocked until official website is reviewed.",
            "confidence": "Search confidence is advisory and not trusted by itself.",
        },
        "summary": {
            "company_count": len(rows),
            "companies_with_search_candidates": with_candidates,
            "companies_without_search_candidates": len(rows) - with_candidates,
        },
        "companies": rows,
        "next_actions": [
            "Manually review website_candidates and search_urls.",
            "Populate selected_official_website_url only when official site is clear.",
            "Reject directories, stock trackers, marketplaces, unrelated companies, and stale domains.",
            "Run product-index discovery only against reviewed official websites.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover candidate official company websites for Pass 1 review.")
    parser.add_argument("--plan", help="Path to Pass 0 company_scrape_plan.json. Defaults to latest under data/staged/company_product_sources.")
    parser.add_argument("--staged-root", default="../data/staged/company_product_sources")
    parser.add_argument("--search", action="store_true", help="Attempt lightweight DuckDuckGo HTML search. Results are advisory only.")
    parser.add_argument("--limit", type=int, help="Limit companies for trial runs.")
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    parser.add_argument("--max-results-per-company", type=int, default=5)
    args = parser.parse_args()

    cwd = Path.cwd()
    root = (cwd / args.staged_root).resolve()
    plan_path = Path(args.plan).resolve() if args.plan else latest_plan_path(root)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    result = build_candidates(
        plan,
        search=args.search,
        limit=args.limit,
        delay_seconds=args.delay_seconds,
        max_results_per_company=args.max_results_per_company,
    )

    output_dir = plan_path.parent
    output_path = output_dir / "company_website_candidates.json"
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "schema_version": "company_official_website_candidates_write_result.v1",
        "input_plan": str(plan_path),
        "output_path": str(output_path),
        "summary": result["summary"],
        "search_attempted": result["search_attempted"],
        "next_actions": result["next_actions"],
    }, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
