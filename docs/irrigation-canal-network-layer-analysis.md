# Irrigation canal network layer analysis

Status date: 2026-08-08

This note records a deferred geography/water-infrastructure idea: using the NWIC/CWC Canal Network dataset as a backend context layer for farmer/parcel irrigation-source validation.

## Source dataset

- Dataset: NWIC / CWC Canal Network
- Portal: https://nwdp.nwic.gov.in/dataset/canal
- Available resources: KML, GeoJSON, SHP
- Producer: Central Water Commission
- Portal description: geospatial layer of different canal types associated with major and medium command areas.
- Observed update date on portal: 2025-11-17

## Relevance to Agri-OS

Agri-OS already asks during farmer/parcel registration whether a field is irrigated by sources such as tubewell, canal, or rainfed. The canal layer can provide backend evidence to corroborate or question farmer-reported canal irrigation.

This should be treated as a plausibility/evidence layer, not as absolute truth.

## Proposed interpretation

| Farmer-reported source | Canal layer signal | Backend interpretation |
| --- | --- | --- |
| CANAL | Parcel near or inside canal/command network | Corroborates reported canal irrigation. |
| CANAL | No nearby canal found | Ask confirmation; do not reject because minor/local canals may be absent from the dataset. |
| TUBEWELL | Nearby canal present | Prompt whether canal is also available; keep farmer-reported tubewell as operational truth. |
| RAIN_FED | Nearby canal present | Prompt field agent/farmer to confirm canal is unavailable, non-functional, or not used. |
| TUBEWELL or RAIN_FED | No nearby canal found | Plausible, but not proof. Tubewell validation needs groundwater/minor-irrigation datasets. |

## Potential backend output

Future `land-intelligence-context` responses could include a compact `water_infrastructure_context` block:

    {
      "water_infrastructure_context": {
        "reported_irrigation_source": "CANAL",
        "nearest_canal_distance_m": 420,
        "canal_context": "NEAR_CANAL_NETWORK",
        "irrigation_source_consistency": "SUPPORTS_REPORTED_SOURCE",
        "source": "NWIC_CWC_CANAL_NETWORK",
        "source_updated_on": "2025-11-17"
      }
    }

Possible consistency buckets:

- CORROBORATED_CANAL
- CANAL_REPORTED_NO_CANAL_SIGNAL
- CANAL_NEAR_BUT_NOT_REPORTED
- NO_CANAL_SIGNAL
- UNKNOWN_GEOMETRY_OR_SOURCE

## Android usage

Android should not download or render the full canal network in MVP. It should consume backend summaries and show confirmation prompts only when useful.

Example prompts:

- Canal selected and canal nearby: "Canal network appears nearby. Confirm canal irrigation details."
- Canal selected and no canal signal: "No major/medium canal is mapped nearby. If this is a local/minor canal, please confirm."
- Rainfed/tubewell selected and canal nearby: "A canal network appears nearby. Is canal water available for this parcel?"

Android should not block registration based on this layer.

## Agronomic value

Canal proximity/context can improve:

- irrigation-source confidence;
- crop suitability guidance for paddy, sugarcane, vegetables, and other water-sensitive crops;
- irrigation scheduling/advisory personalization;
- waterlogging and salinity risk prompts in canal-command areas;
- field-agent review prioritization where farmer-reported source conflicts with mapped infrastructure;
- project planning for irrigation interventions.

## Caveats

- Canal proximity does not prove active water availability.
- Major/medium canal data may miss minor canals, distributaries, field channels, lift irrigation, tanks, private channels, or temporary/local structures.
- Dataset likely does not encode seasonal releases, closures, maintenance status, or allocation.
- Farmer/field-agent reported irrigation source remains the operational source of truth.
- Tubewell validation requires separate groundwater/minor-irrigation datasets.
- Licensing/attribution and data quality must be reviewed before production use.

## Deferred implementation plan

When Android sync/multilingual testing and current backend priorities are complete:

1. Download and archive the Canal Network GeoJSON/SHP with source metadata.
2. Audit feature count, CRS, geometry validity, attributes, state coverage, and file size.
3. Inspect whether attributes include canal type/name/project/command-area identifiers.
4. Build a read-only proximity analysis for current active test states: UP, Karnataka, Maharashtra, Punjab.
5. Compare canal proximity buckets with existing parcel `irrigation_source` values.
6. Design a backend table and ingestion script only after audit results are acceptable.
7. Add summarized water-infrastructure context to land intelligence, not raw geometry to Android.

## Current decision

Deferred. Valuable and relevant, but not part of the current Android Maestro/sync work. Revisit after Android sync, multilingual flow, and backend handoff tasks are complete.
