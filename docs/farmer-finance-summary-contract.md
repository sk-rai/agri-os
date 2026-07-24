# Farmer Stage Cost and P&L Summary Contract

Status date: 2026-07-24

## Principle

Android should render backend-computed farmer economics. Android should not calculate profitability, classify financial events, or decide which cost/income sections are visible.

P&L uses a fixed formula:

profit_or_loss = total_income - total_expenses

The formula itself is not admin-editable. Admin configuration controls only the mappings, labels, visibility, thresholds, and report layout.

## Why formula is fixed

Allowing arbitrary editable formulas creates avoidable risk: invalid syntax, unsafe execution, inconsistent farmer reports, and difficult auditability.

The safe model is configurable classification:

- which event/activity types count as income;
- which event/activity types count as expenses;
- which items are excluded from P&L but still shown as operational context;
- which sections Android should display or hide;
- which warning thresholds should be applied.

## Stage summary

Each crop stage should expose a backend-computed summary:

- stage code and display name;
- stage status;
- planned/recommended cost from workflow recommendations;
- actual expense total from logged crop activities;
- variance between planned and actual expense;
- activity count;
- expense breakup by activity type;
- expense breakup by input/product/labor/machinery item;
- detailed activity rows when enabled by admin display config;
- natural/context events captured during the stage, such as rain, drought, flood, hail, pest, disease, fire, livestock damage, or other field events;
- advisory/weather/soil context only where already persisted as backend snapshots or field events.

## Crop-cycle P&L summary

Each crop cycle should expose:

- total income;
- total expenses;
- profit_or_loss;
- planned expense;
- actual expense;
- variance;
- income breakup;
- expense breakup;
- per-acre values when normalized parcel area is available;
- warnings when area, yield, sale price, or harvest revenue is missing.

## Configurable admin mappings

Admin configuration should support a published versioned mapping like:

- income_categories:
  - HARVEST_SALE
  - CROP_INSURANCE_PAYOUT
  - GOVERNMENT_INCENTIVE
  - OTHER_INCOME
- expense_categories:
  - SEED
  - FERTILIZER
  - PESTICIDE
  - IRRIGATION
  - LABOR
  - MACHINERY
  - TRANSPORT
  - RENT
  - OTHER_EXPENSE
- context_event_categories:
  - RAIN
  - DROUGHT
  - FLOOD
  - HAIL
  - PEST_ATTACK
  - DISEASE
  - FIRE
  - LIVESTOCK_DAMAGE
  - OTHER_FIELD_EVENT

## Admin display control

Admin should be able to control:

- show or hide planned cost;
- show or hide variance;
- show or hide detailed activity rows;
- show or hide natural/context events;
- show or hide per-acre economics;
- show or hide income breakup;
- show or hide expense breakup;
- label text for farmer-facing Android screens;
- display order of sections;
- warning thresholds for cost variance or missing revenue.

## Sanity check before publish

Before a finance report config is published, backend validation must check:

- at least one income category is configured;
- at least one expense category is configured;
- categories are from backend-owned allowed values;
- no category is mapped as both income and expense;
- display sections reference valid summary fields;
- warning thresholds are numeric and within accepted bounds;
- sample report preview can be generated against test crop-cycle data;
- config version and audit metadata are present.

## Android-safe endpoints

Recommended Android endpoints:

- GET /api/v1/crop-cycles/{cycle_id}/stage-cost-summary
- GET /api/v1/crop-cycles/{cycle_id}/profit-loss-summary
- GET /api/v1/farmers/{farmer_id}/financial-summary

Android receives only backend-computed values plus backend display hints.

## Admin endpoints

Recommended admin endpoints:

- GET /api/v1/finance/report-config
- POST /api/v1/finance/report-config/drafts
- POST /api/v1/finance/report-config/drafts/{draft_id}/validate
- GET /api/v1/finance/report-config/drafts/{draft_id}/preview
- POST /api/v1/finance/report-config/drafts/{draft_id}/publish
- GET /api/v1/finance/report-config/audit

## Implementation order

1. Add backend service that computes stage expense summaries from crop_activities and crop_stage_instances.
2. Add natural/context event aggregation from existing field event data.
3. Add fixed P&L calculation using configured income/expense mappings.
4. Add config validator and default published config.
5. Add Android-safe read endpoints.
6. Add admin draft/validate/preview/publish endpoints.
7. Add regression tests and regenerate Android sample payloads.
