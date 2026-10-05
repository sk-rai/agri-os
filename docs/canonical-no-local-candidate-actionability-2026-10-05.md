# Canonical villages with no local candidate — actionability

## Purpose

The existing reconciliation proved that 7,306 canonical villages have neither
PIN coverage nor an exact locally reusable NWDP candidate. It did not classify
why those rows are blocked. This report reuses the same canonical classification
and unmapped NWDP source query to create actionable evidence-acquisition cohorts.

## Cohorts

Each blocked village is assigned exactly one class:

- `NO_NWDP_STATE_SOURCE`: no unmapped NWDP source evidence is available for
  the canonical state;
- `DISTRICT_IDENTITY_ALIGNMENT_REQUIRED`: state evidence exists, but no source
  district aligns by code or normalized state/district identity;
- `BLOCK_TEHSIL_ALIGNMENT_REQUIRED`: district evidence exists, but no
  normalized same-block or same-tehsil source population is present;
- `SAME_PARENT_NAME_RESEARCH_REQUIRED`: unmapped source rows exist under the
  same normalized state, district and block/tehsil, but none meets the existing
  exact candidate rules.

These are acquisition and research queues, not mapping decisions. The final
class may justify later governed transliteration or authoritative-name research,
but this report does not use fuzzy matching.

## Validated result

The read-only run partitions all 7,306 villages exactly:

| Actionability | Villages | Next step |
| --- | ---: | --- |
| `SAME_PARENT_NAME_RESEARCH_REQUIRED` | 3,939 | Build a bounded normalized-name, transliteration and alias evidence queue; retain human review. |
| `BLOCK_TEHSIL_ALIGNMENT_REQUIRED` | 2,122 | Establish block/tehsil crosswalk evidence before comparing village names. |
| `DISTRICT_IDENTITY_ALIGNMENT_REQUIRED` | 824 | Reconcile district code/name drift before lower-level matching. |
| `NO_NWDP_STATE_SOURCE` | 421 | Acquire authoritative state/LGD evidence; all are Jammu and Kashmir. |

The first local priority is the 3,939 same-parent rows because relevant NWDP
source populations already exist under the same normalized state, district and
block/tehsil. This does not make them matches: the next analysis must expose
the name evidence, detect ambiguity and source reuse, and remain review-only.

The other 2,946 hierarchy-alignment rows must not be sent into village-name
matching until their district or block/tehsil identities are reconciled. The
421 Jammu and Kashmir rows cannot advance from current local NWDP evidence.

## Safety

The report is read-only and verifies unchanged database counts. It does not
modify canonical villages, PIN links, NWDP candidates, runtime crosswalks,
projects, Android visibility, or review decisions. No class authorizes automatic
resolution.

## Reproduction

    venv/bin/python backend/scripts/report_canonical_no_local_candidate_actionability.py \
      --output-dir /tmp/canonical-no-local-candidate-actionability-v1

Generated CSV and JSON outputs belong in temporary or staged review storage and
must not be committed until their exact counts and provenance have been reviewed.
