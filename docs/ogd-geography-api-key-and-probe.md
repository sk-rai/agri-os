# OGD Geography API Key and Probe

## Purpose

Provide a safe first step for examining India OGD geography/PIN-code resources before building the all-India import pipeline.

## Resources

- LGD villages with PIN codes: `f17a1608-5f10-4610-bb50-a63c80d83974`
- All India PIN-code directory: `5c2f62fe-5afa-4119-a499-fec9d604d5bd`
- License: Government Open Data License - India

## API key handling

Do not commit API keys. Set the key only in the local shell/session:

```bash
export DATA_GOV_IN_API_KEY='your-key-here'
```

The probe also accepts `OGD_API_KEY` as a fallback environment variable.

## Probe commands

Without a key, this prints setup guidance and exits successfully:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/probe_ogd_geography_sources.py
```

After key generation, fetch one row from each resource for schema inspection:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/probe_ogd_geography_sources.py --limit 1 --include-sample
```

## Runtime decision

Agri-OS should replicate validated source snapshots locally rather than call live OGD APIs from Android/runtime flows. Local replication gives offline support, predictable latency, auditability, source checksums, replayable imports, and protection from upstream rate limits or schema drift.

Live API calls should be limited to acquisition jobs, admin preview/diff screens, and scheduled refresh probes.

## Next step after probe

Use the field names and sample records to design a staged all-India import: detect, validate, stage, diff, apply, and logically expire missing records rather than physically deleting geography rows.

