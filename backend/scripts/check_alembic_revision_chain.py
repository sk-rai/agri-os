#!/usr/bin/env python3
"""Validate local Alembic revision files have one unique head.

This is a static safety check. It does not connect to the database.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / 'alembic' / 'versions'


def literal_assignments(path: Path) -> dict[str, object]:
    text = path.read_text(encoding='utf-8-sig')
    tree = ast.parse(text)
    values: dict[str, object] = {}
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value_node = node.value
        else:
            continue

        for target in targets:
            if target in {'revision', 'down_revision'} and value_node is not None:
                values[target] = ast.literal_eval(value_node)

    # Older revisions may use unusual formatting; fall back to simple regex.
    for key in ['revision', 'down_revision']:
        if key not in values:
            match = re.search(rf"^\\s*{key}\\s*=\\s*(['\\\"])(.*?)\\1", text, re.MULTILINE)
            if match:
                values[key] = match.group(2)

    return values


def as_down_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (tuple, list)):
        return [str(item) for item in value if item]
    return [str(value)]


def main() -> int:
    revisions: dict[str, Path] = {}
    down_revisions: dict[str, list[str]] = {}

    for path in sorted(VERSIONS.glob('*.py')):
        if path.name == '__init__.py':
            continue
        values = literal_assignments(path)
        revision = values.get('revision')
        if not revision:
            raise SystemExit(f'{path}: missing revision')
        revision = str(revision)
        if revision in revisions:
            raise SystemExit(f'duplicate revision {revision}: {revisions[revision]} and {path}')
        revisions[revision] = path
        down_revisions[revision] = as_down_list(values.get('down_revision'))

    referenced = {down for downs in down_revisions.values() for down in downs}
    missing = sorted(ref for ref in referenced if ref not in revisions)
    if missing:
        raise SystemExit(f'missing down_revision targets: {missing}')

    heads = sorted(revision for revision in revisions if revision not in referenced)
    if len(heads) != 1:
        details = ', '.join(f'{head} ({revisions[head].name})' for head in heads)
        raise SystemExit(f'expected exactly one Alembic head, found {len(heads)}: {details}')

    print('=' * 72)
    print('ALEMBIC REVISION CHAIN VALIDATED')
    print('=' * 72)
    print(f'revision_count={len(revisions)}')
    print(f'head={heads[0]} ({revisions[heads[0]].name})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
