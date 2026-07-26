#!/usr/bin/env python3
"""Export Pass 1 company website review checklist.

Reads company_website_candidates.json and writes CSV + Markdown checklist files
for manual official-website review.

This script does not scrape products.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


CSV_COLUMNS = [
    "company_code",
    "company_name",
    "segments",
    "review_status",
    "selected_official_website_url",
    "selected_confidence",
    "selected_reason",
    "candidate_url_1",
    "candidate_confidence_1",
    "candidate_reason_1",
    "candidate_url_2",
    "candidate_confidence_2",
    "candidate_reason_2",
    "search_url_1",
    "search_url_2",
    "search_url_3",
    "reviewer_notes",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def latest_candidates_path(root: Path) -> Path:
    paths = sorted(root.glob("*/company_website_candidates.json"))
    if not paths:
        raise SystemExit(f"No company_website_candidates.json found under {root}")
    return paths[-1]


def csv_row(company: dict[str, Any]) -> dict[str, str]:
    candidates = company.get("website_candidates") or []
    searches = company.get("search_urls") or []

    row = {
        "company_code": clean(company.get("company_code")),
        "company_name": clean(company.get("company_name")),
        "segments": ", ".join(company.get("segments") or []),
        "review_status": clean(company.get("review_status")),
        "selected_official_website_url": clean(company.get("selected_official_website_url")),
        "selected_confidence": clean(company.get("selected_confidence")),
        "selected_reason": clean(company.get("selected_reason")),
        "reviewer_notes": "",
    }

    for idx in range(2):
        candidate = candidates[idx] if idx < len(candidates) else {}
        row[f"candidate_url_{idx+1}"] = clean(candidate.get("url"))
        row[f"candidate_confidence_{idx+1}"] = clean(candidate.get("confidence"))
        row[f"candidate_reason_{idx+1}"] = clean(candidate.get("reason"))

    for idx in range(3):
        search = searches[idx] if idx < len(searches) else {}
        row[f"search_url_{idx+1}"] = clean(search.get("duckduckgo_html") or search.get("google") or search.get("bing"))

    return row


def write_csv(path: Path, companies: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for company in companies:
            writer.writerow(csv_row(company))


def write_markdown(path: Path, data: dict[str, Any]) -> None:
    companies = data.get("companies") or []
    lines = [
        "# Company Website Review Checklist",
        "",
        f"Schema: `{data.get('schema_version')}`",
        f"Generated at: `{data.get('generated_at')}`",
        f"Search attempted: `{data.get('search_attempted')}`",
        "",
        "Review rule: select an official website only after manual verification. Do not scrape products from unreviewed candidates.",
        "",
        "## Checklist",
        "",
    ]

    for company in companies:
        lines.extend([
            f"### {company.get('company_code')} - {company.get('company_name')}",
            "",
            f"- Segments: {', '.join(company.get('segments') or []) or '-'}",
            f"- Review status: {company.get('review_status')}",
            "- Selected official website URL: ",
            "- Selected confidence: ",
            "- Selected reason: ",
            "- Reviewer notes: ",
            "",
            "Search URLs:",
        ])

        for search in (company.get("search_urls") or [])[:3]:
            query = search.get("query") or "search"
            url = search.get("duckduckgo_html") or search.get("google") or search.get("bing")
            lines.append(f"- [{query}]({url})")

        candidates = company.get("website_candidates") or []
        if candidates:
            lines.append("")
            lines.append("Candidates:")
            for candidate in candidates[:5]:
                lines.append(f"- `{candidate.get('confidence')}` {candidate.get('url') or '-'} — {candidate.get('reason') or '-'}")

        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export company website review checklist.")
    parser.add_argument("--candidates", help="Path to company_website_candidates.json. Defaults to latest staged file.")
    parser.add_argument("--staged-root", default="../data/staged/company_product_sources")
    args = parser.parse_args()

    cwd = Path.cwd()
    root = (cwd / args.staged_root).resolve()
    candidates_path = Path(args.candidates).resolve() if args.candidates else latest_candidates_path(root)

    data = json.loads(candidates_path.read_text(encoding="utf-8"))
    output_dir = candidates_path.parent

    csv_path = output_dir / "company_website_review_checklist.csv"
    md_path = output_dir / "company_website_review_checklist.md"

    companies = data.get("companies") or []
    write_csv(csv_path, companies)
    write_markdown(md_path, data)

    print(json.dumps({
        "schema_version": "company_website_review_checklist_export.v1",
        "input_path": str(candidates_path),
        "csv_path": str(csv_path),
        "markdown_path": str(md_path),
        "company_count": len(companies),
        "next_actions": [
            "Open the CSV/Markdown checklist and review official website URLs.",
            "Copy selected official website values back into a reviewed website candidate file before product-index discovery.",
            "Do not scrape products until selected official website URLs are reviewed.",
        ],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
