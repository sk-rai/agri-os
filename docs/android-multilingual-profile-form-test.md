# Android multilingual profile-form test plan

Status date: 2026-08-08

This plan extends the next Android sync/emulator pass with backend-driven multilingual label checks for profile forms, option sets, and farmer-facing sync/conflict screens.

## Why now

CoRE/LGD promoted coverage is sufficient for Android testing across multiple state contexts:

- Uttar Pradesh (`9`) � existing LGD/profile baseline, Hindi-oriented smoke path;
- Karnataka (`29`) � active CoRE/LGD districts available for Kannada-context fallback testing;
- Maharashtra (`27`) � active CoRE/LGD districts available for Marathi-context fallback testing;
- Punjab (`3`) � active CoRE/LGD districts available for Punjabi-context fallback testing.

The goal is not to claim native translations are complete. The goal is to prove Android renders backend-provided labels correctly and falls back safely when a preferred language key is missing.

## Backend audit

Read-only script:

```bash
cd ~/projects/farmint/backend
../venv/bin/python scripts/audit_android_multilingual_form_labels.py | python3 -m json.tool
```

Latest local result:

- forms audited: 5;
- option sets audited: 11;
- label maps audited: 288;
- English labels present: 288 / 288;
- Hindi label keys present: 288 / 288;
- Kannada native labels present: 0 / 288;
- Marathi native labels present: 0 / 288;
- Punjabi native labels present: 0 / 288;
- English fallback available for Kannada/Marathi/Punjabi: 288 / 288.

Readiness interpretation:

- English fallback is complete and must always render.
- Hindi is ready for label-key smoke testing, though many current values are English text under the `hi` key and should not be treated as reviewed Hindi translation quality.
- Kannada, Marathi, and Punjabi are fallback scenarios until native labels are added.

## Android label resolution contract

For every backend-driven label map, Android should resolve:

```kotlin
labels[currentLanguageCode] ?: labels["en"]
```

Android must not hardcode translations for backend-driven forms and must not translate advisories on-device.

## State/language scenarios for next test batch

| State | Language | District examples | Expected label behavior |
| --- | --- | --- | --- |
| Uttar Pradesh (`9`) | Hindi (`hi`) | Agra, Aligarh | Prefer `hi` key where present; fallback to `en` if needed. |
| Karnataka (`29`) | Kannada (`kn`) | Bagalkote, Bengaluru Urban, Dakshina Kannada | Fallback to `en` until native `kn` labels are added. |
| Maharashtra (`27`) | Marathi (`mr`) | Ahmednagar, Akola, Bhandara | Fallback to `en` until native `mr` labels are added. |
| Punjab (`3`) | Punjabi (`pa`) | Amritsar, Bathinda, Faridkot | Fallback to `en` until native `pa` labels are added. |

## Forms and fields to exercise

Minimum Android Maestro coverage should open and render:

- farmer registration;
- parcel registration;
- soil profile;
- crop-cycle create;
- activity log.

For each language scenario, verify representative labels from:

- form title;
- required text field label;
- dropdown/single-select label;
- option-set item label;
- GPS field label/hint;
- conditional field label, such as leased land annual rent or soil lab/SHC details.

## Sync/conflict UI language checks

Run multilingual rendering checks around the same sync matrix:

1. stale-context failure � refresh/discard guidance should render with backend-safe fallback labels;
2. `VERSION_MISMATCH` � conflict drawer and discard/ack copy should render without missing label crashes;
3. `WORKFLOW_INVALID` � workflow-changed copy should render without stale-context wording;
4. multi-conflict pending drawer � multiple cards should render in the selected language context or fallback cleanly;
5. queue/backpressure/resume flows � progress/error labels should remain stable while language preference is non-English.

## Pass criteria

A scenario passes when:

- Android does not show raw label-map JSON;
- Android does not show blank labels for any audited backend-driven field;
- Hindi path resolves from `hi` where present;
- Kannada/Marathi/Punjabi paths visibly fall back to English instead of crashing or blanking;
- offline sync, pending conflict, and conflict acknowledgement behavior is unchanged by language selection;
- Android screenshots/logs record the selected `language_preference` and state context.

## Future native-label expansion

When native labels are added for `kn`, `mr`, or `pa`, update `backend/scripts/audit_android_multilingual_form_labels.py` expectations and convert those scenarios from fallback tests to native-label tests. Advisory translation remains separately review-gated under `docs/language-localization-advisory-runbook.md`.