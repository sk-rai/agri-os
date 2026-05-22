# Master Data Implementation Plan
# Agricultural Operations Intelligence Platform

**Status:** ACTIVE — Sprint 1 Starting Point  
**Date:** May 22, 2026  
**Purpose:** Define the master data tables, data sources, acquisition strategy, and implementation sequence.

---

## 1. Master Data Categories (Implementation Order)

| Priority | Category | Tables | Data Source | MVP Scope |
|----------|----------|--------|-------------|-----------|
| 1 | Geography | states, districts, blocks/tehsils, villages | LGD (lgdirectory.gov.in), Census 2011 | Start with 1 state (pilot) |
| 2 | Crop Master | crops, crop_varieties, lifecycle_templates, stages | ICAR, agriculture universities, public catalogs | Top 10 crops for pilot state |
| 3 | Soil | soil_types, soil_parameters | ICAR-NBSS&LUP | Static reference data |
| 4 | Seasons | seasons, cropping_patterns | Standard Indian agricultural calendar | Kharif, Rabi, Zaid |
| 5 | Inputs | fertilizers, pesticides, seeds, manufacturers | Public company catalogs, ministry data | Top products for pilot crops |

---

## 2. Geography Master — Schema Design

### Hierarchy: State → District → Block/Tehsil → Village

```yaml
geography_states:
  id: UUID (PK)
  lgd_code: STRING (unique, indexed) — from Local Government Directory
  canonical_name: STRING (NOT NULL)
  census_name: STRING (may differ from LGD name)
  aliases: JSONB (array of alternate names including local language)
  is_active: BOOLEAN (default true)
  version: STRING (semver)
  created_at, updated_at: TIMESTAMP WITH TIMEZONE

geography_districts:
  id: UUID (PK)
  lgd_code: STRING (unique, indexed)
  state_id: UUID (FK → geography_states)
  canonical_name: STRING (NOT NULL)
  census_name: STRING
  aliases: JSONB
  is_active, version, created_at, updated_at

geography_blocks:
  id: UUID (PK)
  lgd_code: STRING (unique, indexed)
  district_id: UUID (FK → geography_districts)
  canonical_name: STRING (NOT NULL)
  aliases: JSONB (includes tehsil/taluka/mandal names)
  is_active, version, created_at, updated_at

geography_villages:
  id: UUID (PK)
  lgd_code: STRING (unique, indexed)
  block_id: UUID (FK → geography_blocks)
  district_id: UUID (FK → geography_districts) — denormalized for query performance
  canonical_name: STRING (NOT NULL)
  census_name: STRING
  census_village_code: STRING
  pin_codes: ARRAY(STRING) — GIN indexed
  latitude: DECIMAL(10,8)
  longitude: DECIMAL(11,8)
  aliases: JSONB
  is_active, version, created_at, updated_at

  indexes:
    - idx_village_block (block_id)
    - idx_village_district (district_id)
    - idx_village_pin (pin_codes) — GIN
    - idx_village_search (canonical_name) — GIN with pg_trgm for fuzzy search
```

### Required PostgreSQL Extensions
- `postgis` — geospatial operations
- `pg_trgm` — trigram fuzzy text search

---

## 3. Data Acquisition Strategy

### Sources

| Source | Data | Access Method | Notes |
|--------|------|---------------|-------|
| LGD (lgdirectory.gov.in) | States, districts, blocks, villages with LGD codes | Web scraping (respectful, rate-limited) | Authoritative government source |
| Census 2011 | Village codes, population, coordinates | Downloadable CSV from census.gov.in | Cross-reference with LGD |
| India Post / ArcGIS | PIN codes per village | Public datasets | Enrichment layer |
| ICAR | Crop data, soil classification | Published research, public databases | Manual curation initially |

### Acquisition Rules

```yaml
acquisition_rules:
  - rate_limit: minimum 2 seconds between requests to government servers
  - retry: exponential backoff, max 3 retries
  - output: raw CSV → processed CSV → database insert
  - validation: cross-reference LGD with Census for name matching (fuzzy, threshold ≥85%)
  - pilot_first: start with ONE state, validate pipeline, then scale
  - idempotent: re-running scripts should not create duplicates (upsert by lgd_code)
```

---

## 4. Pilot Strategy

**Pilot State:** To be decided based on your village location (likely UP, Maharashtra, or Karnataka)

**Pilot Scope:**
- All districts in pilot state
- All blocks in pilot state
- All villages in pilot state
- Top 5-10 crops grown in pilot state
- Relevant lifecycle templates for those crops

**Success Criteria:**
- Geography dropdown populates in <200ms offline
- Fuzzy search returns correct village for ≥90% of test queries
- Delta sync updates cache without data loss
- Farmers can be enrolled using offline geography selection

---

## 5. Implementation Sequence

```yaml
sprint_1_master_data:

  day_1_2:
    - initialize project repo and folder structure
    - set up PostgreSQL database (isolated from other DBs)
    - create Alembic migration framework
    - create geography tables with extensions (PostGIS, pg_trgm)

  day_3_4:
    - write LGD data acquisition script (pilot state only)
    - write Census cross-reference script
    - populate geography tables for pilot state

  day_5_6:
    - create crop_master, crop_varieties, lifecycle_templates tables
    - seed with pilot state crops (manual curation initially)
    - create soil_types reference table

  day_7:
    - create master data API endpoints (GET states, districts, villages, crops)
    - create delta sync endpoint
    - validate with API tests
```

---

## 6. Database Isolation

The farmint database MUST be isolated from other databases on the same PostgreSQL instance:

```yaml
database_isolation:
  database_name: farmint_dev (development), farmint_prod (production)
  user: farmint_user (dedicated user, not shared with other projects)
  schema: public (for now; schema-per-tenant when multi-tenant needed)
  extensions: postgis, pg_trgm (installed in farmint database only)
  
  connection_string: postgresql://farmint_user:password@localhost:5432/farmint_dev
```

---

*End of Master Data Implementation Plan*
