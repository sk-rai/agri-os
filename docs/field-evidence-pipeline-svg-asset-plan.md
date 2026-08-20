# Field evidence pipeline SVG asset plan

Status date: 2026-08-20

This plan creates a clean field-evidence pipeline visual for the landing page, demo overlays, and product/investor explainers.

## Asset set

| Asset | Purpose | Best use |
| --- | --- | --- |
| docs/assets/field-evidence-pipeline.svg | Main left-to-right pipeline showing how field capture becomes backend-governed evidence and operations. | Landing page pipeline section, demo intro, investor/product one-pager. |
| docs/assets/field-evidence-pipeline-compact.svg | Smaller strip version for video overlays and section dividers. | Demo videos, carousel slides, thumbnails. |

## Design direction

Use a clean horizontal pipeline.

The message:

> Android captures field reality. Backend turns it into governed evidence, operations, and future intelligence.

## Pipeline stages

1. Android field capture
   - farmer
   - parcel
   - crop cycle
   - activity
   - media
   - field event

2. Offline sync queue
   - persistence
   - replay
   - idempotency
   - conflict cards
   - backlog draining

3. Backend contracts
   - validation
   - labels/options
   - workflow rules
   - targeting
   - audit

4. Admin and FPO operations
   - project trace
   - farmer cohorts
   - advisories
   - read/ack analytics
   - field-agent work

5. Roadmap intelligence
   - risk review
   - agent performance
   - NDVI/satellite
   - insurance/subsidy evidence
   - live weather/soil

## Claim boundaries

- Android capture, offline sync, backend contracts, admin operations, advisories, read/ack, and audit are implemented foundation.
- Roadmap intelligence must be visually marked as future/approval-gated.
- The graphic should not imply live provider execution, operational claim scoring, or automated insurance decisions.
- Android should be shown as capture/display; backend owns interpretation, validation, labels, targeting, and audit history.

## Visual acceptance checklist

- No overlapping labels, nodes, or arrows.
- Pipeline flow is readable at landing-page width.
- Roadmap section is dashed/amber.
- Implemented foundation uses blue/green/purple/gray styles consistent with existing SVG assets.
- The compact version remains readable in a video overlay.
