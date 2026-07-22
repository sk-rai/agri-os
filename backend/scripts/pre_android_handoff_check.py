#!/usr/bin/env python3
"""Run backend-side pre-Android handoff checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def run(label: str, args: list[str], *, cwd: Path = ROOT) -> None:
    print('\n' + '=' * 72)
    print(label)
    print('=' * 72)
    result = subprocess.run(args, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(f'{label} failed with exit code {result.returncode}')


def main() -> int:
    print('=' * 72)
    print('PRE-ANDROID BACKEND HANDOFF CHECK')
    print('=' * 72)
    print('This command is read-only. Review git status before and after.')

    run('Git status', ['git', 'status', '--short', '--branch'], cwd=REPO)
    run('Recent commits', ['git', 'log', '--oneline', '-5'], cwd=REPO)
    run('Alembic heads', ['../venv/bin/alembic', 'heads'])
    run('Alembic current', ['../venv/bin/alembic', 'current'])
    run('Static Alembic revision chain', [sys.executable, 'scripts/check_alembic_revision_chain.py'])
    run('Clean DB bootstrap preflight', [sys.executable, 'scripts/check_clean_db_bootstrap_preflight.py'])
    run('Metadata readiness audit', [sys.executable, 'scripts/audit_metadata_readiness.py'])
    run('Product catalog readiness audit', [sys.executable, 'scripts/audit_product_catalog_readiness.py'])
    run('Season land-unit readiness audit', [sys.executable, 'scripts/audit_season_land_unit_readiness.py'])
    run('Workflow BBCH crop-system readiness audit', [sys.executable, 'scripts/audit_workflow_bbch_crop_system_readiness.py'])
    run('Global geography readiness audit', [sys.executable, 'scripts/audit_global_geography_readiness.py'])
    run('Android backend closeout regression sweep', [sys.executable, 'scripts/test_android_backend_closeout.py'])

    print('\n' + '=' * 72)
    print('MANUAL FOLLOW-UP REQUIRED')
    print('=' * 72)
    print('Run web build separately:')
    print('  cd ~/projects/farmint/web')
    print('  npm run build')
    print('')
    print('If this script and web build pass, backend is ready for final sample payload packaging/review.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
