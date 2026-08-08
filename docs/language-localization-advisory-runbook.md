# Language Localization and Advisory Translation Runbook

Status date: 2026-07-27

This runbook defines how backend-driven labels, localized content, and advisory translations should be handled for Android and demos.

## Current local audit result

Read-only audit script:

    backend/scripts/audit_language_localization_readiness.py

Latest local result:

- backend-driven labels/content supported: yes;
- English-first Android QA ready: yes;
- broad Hindi crop/stage metadata QA ready: yes;
- unreviewed dynamic advisory translation safe: no;
- crops with Hindi alias/script coverage: 30 / 30;
- workflow lifecycle templates with Hindi alias/script coverage: 11 / 11;
- missing seeded Hindi stage labels: 0;
- broadcast content rows:
  - English: 71;
  - Hindi: 54;
  - Kannada: 4.

Important distinction: crop/stage metadata Hindi readiness is green for demo QA, but advisory translation remains review-gated and should not be treated as automatically safe.

## Core decision

Android must not translate advisories locally.

Android should render the backend-selected content variant for the user's language/context. If an approved localized variant is unavailable, fallback behavior should be backend-driven.

## Advisory translation policy

### Production rule

Production advisories should be published only when the language variant is reviewed and approved.

Acceptable production sources:

1. client-provided advisory in the target language;
2. agronomist/local expert-written advisory in the target language;
3. machine-translated draft reviewed and approved by client/agronomist/local expert.

### Machine translation role

Machine translation or AI translation may be used for draft generation.

Machine-translated content must remain in a draft or review status until approved.

Recommended statuses:

- `SOURCE`
- `CLIENT_PROVIDED`
- `MACHINE_TRANSLATED_DRAFT`
- `AGRONOMIST_REVIEW_REQUIRED`
- `CLIENT_REVIEW_REQUIRED`
- `REVIEWED_APPROVED`
- `REJECTED`
- `PUBLISHED`

### Demo rule

For demos, machine-translated content may be shown only if clearly marked as demo/unverified or after internal review.

Do not present machine translation as verified agronomic advice.

## Why review is required

Agronomic advisories are risk-bearing content.

Translation errors can affect:

- dosage;
- product name;
- crop stage;
- pest/disease name;
- application method;
- waiting period/pre-harvest interval;
- safety instructions;
- negation, such as "do not spray";
- local terminology and farmer comprehension.

## Fallback behavior

If a user's preferred language variant is missing:

Preferred order:

1. approved variant in preferred language;
2. approved variant in fallback language configured by backend;
3. source language with visible language availability marker;
4. suppress localized advisory if content is safety-critical and no approved translation exists.

Android should not decide this policy locally. Backend should return the content variant and fallback metadata.

## Label/content types

### Form labels and option sets

Can be backend-driven and progressively localized.

Risk level: low to medium.

Examples:

- gender;
- land unit;
- ownership type;
- irrigation source;
- soil texture.

### Crop/stage/input labels

Should be reviewed for local terminology.

Risk level: medium.

Examples:

- crop names;
- lifecycle stage names;
- input category names;
- soil terms.

### Advisories

Must be reviewed before production broadcast.

Risk level: high.

Examples:

- pest warning;
- disease spray recommendation;
- fertilizer timing;
- weather risk advisory;
- soil amendment guidance.

## Android rule

Android should:

- render backend-provided labels and content;
- respect backend fallback metadata;
- show language availability indicators if backend provides them;
- avoid hardcoded translations.

Android should not:

- translate advisories on-device;
- infer language fallback policy locally;
- publish/display unreviewed machine translations as verified advice;
- modify dosage/product/stage text locally.

## Backend next steps

1. Keep crop/stage Hindi seed pack maintained as crops/workflows expand.
2. Add advisory content translation/review statuses if missing.
3. Add backend fallback metadata to advisory feed/detail if Android needs it.
4. Add sample payloads showing:
   - approved Hindi advisory;
   - missing-language fallback;
   - machine-translated draft not visible to farmer app.
## Android multilingual form-label test extension

The Android sync/emulator test matrix should also exercise backend-driven form labels under Hindi, Kannada, Marathi, and Punjabi language contexts. Current form/option label readiness is intentionally English-fallback-first: English and Hindi keys exist for audited form labels, while Kannada/Marathi/Punjabi should fall back to English until native labels are added and reviewed.

Read-only audit:

    backend/scripts/audit_android_multilingual_form_labels.py

Detailed Android plan:

    docs/android-multilingual-profile-form-test.md