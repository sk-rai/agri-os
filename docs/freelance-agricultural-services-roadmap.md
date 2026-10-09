# Freelance agricultural services roadmap

## Purpose

Agri-OS should eventually allow independently enrolled farmers to discover
and engage registered agricultural specialists, including freelance field
agents and agronomists.

Specialists may declare the crops, service categories, languages, and
geographic areas they support. They may initially offer free services and,
after prerequisite capabilities are proven, may offer monetised services.

This is deferred future engineering work. It does not authorize ecommerce,
payment processing, automatic specialist access to farmers, or changes to the
current project-agent assignment workflow.

## Product boundary

This direction is a focused agricultural-services network built on the
existing farmer, parcel, crop-cycle, advisory, field-event, evidence, and
outcome graph. It is not a broad agricultural ecommerce marketplace.

The intended participants are:

- independently enrolled farmers in self-service mode;
- verified freelance agronomists and field agents;
- project/company agents operating through existing project assignments;
- platform administrators responsible for verification and safety controls.

Project staffing and freelance service engagements are different
relationships:

- project-agent assignment is controlled by a company or project
  administrator;
- freelance engagement must be initiated or explicitly accepted by the
  farmer and specialist;
- geographic and crop suitability may support discovery, but never grant
  access by themselves.

## Apriori dependencies

Before implementing monetised services, the platform should establish:

1. verified specialist identity and qualification records;
2. specialist crop, geography, language, and service-category scopes;
3. farmer-controlled service requests and invitations;
4. mutual acceptance and explicit engagement lifecycle states;
5. purpose-bound, time-bound, revocable farmer data-access grants;
6. appointment, communication, advisory, visit, evidence, and completion
   records;
7. safety and escalation rules for regulated or high-risk advice;
8. consent, privacy, audit, grievance, correction, and dispute workflows;
9. separation between company employee performance and freelance reputation;
10. evidence-backed service completion and transparent farmer feedback.

Payment, pricing, commission, settlement, refunds, taxation, and commercial
disputes should be designed only after the free-service engagement workflow is
operationally validated.

## Proposed domain model

Future additive entities may include:

- `specialist_profiles`;
- `specialist_verifications`;
- `specialist_service_areas`;
- `specialist_crop_scopes`;
- `specialist_service_offerings`;
- `farmer_service_requests`;
- `specialist_service_proposals`;
- `specialist_engagements`;
- `farmer_data_access_grants`;
- `specialist_appointments`;
- `specialist_service_events`;
- `specialist_service_feedback`.

These must not be represented as synthetic projects or farmer-project
enrollments. A farmer remains independent unless they actually join a company
or project.

## Authorization principles

A specialist must not gain access merely by selecting a farmer, geography, or
crop. Access requires a persisted engagement and explicit farmer consent.

An engagement should specify:

- farmer and specialist identities;
- requested service and purpose;
- selected parcels or crop cycles;
- granted data categories;
- start and expiry timestamps;
- current lifecycle status;
- initiating and accepting actors;
- revocation history;
- immutable audit events.

Farmers must be able to decline, revoke, or allow an engagement to expire
without losing their profile or self-service access.

## Delivery sequence

### Phase 1 — Foundation

- specialist registration and verification;
- crop/geography/language scopes;
- free service offerings;
- farmer search and service requests;
- mutual acceptance;
- bounded data-access grants;
- audit and revocation.

### Phase 2 — Operational services

- appointments and field visits;
- advisory delivery;
- evidence and completion records;
- farmer feedback;
- safety escalation and dispute handling.

### Phase 3 — Reputation

- explainable service history;
- verified completion metrics;
- farmer feedback with correction and dispute workflows;
- strict separation from company employee performance scoring.

### Phase 4 — Monetisation

- priced offerings;
- orders and invoices;
- payment-provider integration;
- refunds, settlement, commission, tax, and commercial disputes.

No monetisation phase should begin merely because specialist discovery or
assignment exists.

## Current implementation boundary

Current `farmer_project_enrollments` and
`POST /api/v1/farmers/{farmer_id}/project-agent-assignment` represent
company/project operational relationships. They must not be reused to let a
freelancer unilaterally attach themselves to an independent farmer.

The future freelance workflow should be additive and consent-driven, while
reusing existing farmer, parcel, crop-cycle, advisory, field-event, media, and
audit primitives where appropriate.
