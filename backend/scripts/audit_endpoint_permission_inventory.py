#!/usr/bin/env python3
"""Static endpoint permission inventory for Android/backend handoff.

This is a lightweight source scanner, not a security proof. It helps us
find endpoints that should be classified as Android, Admin, or Worker/Ops
and flags handlers missing obvious tenant/admin dependency markers.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app'

METHODS = {'get', 'post', 'put', 'patch', 'delete'}
ANDROID_HINTS = ('broadcasts/feed', 'broadcasts/{', 'forms', 'farmers/profile-readiness', 'field-agent/worklist')
WORKER_HINTS = ('worker', 'operations/health', 'refresh-plan', 'jobs/audit', 'enrichments/queue')
ADMIN_HINTS = ('tenants', 'projects', 'users', 'company', 'imports', 'csv', 'providers')


def literal(value):
    try:
        return ast.literal_eval(value)
    except Exception:
        return None


def decorator_route(decorator: ast.AST) -> tuple[str, str] | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in METHODS:
        return None
    if not decorator.args:
        return None
    path = literal(decorator.args[0])
    if not isinstance(path, str):
        return None
    return func.attr.upper(), path


def classify(path: str, func_name: str) -> str:
    text = f'{path} {func_name}'.lower()
    if any(hint in text for hint in WORKER_HINTS):
        return 'WORKER_OPS'
    if any(hint in text for hint in ANDROID_HINTS):
        return 'ANDROID_OR_SHARED'
    if any(hint in text for hint in ADMIN_HINTS):
        return 'ADMIN_OR_BACKOFFICE'
    return 'SHARED_REVIEW'


def has_tenant_marker(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    text = ast.unparse(node)
    return 'X-Tenant-ID' in text or 'x_tenant_id' in text or 'tenant_id' in text


def has_admin_marker(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    text = ast.unparse(node)
    return 'require_admin_permission' in text or 'AdminPermission' in text or 'AdminPrincipal' in text


def scan_file(path: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    except SyntaxError as exc:
        return [{'file': str(path.relative_to(ROOT)), 'error': str(exc)}]
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            route = decorator_route(decorator)
            if not route:
                continue
            method, route_path = route
            audience = classify(route_path, node.name)
            tenant = has_tenant_marker(node)
            admin = has_admin_marker(node)
            flags = []
            if audience in {'ADMIN_OR_BACKOFFICE', 'WORKER_OPS'} and not admin:
                flags.append('REVIEW_ADMIN_PERMISSION')
            if not tenant:
                flags.append('REVIEW_TENANT_SCOPE')
            rows.append({
                'file': str(path.relative_to(ROOT)),
                'line': node.lineno,
                'method': method,
                'path': route_path,
                'function': node.name,
                'audience': audience,
                'tenant_marker': tenant,
                'admin_marker': admin,
                'flags': flags,
            })
    return rows


def main() -> int:
    rows = []
    for path in sorted(APP.rglob('*.py')):
        if path.name.startswith('__'):
            continue
        rows.extend(scan_file(path))

    flagged = [row for row in rows if row.get('flags')]
    print('=' * 72)
    print('ENDPOINT PERMISSION INVENTORY')
    print('=' * 72)
    print(f'endpoint_count={len([r for r in rows if "method" in r])}')
    print(f'flagged_count={len(flagged)}')
    print('')
    for row in flagged[:120]:
        print(f"{row['file']}:{row['line']} {row['method']} {row['path']} -> {row['audience']} flags={','.join(row['flags'])}")
    if len(flagged) > 120:
        print(f'... {len(flagged) - 120} more flagged endpoints')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
