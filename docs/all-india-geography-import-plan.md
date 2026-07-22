# All-India Geography Import Plan

## Goal

Expand current one-state geography coverage to all-India while keeping LGD canonical, PIN-code coverage refreshable, Census enrichments separate, and Android-compatible APIs stable.

## Current baseline

- Existing current tables remain stable for Android MVP: states, districts, blocks/sub-districts, villages/localities.
- Current data is deep for one state but not all-India.
- Existing UP acquisition/import scripts should be reused for parsing patterns, but refactored before broader imports.
- OGD source probe exists and is read-only until a Data.gov.in API key is configured.

## Import phases

### Phase 0: Source probe

- Run `backend/scripts/probe_ogd_geography_sources.py` with no API key to verify setup behavior.
- After key generation, run with `--limit 1 --include-sample` to capture field names and sample keys.
- Do not write DB rows during probing.

### Phase 1: Raw snapshot acquisition

- Fetch LGD villages-with-PIN and All India PIN-code directory pages into timestamped raw files.
- Store source resource id, source URL, retrieval timestamp, license, row count, page count, and checksum.
- Do not overwrite prior raw snapshots.

### Phase 2: Staging validation

- Normalize column names from source-specific fields into internal staging fields.
- Validate required identifiers: state, district, sub-district/block/locality/village where present, LGD codes where present, PIN/post-office fields where present.
- Detect duplicates, missing parent references, invalid PIN formats, and conflicting canonical names.
- Emit a validation summary and block apply if critical errors exceed threshold.

### Phase 3: Diff

- Compare staged LGD rows with current local geography rows.
- Classify rows as `NEW`, `UNCHANGED`, `UPDATED`, `SOURCE_MISSING`, `CONFLICT`, or `ALIAS_ONLY`.
- Compare PIN/post-office rows separately because postal coverage is many-to-many and may not align one-to-one with LGD villages.

### Phase 4: Apply

- Admin/backoffice only.
- Record import batch id, actor, reason, source snapshot ids, validation result, and diff summary.
- Insert new canonical LGD rows.
- Update changed source fields only through import/versioning, not ad-hoc UI edits.
- Expire source-missing rows logically by status/effective dates; do not physically delete by default.
- Upsert aliases and PIN associations separately.

### Phase 5: Runtime serving

- Android and web runtime should use local DB/API responses, not live OGD calls.
- Keep compatibility endpoints stable while generic global geography model evolves.
- Expose source metadata and freshness to admin readiness screens.

## LGD, Census, and PIN precedence

1. LGD controls official administrative identity and canonical codes.
2. India Post / OGD PIN directory controls postal/post-office associations.
3. Census enriches aliases, census location codes, population/demographic indicators, and business-opportunity analytics.
4. Census-only settlements should be represented as reference/enrichment/locality candidates, not as LGD-canonical villages unless reconciled to LGD.

## Delete/expiry rule

No geography import should physically delete rows in normal operation. Missing records should be expired or archived with source metadata so historical crop cycles, farmers, parcels, audits, and reports remain explainable.

## First implementation slice

1. Add a raw snapshot fetcher that requires `DATA_GOV_IN_API_KEY` and writes JSON pages under a date/resource directory.
2. Add a staging parser that reads saved JSON only and emits normalized CSV/JSONL plus validation summary.
3. Add an audit script that reports all-India coverage readiness without applying DB changes.
4. Only after review, add admin-approved apply mode.

## Raw snapshot fetcher

`backend/scripts/fetch_ogd_geography_snapshots.py` is the first implementation slice for Phase 1. It requires `DATA_GOV_IN_API_KEY` unless `--dry-run` is passed, writes timestamped raw JSON pages and a manifest, and does not touch database rows.

## Local raw snapshot storage

Generated OGD raw snapshots under `data/raw/ogd_geography/` are intentionally gitignored because they may be large and are source-acquisition artifacts. Commit manifests or summarized audit outputs only when they are explicitly curated for review.

## Raw snapshot validator

`backend/scripts/validate_ogd_geography_snapshot.py` validates saved raw snapshot manifests/pages without database writes. It reports field names, likely PIN/LGD/name fields, invalid PIN examples, and whether the fetched data is safe enough to design staging transforms.

## API-key pending status

The acquisition tooling is ready, but the first live source inspection is blocked until `DATA_GOV_IN_API_KEY` is available. This is expected; missing-key runs produce manifests/status output and do not fail the local development workflow.
