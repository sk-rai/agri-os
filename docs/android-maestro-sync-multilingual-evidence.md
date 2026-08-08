# Android Maestro sync + multilingual evidence checklist

Status date: 2026-08-08

Use this checklist to collect evidence from the next Android Maestro pass without changing backend contracts.

## Backend gates

Before Maestro:

    cd ~/projects/farmint/backend
    ../venv/bin/python scripts/pre_android_handoff_check.py
    ../venv/bin/python scripts/audit_android_multilingual_form_labels.py | python3 -m json.tool

Expected multilingual audit:

- English fallback complete: true
- Hindi label keys present: true
- Kannada/Marathi/Punjabi native labels complete: false
- Android must use English fallback for kn, mr, pa: true

## Evidence to collect per scenario

For each scenario, capture:

- Maestro flow name
- Android app build/version
- tenant id
- project id
- language code
- state/district context
- screenshot path
- backend fixture command output
- backend verifier command output
- pass/fail
- notes/gaps

## Sync scenarios

### Stale-context failure

- Fixture: backend/scripts/prepare_android_stale_context_sync_failure.py
- Verify: backend/scripts/verify_android_stale_context_sync_failure.py
- Verify recovery: backend/scripts/verify_android_stale_context_recovery_state.py

Expected Android UX:

- refresh/discard stale-context guidance
- no manual conflict UI

### VERSION_MISMATCH

- Fixture: backend/scripts/prepare_android_version_mismatch_conflict.py
- Verify: backend/scripts/verify_android_version_mismatch_conflict.py
- Verify recovery: backend/scripts/verify_android_conflict_recovery_state.py --conflict-type VERSION_MISMATCH

Expected Android UX:

- pending conflict drawer/card
- discard local draft/action
- ACCEPT_SERVER acknowledgement

### WORKFLOW_INVALID

- Fixture: backend/scripts/prepare_android_workflow_invalid_conflict.py
- Verify: backend/scripts/verify_android_workflow_invalid_conflict.py
- Verify recovery: backend/scripts/verify_android_conflict_recovery_state.py --conflict-type WORKFLOW_INVALID

Expected Android UX:

- workflow-changed messaging
- no stale-context wording
- discard local action
- ACCEPT_SERVER acknowledgement

### Multi-conflict pending drawer

- Fixture: backend/scripts/prepare_android_multi_conflict_pending_drawer.py
- Verify: backend/scripts/verify_android_multi_conflict_pending_drawer.py

Expected Android UX:

- newest-first pending conflict cards
- event-id deduplication
- independent action lifecycle

## Multilingual scenarios

| State | Language | Expected |
| --- | --- | --- |
| Uttar Pradesh (9) | Hindi (hi) | Use hi labels where present, fallback to English if needed. |
| Karnataka (29) | Kannada (kn) | Fallback to English until native Kannada labels are added. |
| Maharashtra (27) | Marathi (mr) | Fallback to English until native Marathi labels are added. |
| Punjab (3) | Punjabi (pa) | Fallback to English until native Punjabi labels are added. |

Forms/screens to exercise:

- farmer registration
- parcel registration
- soil profile
- crop-cycle create
- activity log
- stale-context guidance
- conflict drawer/cards

Pass criteria:

- no blank labels
- no raw label-map JSON shown
- no hardcoded Android translations for backend-driven forms
- no on-device advisory translation
- sync behavior unchanged by selected language
