# Geography and DigiPin SVG asset plan

Status date: 2026-08-20

This plan converts docs/geography-digipin-visual-spec.md into three lightweight, editable SVG assets for landing-page, demo-video, and investor/product use.

## Asset set

| Asset | Purpose | Best use |
| --- | --- | --- |
| docs/assets/geography-digipin-overview.svg | Clean landing-page overview of the implemented geography stack. | Landing-page section, demo overlay, product one-pager. |
| docs/assets/geography-digipin-layered-model.svg | Fuller layered model showing admin, postal, GPS/parcel, DigiPin, land intelligence, and future enrichment. | Deeper explainer section or slide. |
| docs/assets/geography-global-extension-layer.svg | Roadmap visual for country-specific/global geography generalization. | Roadmap slide, investor follow-up, architecture narrative. |

## Design direction

Use a simple layered/subway style rather than a dense graph.

The key message is:

> PIN is context. GPS and DigiPin are precision evidence.

## Claim boundaries

- DigiPin is backend-generated from coordinates.
- PIN is broad postal context, not parcel precision.
- LGD/admin geography is separate from PIN/postal and Census/reference layers.
- Land intelligence is informational and non-blocking.
- Global geography, live providers, village geocoding, and NDVI/satellite analytics are roadmap or approval-gated.

## Visual acceptance checklist

- No overlap between labels and nodes.
- Roadmap layers use dashed/amber treatment.
- Android is shown as capture/display, not canonical geography computation.
- Backend generation/validation is visually explicit.
- The overview is simple enough for a landing page.
- The layered model is clear enough for a product explainer.
- The global variant says architecture path, not completed rollout.
