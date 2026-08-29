# AgriFabric static demo editor handoff

Status date: 2026-08-29

This handoff is for producing the first AgriFabric static demo clips from already captured landing-page screenshots and promoted thumbnails. It is intentionally safe to use while the long NWDP overlay job is running because it does not require Android capture, backend changes, database writes, or local video rendering.

## Source documents

Use these in order:

1. `docs/agrifabric-demo-video-production-manifest.md`
2. `docs/agrifabric-static-demo-voiceover-timing.md`
3. `docs/agrifabric-static-demo-clip-manifest.json`

Validation helpers:

- `web/smoke/agrifabric_static_demo_readiness_check.mjs`
- `web/smoke/agrifabric_static_demo_clip_manifest_check.mjs`
- `web/smoke/agrifabric_static_demo_render_dry_run.mjs`

## Clip batch

Produce these four static/web-led clips first:

| Clip | Target length | Main visual | Output name |
| --- | ---: | --- | --- |
| V02 Six pillars | 50 sec | Product pillars full screenshot | `agrifabric-v02-product-pillars-static.mp4` |
| V10 Relationship graph | 45 sec | Evidence graph full screenshot | `agrifabric-v10-relationship-graph-static.mp4` |
| V08 Geography + DigiPin | 55 sec | Geography/DigiPin full screenshot | `agrifabric-v08-geography-digipin-static.mp4` |
| V11 Insurance roadmap | 50 sec | Roadmap full screenshot | `agrifabric-v11-insurance-roadmap-static.mp4` |

## Visual style

Use simple, restrained motion:

- gentle zoom-in on opening headline;
- slow pan across cards or diagrams;
- hold on full layout for the final beat;
- avoid fast movement, flashy transitions, or anything that makes text unreadable;
- keep subtitles short enough for mobile.

Recommended export:

- 1280x720 or 1920x1080;
- 30 fps;
- H.264 MP4;
- no dependency on live web rendering once screenshots are captured.

## Claim boundaries

Keep these boundaries visible in script, overlays, or final review notes:

- Roadmap modules are not live production claims.
- Do not claim automated fraud detection.
- Do not claim automated insurance approval or rejection.
- Do not claim live NDVI scoring.
- Do not claim live weather, soil, or provider integration unless separately implemented.
- Do not imply Android computes canonical DigiPin; backend owns generation.
- Treat land intelligence as informational and non-blocking.

## Suggested review checklist

Before publishing or attaching to the landing page, verify:

- each clip uses the correct screenshot family;
- title and subtitle text match the timing document;
- roadmap and claim-boundary labels remain visible;
- no subtitle implies live automated decisioning;
- exported filename matches the planned output name;
- thumbnail matches the same clip family;
- final MP4 plays on desktop and mobile;
- file size is acceptable for web delivery.

## Deferred items

Do not start these until NWDP overlay and CPU-heavy work are complete:

- Android onboarding recording;
- offline sync resilience recording;
- live emulator capture;
- final MP4 render automation;
- attaching MP4 playback to the landing page.
