#!/usr/bin/env python3
"""Execute clean temporary database bootstrap validation.

Requires --execute. Creates a random temporary PostgreSQL database, runs
`alembic upgrade head` against it, and drops the temp database in finally.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import uuid
from urllib.parse import unquote, urlparse, urlunparse


def replace_db_name(database_url: str, db_name: str) -> str:
    parsed = urlparse(database_url)
    return urlunparse(parsed._replace(path='/' + db_name))


def postgres_cli_env(database_url: str) -> dict:
    parsed = urlparse(database_url)
    env = dict(os.environ)
    if parsed.hostname:
        env["PGHOST"] = parsed.hostname
    if parsed.port:
        env["PGPORT"] = str(parsed.port)
    if parsed.username:
        env["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    return env


def run(args: list[str], *, env: dict | None = None) -> None:
    print('+ ' + ' '.join(args))
    result = subprocess.run(args, env=env)
    if result.returncode != 0:
        raise SystemExit(f'command failed with exit code {result.returncode}: {args}')


def main() -> int:
    parser = argparse.ArgumentParser(description='Run clean temp DB Alembic bootstrap validation.')
    parser.add_argument('--execute', action='store_true', help='Actually create/drop temp DB and run migrations.')
    parser.add_argument('--keep-db', action='store_true', help='Do not drop temp DB after run; for debugging only.')
    args = parser.parse_args()

    if not args.execute:
        print('Refusing to run without --execute.')
        print('This script creates and drops a temporary PostgreSQL database.')
        return 2

    database_url = os.environ.get('DATABASE_URL') or ''
    if not database_url:
        raise SystemExit('DATABASE_URL is required')

    parsed = urlparse(database_url)
    if parsed.scheme not in {'postgresql', 'postgresql+psycopg2', 'postgres'}:
        raise SystemExit(f'DATABASE_URL must be PostgreSQL, got scheme={parsed.scheme}')

    source_db = parsed.path.lstrip('/')
    if not source_db:
        raise SystemExit('DATABASE_URL must include database name')

    createdb = shutil.which('createdb')
    dropdb = shutil.which('dropdb')
    if not createdb or not dropdb:
        raise SystemExit('createdb/dropdb must be available')

    temp_db = f'agrios_bootstrap_{uuid.uuid4().hex[:10]}'
    temp_url = replace_db_name(database_url, temp_db)
    env = dict(os.environ)
    env['DATABASE_URL'] = temp_url
    pg_env = postgres_cli_env(database_url)

    print('=' * 72)
    print('CLEAN TEMP DB BOOTSTRAP VALIDATION')
    print('=' * 72)
    print(f'source_db={source_db}')
    print(f'temp_db={temp_db}')
    print(f'pg_host={parsed.hostname or "local-socket"}')
    print(f'pg_port={parsed.port or "default"}')
    print(f'pg_user={unquote(parsed.username) if parsed.username else "default-os-user"}')

    try:
        run([createdb, temp_db], env=pg_env)
        run(['../venv/bin/alembic', 'upgrade', 'head'], env=env)
        run(['../venv/bin/alembic', 'current'], env=env)
        print('=' * 72)
        print('Clean temp DB bootstrap validated')
        print('=' * 72)
    finally:
        if args.keep_db:
            print(f'Keeping temp DB for debugging: {temp_db}')
        else:
            run([dropdb, '--if-exists', temp_db], env=pg_env)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
