#!/usr/bin/env python3
"""Run backend provider worker stubs for a tenant."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.modules.media.weather_api import _run_due_weather_refresh_worker
from app.modules.farmer.soil_profile import _run_soil_enrichment_queue_worker


def main() -> int:
    parser = argparse.ArgumentParser(description='Run due backend provider worker stubs.')
    parser.add_argument('--tenant-id', required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--skip-weather', action='store_true')
    parser.add_argument('--skip-soil', action='store_true')
    parser.add_argument('--provider-code')
    parser.add_argument('--missing', default='ANY', choices=['ANY', 'BASELINE', 'MOISTURE'])
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = {
            'schema_version': 'provider_worker_run.v1',
            'tenant_id': args.tenant_id,
            'dry_run': args.dry_run,
            'weather': None,
            'soil_enrichment': None,
        }

        if not args.skip_weather:
            result['weather'] = _run_due_weather_refresh_worker(
                db,
                tenant_id=args.tenant_id,
                dry_run=args.dry_run,
                provider_code=args.provider_code,
                limit=args.limit,
            )

        if not args.skip_soil:
            result['soil_enrichment'] = _run_soil_enrichment_queue_worker(
                db,
                tenant_id=args.tenant_id,
                dry_run=args.dry_run,
                missing=args.missing,
                limit=args.limit,
            )

        print(json.dumps(result, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == '__main__':
    raise SystemExit(main())
