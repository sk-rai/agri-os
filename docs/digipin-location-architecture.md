# DigiPin Location Architecture

Status date: 2026-07-24

## Decision

Agri-OS should generate DigiPin at runtime from captured GPS coordinates. It should not preload or store all possible DigiPins for each PIN code.

DigiPin is a precise coordinate-derived digital address layer. PIN code is a broad postal/reference layer. LGD village is an administrative identity layer. Parcel geometry/GPS is the physical location layer.

These layers complement each other and should not replace one another.

## Location layers

### LGD geography

LGD remains the canonical administrative identity for India geography.

Examples:

- state
- district
- block or sub-district
- village or locality
- LGD codes

LGD is used for official administrative grouping, reporting, project geography scope, and source reconciliation.

### PIN code / postal reference

PIN code remains the postal lookup and reference layer.

A PIN code can map to multiple villages, post offices, and localities. Android should call backend geography/PIN lookup endpoints and should not ship its own PIN database.

PIN data should be periodically refreshed from India Post / OGD postal sources and reconciled without overwriting LGD identity.

### GPS and parcel geometry

GPS coordinates and parcel geometry are the physical location layer.

Agri-OS already supports:

- farmer enrollment GPS latitude/longitude;
- parcel centroid latitude/longitude;
- parcel polygon geometry;
- geometry source such as NONE, PIN_DROP, GPS_WALK, MANUAL_DRAW, and SATELLITE.

GPS remains optional but should be captured when available.

### DigiPin

DigiPin is derived from precise latitude/longitude and represents a small grid cell, roughly 4m x 4m.

DigiPin should be generated only when Agri-OS has an actual coordinate.

It should not be guessed from PIN code, village, district, or manual address text.

## Why DigiPin should not be preloaded for PIN codes

A PIN code covers a broad postal service area. A DigiPin represents a very small coordinate grid cell.

One PIN code area can contain thousands or millions of DigiPin cells. Preloading all DigiPins for a PIN code would be wasteful, hard to refresh, and not useful for enrollment.

Correct flow:

1. User enters PIN code.
2. Backend returns candidate villages/localities/postal references.
3. User selects or confirms village/locality.
4. If GPS is captured, backend generates DigiPin from latitude/longitude.
5. Backend saves DigiPin on the farmer home or parcel record.
6. If GPS is missing, DigiPin remains null.

## Farmer home DigiPin

Farmer home DigiPin should be derived from:

- farmers.enrollment_gps_lat
- farmers.enrollment_gps_lng

Recommended farmer fields:

- home_digipin
- home_digipin_algorithm_version
- home_digipin_generated_at

Farmer home DigiPin should not replace:

- village_id
- village_name_manual
- pin_code
- enrollment_gps_lat
- enrollment_gps_lng

## Parcel DigiPin

Parcel DigiPin should be derived from:

- parcels.centroid_lat
- parcels.centroid_lng

If a parcel polygon is captured, backend can derive centroid coordinates from the polygon and then generate DigiPin.

Recommended parcel fields:

- centroid_digipin
- centroid_digipin_algorithm_version
- centroid_digipin_generated_at

Parcel DigiPin should not replace:

- village_id
- village_name_manual
- pin_code
- location_scope
- centroid_lat
- centroid_lng
- geometry
- geometry_source

## Runtime generation rules

Backend should generate DigiPin when:

- farmer enrollment GPS lat/lng are created or updated;
- parcel centroid lat/lng are created or updated;
- parcel polygon geometry is captured and centroid is computed;
- future field-event/shop/warehouse coordinates are captured, if those entities later adopt DigiPin.

Backend should clear or recompute DigiPin when:

- source coordinates are removed;
- source coordinates are changed;
- algorithm version changes and a migration/backfill is run.

## Validation rules

Backend should validate:

- latitude and longitude are numeric;
- coordinates are inside the DigiPin-supported India bounding box;
- generated DigiPin matches the current algorithm version;
- a supplied client DigiPin, if ever accepted, matches backend recomputation from lat/lng.

Android should not be trusted as the source of DigiPin. Android may display DigiPin and may capture GPS, but backend computes the canonical DigiPin.

## Storage decision

Initial implementation should add direct fields to farmers and parcels.

This is simpler and Android-friendly because these are the two core MVP entities that need DigiPin.

A generic cross-reference table is deferred until Agri-OS needs DigiPin for many entity types such as warehouses, dealers, field events, agent offices, or weather grid points.

## Future generic table

If needed later, add an entity geocode table:

- tenant_id
- entity_type
- entity_id
- location_role
- lat
- lng
- digipin
- algorithm_version
- source
- generated_at
- is_active

Do not add this table for the first implementation unless multiple non-farmer/non-parcel entity types require DigiPin at the same time.

## Android behavior

Android should:

- collect PIN/village using backend lookup;
- collect GPS where available;
- send latitude/longitude to backend;
- render backend-returned DigiPin;
- handle null DigiPin when GPS is not available.

Android should not:

- preload DigiPin grids;
- infer DigiPin from PIN code;
- replace PIN/village with DigiPin;
- compute farmer economics or geography identity locally.

## Implementation order

1. Add backend DigiPin utility with encode/decode/validation functions.
2. Add migration for farmer and parcel DigiPin fields.
3. Generate farmer home DigiPin during create/update when enrollment GPS exists.
4. Generate parcel DigiPin during create/update/geometry update when centroid exists.
5. Add DigiPin fields to farmer and parcel response payloads.
6. Add regression tests for generation, recomputation, and null behavior.
7. Regenerate Android sample payloads.
