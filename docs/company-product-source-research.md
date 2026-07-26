# Company Product Source Research and Scrape Risk Register

Status date: 2026-07-26

This document defines how Agri-OS should research, scrape, normalize, and review company/product/input data before it becomes trusted product catalog data.

The immediate goal is Android emulator testing and client-demo readiness. The production goal is a reviewable, auditable input catalog where product, dosage, crop, pest/disease, registration, and certification claims are traceable to source evidence.

## Starter discovery sources

Current starter sources:

- Screener fertilizers/agrochemicals sector page: https://www.screener.in/market/IN01/IN0101/IN010102/
- TNAU seed-industry directory PDF: https://agritech.tnau.ac.in/agricultural_marketing/pdf/Seed_Industries_India.pdf

Interpretation:

- Screener is a stock/sector tracker and should be used only to identify listed agrochemical, fertilizer, and broader agri-input companies.
- TNAU is a seed-company discovery source.
- Neither source is a dosage, label, registration, certification, or SKU source.
- Product truth must come from official company sites, product labels, regulator data, or other reviewable primary sources.

## Source trust hierarchy

Use this hierarchy whenever multiple sources disagree.

### Tier 0: regulator/legal source

Prefer this tier for legality, safety, label claims, and controlled product categories.

Examples:

- Central Insecticides Board and Registration Committee / National Portal reference: https://www.india.gov.in/category/agriculture-rural-environment/subcategory/resources-for-agriculture/details/central-insecticides-board-and-registration-committee
- Insecticides Act, 1968: https://www.indiacode.nic.in/handle/123456789/12865?view_type=browse
- Pesticide label and misbranding reference: https://www.pib.gov.in/newsite/PrintRelease.aspx?lang=2&reg=48&relid=124297
- Fertilizer Control Order context: https://www.pib.gov.in/newsite/PrintRelease.aspx?lang=2&reg=48&relid=186536
- Biostimulant regulation under FCO: https://www.pib.gov.in/newsite/erelcontent.aspx?lang=2&reg=48&relid=275777
- SATHI / SeedTrace portal: https://seedtrace.gov.in/ms014/english
- Seed quality/regulatory context: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2224590&lang=1&reg=3
- FSSAI pesticide data repository for pesticide/MRL reference, not product dosage: https://sites.fssai.gov.in/dataportal/

### Tier 1: official manufacturer source

Use for product existence, brand names, product pages, catalog PDFs, label PDFs, package details, product family, claimed composition, crops, target pests/diseases, dosage notes, and safety notes.

Accepted forms:

- official company website product pages;
- official company product catalog PDFs;
- official product label PDFs;
- official SDS/MSDS PDFs;
- official distributor catalog only when clearly linked from company site.

### Tier 2: government/academic/company-directory source

Use for company discovery and coarse classification, not product truth.

Examples:

- Screener sector lists;
- TNAU seed-industry PDF;
- ICAR/SAU public seed references;
- government service portals listing seed/fertilizer/dealer ecosystem data.

### Tier 3: marketplace/distributor/retailer source

Use only as weak discovery evidence. Do not trust for dosage, registration, certification, or legal label claims unless it links to official label/source.

## Input categories to cover

### Fertilizers and nutrients

- Bulk fertilizers: urea, DAP, MOP, NPK.
- Secondary nutrients: calcium, magnesium, sulphur.
- Micronutrients: zinc, boron, iron, manganese, copper, molybdenum.
- Water-soluble/fertigation fertilizers.
- Liquid fertilizers.
- Nano fertilizers, only where source/legal status is clear.

### Crop protection

- Insecticides.
- Fungicides.
- Herbicides/weedicides.
- Acaricides.
- Nematicides.
- Rodenticides.
- Molluscicides.
- Seed-treatment chemicals.

Important: pesticide dosage must be crop/pest/formulation-specific and should prefer approved label claims.

### Biological and organic-compatible inputs

- Biofertilizers: Rhizobium, Azotobacter, Azospirillum, PSB, KSB.
- Biopesticides: Trichoderma, Pseudomonas, Beauveria, Metarhizium, NPV.
- Biostimulants: seaweed extract, humic acid, amino acid, fulvic acid.
- Organic manure/products: compost, vermicompost, neem cake, castor cake, bone meal.

Important: biostimulants are separately regulated under FCO. Do not treat all biostimulant marketing claims as approved input claims.

### Natural farming inputs

- Jeevamrit.
- Beejamrit.
- Ghanjeevamrit.
- Panchagavya.
- Dashparni ark.
- Neemastra/Brahmastra-style preparations.

Important: natural farming inputs are distinct from organic-certified purchased products.

- `NATURAL`: natural-farming/on-farm or low-external-input preparations/practices.
- `ORGANIC`: externally supplied organic-compatible product where certification/evidence may still require verification.
- `BIO_INPUT`: microbial/biological input products.
- `CONVENTIONAL`: synthetic/mineral fertilizer and crop-protection products.
- `SEED`: seed or planting material.

### Application helpers and field consumables

- Spreaders.
- Stickers.
- Surfactants.
- Adjuvants.
- Wetting agents.
- pH correctors/water conditioners.
- Pheromone traps/lures.
- Sticky traps.
- Mulching film.
- Grow bags.
- Nursery media/cocopeat, where operationally relevant.

### Planting material

- Seeds.
- Saplings.
- Seedlings.
- Tubers.
- Cuttings.
- Rhizomes.
- Other crop-specific propagation material.

## Data fields to capture during scrape/review

Minimum company-level fields:

- manufacturer_code
- company_name
- official_website_url
- source_discovery_url
- company_segments
- company_type
- confidence
- review_status

Minimum product-level fields:

- manufacturer_code
- product_code
- brand_name
- canonical_input_code
- agriculture_type: CONVENTIONAL / ORGANIC / NATURAL / BIO_INPUT / SEED
- source_url
- source_notes
- source_text
- source_capture_status
- composition
- formulation
- registration_number
- registration_authority
- registration_expiry_date
- crops
- target_pests_or_diseases
- dosage_quantity
- dosage_unit
- dosage_area_unit
- application_method
- timing_note
- safety_note
- package_sizes
- label_pdf_url
- sds_pdf_url
- reviewed_by
- reviewed_at

Existing product metadata support:

- `source_url`
- `source_notes`
- `source_text`
- `source_capture_status`

These fields were intentionally added before scraping so scraped source evidence can be reviewed in admin UI.

## Multi-pass scrape workflow

### Pass 0: company queue

Input:

- seeded manufacturers;
- company discovery candidates;
- Screener/TNAU/source-list rows.

Output:

- company scrape queue with candidate company names, segments, and source-list evidence.

Do not scrape products in this pass.

### Pass 1: official website discovery

For each company:

- search for official website;
- reject similarly named unrelated companies;
- capture official website URL;
- capture confidence and reason.

Failure preemption:

- listed companies may use subsidiaries or product divisions;
- company names may be old, renamed, merged, or delisted;
- seed companies may have regional sites or no modern website.

### Pass 2: product index discovery

For each official website:

- find product/category/catalog pages;
- identify downloadable product catalog PDFs;
- identify seed/fertilizer/crop-protection category pages;
- capture product listing URLs.

Failure preemption:

- product pages may be JavaScript-rendered;
- product catalog may be PDF-only;
- product names may appear only in images;
- sites may block aggressive scraping;
- website category names may not match our canonical input taxonomy.

### Pass 3: product detail capture

For each product candidate:

- capture product page URL;
- capture visible text;
- capture label/catalog PDF URL if present;
- capture composition/formulation;
- capture crop, pest/disease, dosage, timing, safety, and package info where available.

Failure preemption:

- dosage can vary by crop, pest, formulation, and application method;
- marketing pages may omit legal dosage;
- product pages may have stale data;
- label PDFs may be scanned images requiring OCR;
- product names may be reused across formulations.

### Pass 4: normalization

Normalize into Agri-OS concepts:

- manufacturer;
- branded product;
- canonical input;
- package/SKU;
- crop-stage dosage rule;
- advisory-safe usage note;
- source evidence.

Failure preemption:

- do not infer canonical input from brand name alone;
- distinguish product brand from active ingredient;
- preserve raw source text;
- never overwrite reviewed data without diff/audit;
- mark ambiguous rows as `MANUAL_REVIEW`.

### Pass 5: human review

Admin reviewer should verify:

- official source URL;
- product identity;
- composition/formulation;
- dosage/crop/pest mapping;
- organic/natural/bio/conventional classification;
- label/regulator evidence;
- package size;
- whether product is demo-only or trusted.

Only reviewed rows should be promoted from demo/source-captured state to production-ready state.

## Known failure modes and controls

### Wrong company website

Risk: search results may point to distributors, similarly named entities, or old domains.

Control:

- store discovery source separately from official website;
- keep website confidence and reason;
- require manual review before trusting product data.

### Product names without dosage

Risk: many company pages list products but omit dosage.

Control:

- allow product row with source text but leave dosage blank;
- mark source_capture_status as `MANUAL_REVIEW`;
- prefer label/regulator sources for dosage.

### Dosage varies by context

Risk: one product may have different doses by crop, pest, disease, soil, stage, formulation, or application method.

Control:

- model dosage as crop-stage/input rule, not just product-level text;
- keep raw label/source text;
- do not collapse all dosages to a single product default.

### Organic vs natural confusion

Risk: marketing words such as organic, bio, residue-free, and natural can be mixed.

Control:

- `NATURAL` is for natural-farming/on-farm/low-external-input practices.
- `ORGANIC` is for organic-compatible purchased products, subject to evidence.
- `BIO_INPUT` is for microbial/biological input products.
- Certification evidence must be stored separately; do not infer certification from marketing text.

### Biostimulant legal status

Risk: biostimulants have a specific regulatory context under FCO.

Control:

- capture product source and regulatory evidence;
- do not treat unverified biostimulant products as approved.

### Seed variety and region ambiguity

Risk: seeds depend on crop, variety/hybrid, season, region, maturity duration, disease resistance, and certification/traceability.

Control:

- use SATHI/SeedTrace and official seed-company sources where possible;
- capture crop/variety/season/region separately;
- distinguish seed company from seed variety.

### PDF and OCR issues

Risk: labels/catalogs may be scanned, tables may be malformed, dosage units may be split across rows.

Control:

- preserve original source URL and raw extracted text;
- flag OCR-derived data;
- require manual review before dosage import.

### Unit normalization

Risk: dosage units appear as ml/acre, litre/ha, gm/litre water, kg/acre, packets/acre, seed rate kg/ha, etc.

Control:

- store raw dosage text;
- normalize only when unit conversion is safe;
- keep dosage_area_unit and application_method.

### Discontinued or renamed products

Risk: product pages and company catalogs change.

Control:

- store captured_at timestamp in later scrape queue;
- keep source_capture_status;
- never delete blindly; mark inactive/discontinued after review.

### Retail price/MRP volatility

Risk: price and package data changes frequently.

Control:

- do not use scraped price as stable catalog truth unless source/date is stored;
- store effective date and source if price is captured.

## Recommended next engineering module

Build a `company_product_scrape_plan` utility that emits a review queue instead of scraping products immediately.

Recommended output:

- `data/staged/company_product_sources/YYYYMMDDTHHMMSSZ/company_scrape_plan.json`
- `company_code`
- `company_name`
- `segments`
- `source_list_references`
- `suggested_search_queries`
- `official_website_url`
- `official_website_confidence`
- `product_index_urls`
- `review_status`
- `notes`

This should be reviewed manually before any product-detail scrape.
