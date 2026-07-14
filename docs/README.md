# Agri-OS Documentation

## Structure

```
docs/
├── README.md                ← This file
├── reconciliation/          ← AUTHORITATIVE governance decisions
│   ├── adrs/               ← Architecture Decision Records (9 ADRs + semantic registry)
│   ├── contracts/          ← Behavioral specifications (13 documents)
│   └── operations/         ← Operational governance (5 documents)
│
└── sources/                 ← RAW INPUT MATERIAL (not authoritative)
    ├── ai-1/               ← Original AI-1 documents (15 files expected)
    └── reviews/            ← 4-pass architecture review reports (6 files)
```

## Reading Order (for new team members)

1. `reconciliation/adrs/ADR-001-architecture-identity.md` — What kind of system is this?
2. `reconciliation/adrs/canonical-semantic-registry-v1.md` — What do we call things?
3. `reconciliation/adrs/ADR-005-mvp-vertical-slice.md` — What are we building first?
4. `reconciliation/adrs/farmer-value-ladder.md` — Why would farmers use this?
5. `reconciliation/contracts/mvp-api-contract.md` — What does the API look like?
6. `reconciliation/contracts/complete-state-machines.md` — How do workflows behave?
7. `backend-driven-platform-architecture.md` — How are backend-driven platform modules evolving?
8. `profile-form-contracts.md` — How should farmer/parcel/soil profile forms be rendered?

## Governance Rule

- **reconciliation/** = implementation law (frozen decisions)
- **sources/** = historical reference (how we got here)
- If sources and reconciliation conflict → reconciliation wins
- Changes to reconciliation require explicit decision + version bump
