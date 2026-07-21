#!/usr/bin/env python3
"""Preflight clean database bootstrap validation.

Default mode is read-only. It reports whether this environment appears able
to run a temporary PostgreSQL bootstrap validation later.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from urllib.parse import urlparse


def main() -> int:
    database_url = os.environ.get('DATABASE_URL') or ''
    parsed = urlparse(database_url) if database_url else None
    scheme = parsed.scheme if parsed else None
    host = parsed.hostname if parsed else None
    db_name = parsed.path.lstrip('/') if parsed and parsed.path else None

    createdb = shutil.which('createdb')
    dropdb = shutil.which('dropdb')
    psql = shutil.which('psql')

    print('=' * 72)
    print('CLEAN DB BOOTSTRAP PREFLIGHT')
    print('=' * 72)
    print(f'DATABASE_URL_present={bool(database_url)}')
    print(f'DATABASE_URL_scheme={scheme}')
    print(f'DATABASE_URL_host={host}')
    print(f'DATABASE_URL_db={db_name}')
    print(f'createdb_available={bool(createdb)} path={createdb}')
    print(f'dropdb_available={bool(dropdb)} path={dropdb}')
    print(f'psql_available={bool(psql)} path={psql}')

    if scheme not in {'postgresql', 'postgresql+psycopg2', 'postgres'}:
        print('status=NOT_READY reason=DATABASE_URL is not PostgreSQL or is missing')
        return 0

    if not createdb or not dropdb:
        print('status=NOT_READY reason=createdb/dropdb command not available')
        return 0

    print('status=READY_FOR_MANUAL_TEMP_DB_BOOTSTRAP')
    print('Suggested later command after review:')
    print('  ../venv/bin/python scripts/check_clean_db_bootstrap.py --execute')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
