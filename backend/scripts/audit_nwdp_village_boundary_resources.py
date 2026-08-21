#!/usr/bin/env python3
"""Read-only audit for NWDP/GSI village-boundary resource manifest.

This script inventories the National Water Data Portal village-boundary dataset
without downloading KML/GeoJSON/SHP files and without database writes.

It checks whether expected state/UT + format combinations are visible, whether
resource URLs can be discovered, and whether obvious naming/coverage gaps exist.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

DATASET_URL = "https://nwdp.nwic.gov.in/dataset/village-boundary"

EXPECTED_STATES_AND_UTS = [
    "Andaman and Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Dadra and Nagar Haveli and Daman & Diu",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu & Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttarakhand",
    "Uttar Pradesh",
    "West Bengal",
]

EXPECTED_FORMATS = ["KML", "GeoJSON", "SHP"]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


STATE_BY_NORM = {_norm(state): state for state in EXPECTED_STATES_AND_UTS}


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._stack: list[dict[str, Any]] = []
        self.links: list[dict[str, str]] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "a":
            self._stack.append({"href": attrs_dict.get("href", ""), "text": []})

    def handle_data(self, data: str) -> None:
        clean = data.strip()
        if clean:
            self.text_parts.append(clean)
            if self._stack:
                self._stack[-1]["text"].append(clean)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._stack:
            item = self._stack.pop()
            text = " ".join(item["text"]).strip()
            if text or item.get("href"):
                self.links.append({"text": text, "href": item.get("href", "")})


def _fetch_html(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "agri-os-nwdp-village-boundary-audit/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _absolute_url(base_url: str, href: str) -> str | None:
    if not href:
        return None
    return urllib.parse.urljoin(base_url, href)


def _extract_resource_from_label(label: str) -> tuple[str, str] | None:
    compact = re.sub(r"\s+", " ", html.unescape(label)).strip()
    match = re.search(
        r"\bvillage\s+boundary\s+of\s+(.+?)\s*(KML|GeoJSON|SHP)\b",
        compact,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    state_raw = match.group(1).strip(" -:|")
    fmt_raw = match.group(2)
    state_norm = _norm(state_raw)
    state = STATE_BY_NORM.get(state_norm)

    if not state:
        for expected_norm, expected_state in STATE_BY_NORM.items():
            if expected_norm in state_norm or state_norm in expected_norm:
                state = expected_state
                break

    if not state:
        state = state_raw

    fmt = "GeoJSON" if fmt_raw.lower() == "geojson" else fmt_raw.upper()
    return state, fmt


def _parse_resources(raw_html: str, base_url: str) -> dict[str, Any]:
    parser = LinkTextParser()
    parser.feed(raw_html)

    resources: list[dict[str, Any]] = []
    seen_labels: set[tuple[str, str, str | None]] = set()

    for link in parser.links:
        parsed = _extract_resource_from_label(link["text"])
        if not parsed:
            continue
        state, fmt = parsed
        url = _absolute_url(base_url, link.get("href", ""))
        key = (state, fmt, url)
        if key in seen_labels:
            continue
        seen_labels.add(key)
        resources.append({
            "state_or_ut": state,
            "format": fmt,
            "title": link["text"],
            "url": url,
            "source": "anchor",
        })

    visible_text = " ".join(parser.text_parts)
    for match in re.finditer(
        r"\bvillage\s+boundary\s+of\s+(.+?)\s*(KML|GeoJSON|SHP)\b",
        visible_text,
        flags=re.IGNORECASE,
    ):
        title = match.group(0).strip()
        parsed = _extract_resource_from_label(title)
        if not parsed:
            continue
        state, fmt = parsed
        if any(row["state_or_ut"] == state and row["format"] == fmt for row in resources):
            continue
        resources.append({
            "state_or_ut": state,
            "format": fmt,
            "title": title,
            "url": None,
            "source": "visible_text",
        })

    return {
        "links_seen": len(parser.links),
        "visible_text_length": len(visible_text),
        "resources": sorted(resources, key=lambda row: (row["state_or_ut"], row["format"], row.get("url") or "")),
    }


def _summarize(resources: list[dict[str, Any]]) -> dict[str, Any]:
    expected_pairs = {(state, fmt) for state in EXPECTED_STATES_AND_UTS for fmt in EXPECTED_FORMATS}
    observed_pairs = {(row["state_or_ut"], row["format"]) for row in resources}

    pair_counts = Counter((row["state_or_ut"], row["format"]) for row in resources)
    duplicates = [
        {"state_or_ut": state, "format": fmt, "count": count}
        for (state, fmt), count in sorted(pair_counts.items())
        if count > 1
    ]

    state_counts: dict[str, dict[str, int]] = defaultdict(lambda: {fmt: 0 for fmt in EXPECTED_FORMATS})
    for row in resources:
        if row["format"] in EXPECTED_FORMATS:
            state_counts[row["state_or_ut"]][row["format"]] += 1

    unknown_states = sorted({
        row["state_or_ut"]
        for row in resources
        if row["state_or_ut"] not in EXPECTED_STATES_AND_UTS
    })

    resources_without_url = [
        {"state_or_ut": row["state_or_ut"], "format": row["format"], "title": row["title"]}
        for row in resources
        if not row.get("url")
    ]

    missing = [
        {"state_or_ut": state, "format": fmt}
        for state, fmt in sorted(expected_pairs - observed_pairs)
    ]

    extra = [
        {"state_or_ut": state, "format": fmt}
        for state, fmt in sorted(observed_pairs - expected_pairs)
    ]

    suspected_label_issues = []
    if any(row["state_or_ut"] == "Telangana" and row["format"] == "SHP" for row in resources) and (
        "Uttarakhand",
        "SHP",
    ) not in observed_pairs:
        suspected_label_issues.append({
            "issue": "possible_uttarakhand_shp_label_mismatch",
            "detail": "Visible portal text previously appeared to repeat Telangana SHP near Uttarakhand entries.",
        })

    complete_pairs_with_urls = not missing and not duplicates and not resources_without_url and not unknown_states

    return {
        "expected_state_or_ut_count": len(EXPECTED_STATES_AND_UTS),
        "expected_formats": EXPECTED_FORMATS,
        "expected_resource_count": len(expected_pairs),
        "observed_resource_count": len(resources),
        "observed_pair_count": len(observed_pairs),
        "format_counts": dict(sorted(Counter(row["format"] for row in resources).items())),
        "state_format_counts": dict(sorted(state_counts.items())),
        "missing_resources": missing,
        "duplicate_resources": duplicates,
        "extra_resources": extra,
        "unknown_states": unknown_states,
        "resources_without_url": resources_without_url,
        "suspected_label_issues": suspected_label_issues,
        "readiness": {
            "safe_read_only": True,
            "downloads_attempted": False,
            "db_writes_attempted": False,
            "complete_expected_state_format_matrix": not missing,
            "resource_urls_discovered_for_all_rows": not resources_without_url,
            "ready_for_pilot_download": complete_pairs_with_urls,
            "ready_for_ingestion": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit NWDP/GSI village-boundary dataset resources without downloads or DB writes.")
    parser.add_argument("--url", default=DATASET_URL)
    parser.add_argument("--html-file", help="Optional saved HTML/text file to parse instead of fetching the portal.")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--output", help="Optional path to write JSON result.")
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).isoformat()

    try:
        if args.html_file:
            raw_html = Path(args.html_file).read_text(encoding="utf-8", errors="replace")
            fetch_status = {"mode": "HTML_FILE", "html_file": args.html_file}
        else:
            raw_html = _fetch_html(args.url, args.timeout)
            fetch_status = {"mode": "HTTP_FETCH", "url": args.url, "healthy": True}
    except urllib.error.HTTPError as exc:
        result = {
            "schema_version": "nwdp_village_boundary_manifest_audit.v1",
            "generated_at": generated_at,
            "source_url": args.url,
            "healthy": False,
            "error": "HTTP_ERROR",
            "status_code": exc.code,
            "body_preview": exc.read().decode("utf-8", errors="replace")[:1200],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        result = {
            "schema_version": "nwdp_village_boundary_manifest_audit.v1",
            "generated_at": generated_at,
            "source_url": args.url,
            "healthy": False,
            "error": exc.__class__.__name__,
            "message": str(exc),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    parsed = _parse_resources(raw_html, args.url)
    summary = _summarize(parsed["resources"])

    result = {
        "schema_version": "nwdp_village_boundary_manifest_audit.v1",
        "generated_at": generated_at,
        "source_url": args.url,
        "source_summary": {
            "portal": "National Water Data Portal",
            "dataset": "Village Boundary",
            "producer_agency": "Geological Survey of India",
            "claim_boundary": "Village boundary is reference locality context, not cadastral parcel or ownership truth.",
        },
        "fetch_status": fetch_status,
        "parse_summary": {
            "links_seen": parsed["links_seen"],
            "visible_text_length": parsed["visible_text_length"],
        },
        "summary": summary,
        "resources": parsed["resources"],
        "next_actions": [
            "Review missing, duplicate, unknown, and no-URL rows before pilot download.",
            "Pilot one state first, preferably Karnataka, before all-India acquisition.",
            "Validate CRS, geometry type, invalid geometries, feature count, attributes, and license/source metadata before ingestion.",
            "Load into separate reference boundary tables only after a reviewed manifest and pilot validation.",
        ],
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
