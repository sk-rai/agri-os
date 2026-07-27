# Product Source Verification Runbook

Status date: 2026-07-27

This runbook defines how product catalog rows graduate from demo/reference data to reviewed or verified product data.

## Current local audit result

Read-only audit script:

    backend/scripts/audit_product_source_verification_readiness.py

Latest local result:

- agricultural products: 31;
- agricultural inputs: 40;
- manufacturers: 39;
- product rows with source URL: 0;
- product rows with source text: 0;
- product rows with label URL: 0;
- product rows with registration number: 0;
- product rows with review/verification status: 0;
- ready for demo/reference catalog: yes;
- ready for manufacturer-verified catalog: no;
- ready for dosage claims: no;
- ready for organic/natural claims: no.

## Source hierarchy

Use source evidence in this order when claims matter:

1. regulator registration or official label;
2. official manufacturer product label/catalog PDF;
3. official manufacturer product page;
4. official distributor/dealer page only as secondary evidence;
5. discovery sources such as Screener/TNAU only for company discovery, not product truth.

## Product trust lifecycle

### DEMO_REFERENCE

Use when:

- row is seeded for Android emulator or demo flows;
- source evidence is missing or incomplete;
- product must not be presented as verified.

Allowed claims:

- product/input category;
- broad demo display name;
- manufacturer association if seeded from local reference data.

Not allowed:

- dosage claims;
- certification claims;
- regulator-approved claims;
- organic/natural claims unless explicitly evidence-backed.

### SOURCE_CAPTURED

Use when:

- official source URL or source text is captured;
- source has not yet been manually reviewed.

Required evidence:

- `source_url` or source reference;
- captured text or reviewer note.

### MANUAL_REVIEW

Use when:

- source evidence exists;
- a human reviewer must verify product identity, composition, dosage, certification, or registration.

Required reviewer checks:

- product name matches source;
- manufacturer identity is correct;
- formulation/composition is clear;
- crop/pest/disease claims are source-backed;
- dosage varies by crop/application where applicable;
- organic/natural classification is evidence-backed.

### VERIFIED_FOR_DEMO

Use when:

- source evidence is manually reviewed enough for client demo;
- still not necessarily regulator/label verified.

Allowed claims:

- source-backed product description;
- source-backed broad usage context.

Avoid:

- legal dosage unless label/regulator source is reviewed;
- certification claims unless certificate/regulator source is reviewed.

### REGULATOR_OR_LABEL_VERIFIED

Use when:

- regulator registration, approved label, or manufacturer label/catalog is reviewed;
- dosage/composition/crop claims are traceable to the reviewed source.

Allowed claims:

- source-backed dosage;
- source-backed composition;
- source-backed crop/pest/application timing;
- reviewed certification/registration details.

## Organic vs natural distinction

Keep `ORGANIC` and `NATURAL` separate.

### ORGANIC

Means externally supplied organic-compatible or organic-certified product.

Requires evidence such as:

- certification;
- official product label;
- regulator-approved organic input listing;
- manufacturer documentation with review notes.

### NATURAL

Means natural-farming, on-farm, or low-external-input practice/product.

Examples:

- Jeevamrit;
- Beejamrit;
- Ghanjeevamrit;
- Panchagavya;
- Dashparni ark;
- Neemastra/Brahmastra-style preparations.

Natural does not mean certified organic. Natural/on-farm recipes should not be mixed with externally supplied organic-certified products.

## Dosage policy

Do not show dosage as verified unless one of these is reviewed:

- regulator label;
- product label PDF;
- manufacturer catalog with crop/application-specific dosage;
- official package-of-practices source.

Dosage can vary by:

- crop;
- pest/disease/nutrient deficiency;
- formulation;
- application method;
- crop stage;
- geography;
- water volume;
- safety/pre-harvest interval.

## Scrape policy

Do not scrape products aggressively.

Use reviewed passes:

1. official website discovery;
2. product index discovery;
3. product detail capture;
4. source text extraction;
5. manual review;
6. promotion to verified status only after review.

## Android/demo rule

Android may display demo/reference products only if the UI does not imply regulatory/manufacturer verification.

Android should not display dosage, certification, or organic claims unless backend returns reviewed evidence fields and trust status.
