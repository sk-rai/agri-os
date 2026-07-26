# Company and Product Catalog Starter Seed

Status date: 2026-07-26

This starter seed gives local admin and Android testing a broader company/manufacturer and representative product catalog. It is intentionally a demo/reference seed, not a production regulatory product registry.

## Sources

- Screener fertilizers/agrochemicals sector page: https://www.screener.in/market/IN01/IN0101/IN010102/
- TNAU AgriTech seed-industry directory PDF: https://agritech.tnau.ac.in/agricultural_marketing/pdf/Seed_Industries_India.pdf

These are used as company-directory references only. Screener is a stock/sector tracker, not a product-label source. Exact product labels, dosage, registrations, prices, and certifications must be captured later from each manufacturer website, product label, or regulator source and reviewed before trust.

## Apply command

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/seed_company_product_catalog.py --tenant-id default --apply
```

The script is idempotent. A second apply should update existing seeded rows rather than duplicating products, packages, manufacturers, or discovery candidates.

## What it seeds

- manufacturers from fertilizer/agrochemical and seed-company starter lists;
- company discovery candidates for admin review;
- default tenant company-profile config describing catalog-readiness and input-classification policy;
- canonical inputs for seed, organic, natural-farming, and biological product examples;
- representative product/package rows across:
  - conventional fertilizer/crop-protection;
  - seed;
  - organic-compatible inputs;
  - natural-farming/on-farm preparations;
  - biological/bio-input products.

## Organic vs natural distinction

Agri-OS tracks these separately:

- `ORGANIC`: external products that may be compatible with organic systems, but certification/evidence must be verified separately.
- `NATURAL`: natural-farming/on-farm or minimal-purchased preparations such as Jeevamrit/Beejamrit.
- `BIO_INPUT`: biological or microbial input products such as Azospirillum/PSB.
- `CONVENTIONAL`: synthetic/mineral fertilizer and crop-protection products.
- `SEED`: seed/planting material.

The current seed stores this under product metadata fields:

- `agriculture_type`
- `input_origin`
- `farming_system_tags`

If Android/admin needs first-class filters later, these metadata fields can be promoted into explicit columns or indexed read models.

## Company-site product capture workflow

Because every manufacturer website structures products differently, product enrichment should run in multiple passes:

1. Use Screener/TNAU/local references to identify candidate companies and map them to manufacturer rows.
2. For each manufacturer, find the official company website and product pages.
3. Capture source URL, dosage/label notes, and raw useful source text into product metadata fields: `source_url`, `source_notes`, and `source_text`.
4. Review captured text in admin UI before marking product rows as production-ready.
5. Distinguish `ORGANIC`, `NATURAL`, `BIO_INPUT`, `CONVENTIONAL`, and `SEED`; do not infer organic certification from marketing text alone.

## Verification commands

```bash
cd ~/projects/farmint/backend
../venv/bin/python -m py_compile scripts/seed_company_product_catalog.py
../venv/bin/python scripts/seed_company_product_catalog.py --tenant-id default
../venv/bin/python scripts/audit_product_catalog_readiness.py
```

Expected local starter result after apply:

- 39 manufacturers total;
- 31 products total;
- 36 seeded company discovery candidates;
- seeded product mix: 11 conventional, 5 seed, 2 organic, 2 natural, 2 bio-input.
