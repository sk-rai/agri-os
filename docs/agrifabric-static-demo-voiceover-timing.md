# AgriFabric static demo voiceover and scene timing

Status date: 2026-08-29

This document turns the first static/web demo batch into editor-ready voiceover and scene timing. It uses AgriFabric landing page screenshots and SVG assets only. It does not require Android capture, backend fixture mutation, database writes, live providers, or runtime lookup enablement.

Use this after docs/agrifabric-demo-video-production-manifest.md and docs/agrifabric-static-demo-capture-runbook.md.

## Shared production rules

- Target length: 35 to 60 seconds per clip.
- Use gentle zoom or pan on the existing full-page screenshot or tab screenshot.
- Use promoted thumbnails as card thumbnails, not necessarily as final full-frame video sources.
- Keep subtitles short enough for mobile viewing.
- Use claim labels where needed: Verified MVP, Backend-owned, Roadmap, Human review, Approval-gated.
- Avoid live-provider, live-NDVI, automated fraud, automated claim approval, and automated claim rejection language.

## V02 - Six pillars of AgriFabric

Primary asset: web/smoke/screenshots/agrifabric/agrifabric-v02-product-pillars-full.png

Thumbnail: web/public/demo-assets/agrifabric-v02-product-pillars-thumb.png

Target length: 50 seconds

Scene timing:

- 00:00 to 00:05. Product tab title and six-pillar headline. Voiceover: AgriFabric is not just a mobile app. It is a field evidence fabric for agriculture programs. Overlay: Field evidence fabric.
- 00:05 to 00:13. Slow pan across Capture and Coordinate cards. Voiceover: Capture records farmer, parcel, crop, activity, media, and field-event data. Coordinate connects FPO projects, field agents, farmers, villages, crops, and stages. Overlay: Capture plus Coordinate.
- 00:13 to 00:22. Pan across Sync and Advise cards. Voiceover: Sync protects offline work with replay ordering, idempotency, conflict recovery, and backlog draining. Advise delivers backend-owned advisories with media, language fallback, read and acknowledgement trails. Overlay: Offline-first plus targeted advisories.
- 00:22 to 00:33. Pan across Govern and Extend cards. Voiceover: Govern keeps contracts, labels, workflows, land guidance, and audit under backend control. Extend is the roadmap layer: insurance, subsidy, credit, provider, and satellite intelligence built on the same foundation. Overlay: Govern today. Extend carefully.
- 00:33 to 00:45. Product pillars SVG section. Voiceover: The key is separation: what is verified today stays visible, and what belongs to roadmap remains clearly bounded. Overlay: Verified foundation. Roadmap bounded.
- 00:45 to 00:50. Hold on full six-pillar layout. Voiceover: That is the operating fabric: capture, coordinate, sync, advise, govern, and extend. Overlay: Six pillars, one fabric.

Claim boundary: Extend is a roadmap foundation. Do not imply live risk scoring, live weather or soil, live NDVI, or automated decisioning.

## V10 - Relationship graph and commercial analytics

Primary asset: web/smoke/screenshots/agrifabric/agrifabric-v10-relationship-graph-full.png

Thumbnail: web/public/demo-assets/agrifabric-v10-relationship-graph-thumb.png

Target length: 45 seconds

Scene timing:

- 00:00 to 00:06. Evidence graph tab headline. Voiceover: The graph is the product moat. Agriculture operations should not live as disconnected forms. Overlay: Evidence graph.
- 00:06 to 00:16. Pan across company, project, farmer, parcel, crop cycle. Voiceover: Farmers, companies, FPOs, projects, parcels, and crop cycles become typed relationships that can be traced. Overlay: Project traceability.
- 00:16 to 00:26. Pan across GPS and DigiPin, activity, sync, read or acknowledgement, and audit. Voiceover: Field activity, location evidence, advisories, sync events, and audit trails stay connected to the same operating record. Overlay: Crop plus advisory plus audit.
- 00:26 to 00:36. Hold on roadmap analytics text card. Voiceover: This supports project operations today, and later can support agent benchmarking, assignment planning, risk review, and claim evidence bundles. Overlay: Roadmap analytics bounded.
- 00:36 to 00:45. Zoom out to full graph. Voiceover: The future analytics are deliberately bounded until separately implemented and governed. Overlay: Implemented traceability today.

Claim boundary: Do not imply current automated field-agent scoring, formal fraud scoring, claim approval, or claim rejection.

## V08 - PIN, GPS, DigiPin, and land intelligence

Primary asset: web/smoke/screenshots/agrifabric/agrifabric-v08-geography-digipin-full.png

Thumbnail: web/public/demo-assets/agrifabric-v08-geography-digipin-thumb.png

Target length: 55 seconds

Scene timing:

- 00:00 to 00:06. Geography tab headline. Voiceover: Geography is layered on purpose. PIN is useful context, but it is not parcel precision. Overlay: PIN is context.
- 00:06 to 00:16. Pan over LGD hierarchy, PIN reference, candidate locality. Voiceover: Administrative boundaries and localities provide identity and guardrails for selection, filtering, and review. Overlay: Admin plus postal context.
- 00:16 to 00:27. Pan over GPS capture, parcel evidence, DigiPin. Voiceover: GPS and parcel geometry provide field evidence. DigiPin is generated by the backend from coordinates. Overlay: GPS and DigiPin precision.
- 00:27 to 00:38. Pan over land intelligence and future enrichment layer. Voiceover: Land intelligence is informational and non-blocking. Provider, NDVI, and global profile enrichments remain future or approval-gated. Overlay: Informational guidance.
- 00:38 to 00:50. Show layered geography model. Voiceover: This separation lets the platform improve geography intelligence without confusing postal context, official identity, and physical field evidence. Overlay: Layers stay separate.
- 00:50 to 00:55. Hold on full geography layout. Voiceover: That is why the product treats location as evidence, not just an address field. Overlay: Location as evidence.

Claim boundary: Do not claim PIN resolves exact plot identity, Android computes canonical DigiPin, live geocoding is enabled, or global geography rollout is complete.

## V11 - Insurance and subsidy integrity foundation

Primary asset: web/smoke/screenshots/agrifabric/agrifabric-v11-insurance-roadmap-full.png

Thumbnail: web/public/demo-assets/agrifabric-v11-insurance-roadmap-thumb.png

Target length: 50 seconds

Scene timing:

- 00:00 to 00:06. Roadmap tab headline. Voiceover: AgriFabric creates a field evidence foundation today, and keeps review intelligence clearly bounded for tomorrow. Overlay: Evidence today.
- 00:06 to 00:18. Pan over implemented evidence foundation. Voiceover: Identity, project participation, parcel precision, crop ledger, field media, advisory lifecycle, sync, and audit become an evidence bundle. Overlay: Field evidence bundle.
- 00:18 to 00:30. Pan over roadmap review intelligence. Voiceover: In the future, that bundle can help flag duplicate parcel claims, sparse activity trails, media mismatch, geo-time plausibility issues, or missing supporting evidence. Overlay: Review signals, not verdicts.
- 00:30 to 00:40. Claim boundary card. Voiceover: The boundary matters. This is review-assistive intelligence for human workflows. Overlay: Human review.
- 00:40 to 00:50. Hold on roadmap graphic and compact graphic. Voiceover: It is not automated fraud detection, not automated claim approval, and not automated claim rejection. Overlay: Not automated decisioning.

Claim boundary: Never say detects fraud today, approves claims, rejects claims, live NDVI scoring, or insurer-integrated production scoring.

## Recommended batch sequence

Produce clips in this order:

1. V02 - Six pillars of AgriFabric
2. V10 - Relationship graph and commercial analytics
3. V08 - PIN, GPS, DigiPin, and land intelligence
4. V11 - Insurance and subsidy integrity foundation

This sequence moves from product overview, to data model, to geography evidence, to future review intelligence.

## Suggested editor export names

- agrifabric-v02-product-pillars-static.mp4
- agrifabric-v10-relationship-graph-static.mp4
- agrifabric-v08-geography-digipin-static.mp4
- agrifabric-v11-insurance-roadmap-static.mp4

## Next implementation step

After NWDP overlay completes or when CPU is available, create a lightweight static-video builder that turns each full screenshot into a short pan or zoom MP4 with optional subtitle overlays. Until then, this document is enough for manual editing in any video tool.
