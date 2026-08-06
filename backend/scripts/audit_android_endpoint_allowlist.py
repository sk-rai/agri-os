#!/usr/bin/env python3
"""Audit Android-facing endpoint docs against the current FastAPI OpenAPI paths.

This script is intentionally read-only.  It gives Android/backend handoff a
small tripwire for stale endpoint names such as old bootstrap/profile aliases.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
DOCS_DIR = ROOT / "docs"
ALLOWLIST_PATH = DOCS_DIR / "android-endpoint-allowlist.md"

ANDROID_DOC_GLOBS = (
    "android-*.md",
    "samples/android/**/*.json",
    "samples/android/**/*.md",
)

KNOWN_ALIASES = {
    "/api/v1/config/app-bootstrap": "/api/v1/app-config/bootstrap",
    "/api/v1/profile/contract": "/api/v1/forms/profile-contract",
    "/api/v1/profile/readiness": "/api/v1/farmers/profile-readiness",
    "/api/v1/broadcasts/feed": "/api/v1/broadcasts/farmers/{farmer_id}/broadcasts",
}

ENDPOINT_RE = re.compile(r"/api/v1/[^\s`),;]+")
UUID_RE = re.compile(
    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?=/|$)"
)


def import_app():
    sys.path.insert(0, str(BACKEND_DIR))
    from app.main import app  # noqa: WPS433 - local CLI import

    return app


def endpoint_refs(text: str) -> set[str]:
    refs: set[str] = set()
    for match in ENDPOINT_RE.finditer(text):
        value = match.group(0).rstrip("`\"':.,);]")
        value = value.replace("\\", "")
        if "..." in value:
            continue
        refs.add(value)
    return refs


def normalize_endpoint(endpoint: str) -> str:
    path = endpoint.split("?", 1)[0]
    path = UUID_RE.sub("/{param}", path)
    path = re.sub(r"/\+?91[0-9]{10}(?=/|$)", "/{param}", path)
    path = re.sub(r"/[0-9]{10}(?=/|$)", "/{param}", path)
    path = re.sub(r"\{[^}/]+\}", "{param}", path)
    return path.rstrip("/") or path


def template_matches(endpoint: str, template: str) -> bool:
    path = endpoint.split("?", 1)[0].rstrip("/") or endpoint
    template_path = template.split("?", 1)[0].rstrip("/") or template
    pattern = re.escape(template_path)
    pattern = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", pattern)
    return bool(re.fullmatch(pattern, path))


def matches_any_template(endpoint: str, templates: Iterable[str]) -> bool:
    return any(template_matches(endpoint, template) for template in templates)


def doc_files() -> list[Path]:
    files = {ALLOWLIST_PATH}
    for pattern in ANDROID_DOC_GLOBS:
        files.update(DOCS_DIR.glob(pattern))
    return sorted(path for path in files if path.exists() and path.is_file())


def refs_by_file(paths: Iterable[Path]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in paths:
        refs = sorted(endpoint_refs(path.read_text(encoding="utf-8")))
        if refs:
            found[str(path.relative_to(ROOT))] = refs
    return found


def main() -> int:
    app = import_app()
    backend_paths = sorted(app.openapi().get("paths", {}).keys())
    docs = doc_files()
    refs = refs_by_file(docs)
    allowlist_refs = refs_by_file([ALLOWLIST_PATH]).get(
        str(ALLOWLIST_PATH.relative_to(ROOT)),
        [],
    )

    android_doc_refs = sorted({ref for values in refs.values() for ref in values})
    missing_from_backend = []
    missing_from_allowlist = []
    stale_alias_refs = []

    for file_name, file_refs in refs.items():
        for ref in file_refs:
            normalized = normalize_endpoint(ref)
            if not matches_any_template(ref, backend_paths):
                missing_from_backend.append(
                    {"file": file_name, "endpoint": ref, "normalized": normalized},
                )
            if not matches_any_template(ref, allowlist_refs):
                missing_from_allowlist.append(
                    {"file": file_name, "endpoint": ref, "normalized": normalized},
                )
            if ref.split("?", 1)[0] in KNOWN_ALIASES:
                stale_alias_refs.append(
                    {
                        "file": file_name,
                        "stale_endpoint": ref.split("?", 1)[0],
                        "replace_with": KNOWN_ALIASES[ref.split("?", 1)[0]],
                    },
                )

    result = {
        "schema_version": "android_endpoint_allowlist_audit.v1",
        "allowlist_path": str(ALLOWLIST_PATH),
        "backend_route_count": len(backend_paths),
        "allowlist_endpoint_count": len(allowlist_refs),
        "android_doc_endpoint_count": len(android_doc_refs),
        "known_aliases": KNOWN_ALIASES,
        "missing_from_backend": sorted(
            missing_from_backend,
            key=lambda row: (row["file"], row["endpoint"]),
        ),
        "missing_from_allowlist": sorted(
            missing_from_allowlist,
            key=lambda row: (row["file"], row["endpoint"]),
        ),
        "stale_alias_refs": sorted(
            stale_alias_refs,
            key=lambda row: (row["file"], row["stale_endpoint"]),
        ),
        "readiness": {
            "allowlist_parseable": ALLOWLIST_PATH.exists(),
            "no_known_stale_aliases": not stale_alias_refs,
        },
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if stale_alias_refs else 0


if __name__ == "__main__":
    raise SystemExit(main())
