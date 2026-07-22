# Workflow Crop-System and BBCH Customization

## Principle

BBCH-style phenology remains the baseline crop-stage classification spine. Project/client customization should layer labels, local practices, stage durations, recommendations, costs, decision nodes, and crop-system-specific onboarding rules on top of that baseline rather than replacing it with unrelated stage semantics.

## Source of truth

The workflow template catalog is the source of truth for actual crop-cycle stages. The crop-system metadata endpoint is a discovery/evaluation helper for Android and should not become a parallel workflow editor.

## Admin customization model

- Default templates define canonical stages, BBCH ranges where applicable, propagation method, and recommended activities.
- Admin draft customization may edit labels, descriptions, durations, stage order, recommendations, costs, warning metadata, and decision nodes.
- Project-level overrides may customize visibility, recommendations, and local costs without mutating the canonical template.
- Published versions should be immutable for active/pinned crop cycles; new changes should be published as new versions.
- Deletion should be logical/archive where possible, with audit trail and actor/reason.

## Crop-system metadata keys

Recommended template/version/stage metadata keys:

- `crop_system`: annual field crop, perennial orchard, plantation crop, perennial spice, floriculture, agroforestry/timber.
- `bbch_baseline`: true/false plus BBCH scale/range reference where applicable.
- `allowed_start_stages`: stages Android may use when registering an existing crop/orchard/plantation.
- `supports_existing_crop_current_stage`: whether Android can start the cycle at a non-initial stage.
- `requires_establishment_year`: whether crop age/year is recommended before onboarding.
- `stage_warning_rules`: season mismatch, geography mismatch, stage/calendar mismatch, market-window mismatch.
- `decision_nodes`: explicit branch choices such as ratoon vs new crop, nursery vs direct-seeded, keep/replant orchard.

## Android behavior

Android should render backend stages and labels from the published workflow preview. When a farmer/agent starts an existing orchard, plantation, floriculture, spice, or agroforestry crop, Android should use backend metadata to offer current-stage choices and show confirmation warnings before proceeding with unusual crop/season/geography/stage combinations.

Workflow BBCH/crop-system audit checkpoint
Added `backend/scripts/audit_workflow_bbch_crop_system_readiness.py` to measure BBCH range coverage, propagation-step stages, recommendation cost coverage, decision-like recommendations, and missing crop-system metadata on workflow templates.

Workflow crop-system metadata backfill checkpoint
Added `backend/scripts/backfill_workflow_crop_system_metadata.py` to backfill crop-system, BBCH baseline, allowed start stages, warning rules, and decision-node metadata on existing Rice/Sugarcane workflow templates and versions without changing stage rows.

Pre-Android metadata audit checkpoint
`backend/scripts/pre_android_handoff_check.py` now runs metadata, product catalog, season/land-unit, and workflow BBCH/crop-system readiness audits as part of the backend handoff gate.
