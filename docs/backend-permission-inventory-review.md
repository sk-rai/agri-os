# Backend Permission Inventory Review

Status date: 2026-07-21

This review converts the static endpoint scanner output into a human-reviewed backend hardening artifact. The scanner is intentionally conservative and flags some acceptable public/reference or generic template endpoints.

## Current scanner command

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/audit_endpoint_permission_inventory.py
```

Focused admin/backoffice view:

```bash
../venv/bin/python scripts/audit_endpoint_permission_inventory.py \
  | grep -E "flagged_count|ADMIN_OR_BACKOFFICE|WORKER_OPS"
```

## Hardening completed

- Provider worker/ops endpoints now require admin permissions.
- Weather provider configuration and provider execution endpoints now require admin permissions.
- Company profile read and company discovery CSV template download now require admin permissions.
- Tenant/project administration endpoints now require admin permissions.
- Project-scoped input assignment and workflow configuration read endpoints now require admin permissions.

## Accepted scanner noise for now

### Public/reference endpoints

Some endpoints are intentionally shared/public reference reads and may not require tenant scoping in MVP:

- health check;
- OTP request;
- geography reference reads;
- crop catalog reference reads;
- soil inference/source-contract reads.

These should be revisited before production if deployment requires every reference read to be tenant-branded or rate-limited.

### Generic CSV template/export endpoints

Several admin template/export endpoints may be flagged for missing tenant marker even when they are safe generic templates or admin-authenticated exports. Examples:

- crop taxonomy template/export;
- crop propagation template/export;
- crop template/export;
- input catalog template/export;
- product catalog template/export;
- workflow CSV template;
- company discovery template.

Decision for now: do not block Android handoff on these if they are admin-authenticated or generic static templates. Future production pass can add tenant headers consistently for observability.

## Remaining review areas

### Tenant-scope consistency

Remaining flags mostly mean the scanner cannot see tenant markers. For production hardening, decide whether generic admin templates should still require `X-Tenant-ID` for auditability.

### Public reference rate limiting

Public/shared endpoints should be protected through platform-level rate limiting or API gateway controls before open production traffic.

### Android-safe endpoint allowlist

Before Android rewiring starts, produce a final allowlist of endpoints Android may call. Worker/ops, provider configuration, company administration, and discovery/prepopulation endpoints should stay off Android.

## Current conclusion

The high-risk backend-owned operations surfaces created during weather, soil enrichment, company profile, and provider-worker work are now permission hardened. Remaining scanner flags are mostly reference-read or template/export classification items and should be handled as a production hardening pass rather than Android MVP blockers.

Android endpoint allowlist is maintained in `docs/android-endpoint-allowlist.md`; use it to separate Android-safe endpoints from admin/backend-only operations surfaces.

## Permission inventory checkpoint - flagged_count=38

Current inventory flags are mostly expected shared-read or tenant-scope review items, not newly discovered high-risk mutations.

Intentional Android/shared-read surfaces:

- health/OTP bootstrap style endpoints remain shared review items;
- geography cascade and village search endpoints are Android-allowed master-data reads;
- `GET /api/v1/master-data/geography/villages/by-pin-code` is Android-allowed for parcel PIN-code candidate village selection;
- crop catalog and input catalog reference reads remain Android/admin shared-read surfaces where tenant-specific behavior is controlled by backend filters/options;
- soil enrichment source-contract and district inference are read-only contract/helper endpoints.

Remaining admin/backoffice template/export endpoints are flagged for tenant-scope review because the scanner cannot infer whether templates are global or tenant-filtered. These should be reviewed endpoint-by-endpoint before production, but they are lower priority than mutation/provider-worker hardening already completed.

Do not reduce flagged_count by adding auth to Android-required geography/catalog reads without updating `docs/android-endpoint-allowlist.md` and Android handoff docs.

## Metadata governance rule

All metadata mutations must be admin/backoffice controlled and audit logged. This applies to geography aliases/imports, crop taxonomy, crop seasons, local unit conversions, input/product catalog rows, workflow templates, advisory seed content, and broadcast templates. The preferred mutation model is append/update/expire rather than physical delete: rows should keep `created_at`, `updated_at`, actor metadata, reason, and where relevant `effective_from`, `expires_at`, `status`, or `is_active`. Runtime consumers should decide visibility/validity from status plus effective/expiry windows. Physical deletion should be reserved for failed imports, temporary staging rows, or explicit maintenance tasks with audit trail.
