#!/usr/bin/env python3
"""Probe NWDP raw village features for current-district reconciliation.

Read-only. For the C4 hierarchy conflicts and C5 current-geometry gaps, this
joins canonical LGD villages to NWDP source features by village LGD code and
reports the legacy NWDP district-parent distribution. It does not treat NWDP
as authoritative and performs no geography or mapping writes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_DIR = ROOT / (
    "data/staged/core_stack/climate_agro_ecology_readiness"
)
DEFAULT_INPUT = DEFAULT_DIR / (
    "geography_core_layer_authoritative_research_worklist_rows.jsonl"
)

EXPECTED_INPUT_SHA256 = (
    "57ba2f06c5dec14b920c014edc16eef537fa472699ef531e2e85314abc222ae7"
)
EXPECTED_INPUT_ROW_COUNT = 108
EXPECTED_DISTRICT_COUNT = 13

TARGET_PRIORITIES = {
    "C4_STALE_HIERARCHY_CONFLICT",
    "C5_CURRENT_DISTRICT_GEOMETRY_GAP",
}
SOURCE_SYSTEM = "NWDP_GSI_VILLAGE_BOUNDARY"
SCHEMA_VERSION = (
    "geography_core_layer_nwdp_district_reconciliation_probe.v1"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-rows",
        type=Path,
        default=DEFAULT_INPUT,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DIR,
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def district_targets(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        priority = row["crosswalk_review_priority"]
        if priority not in TARGET_PRIORITIES:
            continue
        identity = (
            str(row["state_lgd_code"]),
            str(row["district_lgd_code"]),
        )
        targets.setdefault(
            identity,
            {
                "state_or_ut": row["state_or_ut"],
                "state_lgd_code": str(
                    row["state_lgd_code"]
                ),
                "district": row["district"],
                "district_lgd_code": str(
                    row["district_lgd_code"]
                ),
                "crosswalk_review_priority": priority,
                "lgd_village_count_from_worklist": int(
                    row["lgd_village_count"]
                ),
            },
        )
    return sorted(
        targets.values(),
        key=lambda row: (
            row["state_or_ut"],
            row["district_lgd_code"],
        ),
    )


def load_probe_rows(
    targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from app.core.database import SessionLocal

    district_codes = [
        row["district_lgd_code"] for row in targets
    ]

    district_sql = text(
        """
        select
          s.canonical_name as state_or_ut,
          s.lgd_code::text as state_lgd_code,
          d.canonical_name as district,
          d.lgd_code::text as district_lgd_code,
          count(v.id)::bigint as canonical_active_village_count
        from geography_districts d
        join geography_states s on s.id = d.state_id
        left join geography_villages v
          on v.district_id = d.id
         and v.is_active = true
        where d.lgd_code::text in :district_codes
        group by
          s.canonical_name,
          s.lgd_code,
          d.canonical_name,
          d.lgd_code
        order by s.canonical_name, d.lgd_code
        """
    ).bindparams(
        bindparam("district_codes", expanding=True)
    )

    parent_sql = text(
        """
        select
          d.lgd_code::text as target_district_lgd_code,
          sf.source_state_name,
          sf.source_stcode,
          sf.source_district_name,
          sf.source_dtcode,
          count(distinct v.id)::bigint
            as matched_canonical_village_count,
          count(distinct sf.id)::bigint
            as matched_source_feature_count,
          count(distinct sf.id) filter (
            where sf.geometry_validation_status = 'VALIDATED'
          )::bigint as validated_source_feature_count,
          count(distinct sf.source_vlcode)::bigint
            as distinct_source_village_code_count,
          min(sf.source_feature_index)::bigint
            as first_source_feature_index,
          max(sf.source_feature_index)::bigint
            as last_source_feature_index
        from geography_districts d
        join geography_states s
          on s.id = d.state_id
        join geography_villages v
          on v.district_id = d.id
         and v.is_active = true
        join geography_boundary_source_features sf
          on nullif(ltrim(sf.source_vlcode, '0'), '')
             = nullif(ltrim(v.lgd_code::text, '0'), '')
         and nullif(ltrim(sf.source_stcode, '0'), '')
             = nullif(ltrim(s.lgd_code::text, '0'), '')
        where d.lgd_code::text in :district_codes
        group by
          d.lgd_code,
          sf.source_state_name,
          sf.source_stcode,
          sf.source_district_name,
          sf.source_dtcode
        order by
          d.lgd_code,
          matched_canonical_village_count desc,
          sf.source_dtcode,
          sf.source_district_name
        """
    ).bindparams(
        bindparam("district_codes", expanding=True)
    )

    db = SessionLocal()
    try:
        district_rows = {
            str(row["district_lgd_code"]): dict(row)
            for row in db.execute(
                district_sql,
                {"district_codes": district_codes},
            ).mappings()
        }
        parent_rows = [
            dict(row)
            for row in db.execute(
                parent_sql,
                {
                    "district_codes": district_codes,
                },
            ).mappings()
        ]
    finally:
        db.close()

    parents_by_target: dict[str, list[dict[str, Any]]] = {}
    for row in parent_rows:
        code = str(row.pop("target_district_lgd_code"))
        for field in (
            "matched_canonical_village_count",
            "matched_source_feature_count",
            "validated_source_feature_count",
            "distinct_source_village_code_count",
            "first_source_feature_index",
            "last_source_feature_index",
        ):
            row[field] = int(row[field] or 0)
        parents_by_target.setdefault(code, []).append(row)

    result = []
    for target in targets:
        code = target["district_lgd_code"]
        canonical = district_rows.get(code)
        parents = parents_by_target.get(code, [])

        canonical_count = int(
            (canonical or {}).get(
                "canonical_active_village_count",
                0,
            )
        )
        matched_count = sum(
            row["matched_canonical_village_count"]
            for row in parents
        )
        matched_count = min(matched_count, canonical_count)
        validated_feature_count = sum(
            row["validated_source_feature_count"]
            for row in parents
        )
        source_feature_count = sum(
            row["matched_source_feature_count"]
            for row in parents
        )
        coverage_ratio = (
            round(matched_count / canonical_count, 6)
            if canonical_count
            else 0.0
        )

        normalized_target = "".join(
            character.casefold()
            for character in target["district"]
            if character.isalnum()
        )
        direct_name_match = any(
            "".join(
                character.casefold()
                for character in str(
                    parent["source_district_name"] or ""
                )
                if character.isalnum()
            )
            == normalized_target
            for parent in parents
        )

        if matched_count == 0:
            evidence_status = (
                "NWDP_NO_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
            )
        elif matched_count == canonical_count:
            evidence_status = (
                "NWDP_COMPLETE_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
            )
        else:
            evidence_status = (
                "NWDP_PARTIAL_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
            )

        result.append(
            {
                **target,
                "canonical_active_village_count": canonical_count,
                "matched_canonical_village_count": matched_count,
                "unmatched_canonical_village_count": max(
                    canonical_count - matched_count,
                    0,
                ),
                "nwdp_village_code_coverage_ratio": coverage_ratio,
                "nwdp_source_parent_count": len(parents),
                "nwdp_direct_district_name_match": (
                    direct_name_match
                ),
                "nwdp_matched_source_feature_count": (
                    source_feature_count
                ),
                "nwdp_validated_source_feature_count": (
                    validated_feature_count
                ),
                "all_matched_source_geometry_validated": (
                    source_feature_count > 0
                    and validated_feature_count
                    == source_feature_count
                ),
                "nwdp_source_parents": parents,
                "evidence_status": evidence_status,
                "recommended_use": (
                    "NON_AUTHORITATIVE_RECONCILIATION_EVIDENCE_ONLY"
                    if matched_count
                    else "AUTHORITATIVE_SOURCE_OR_NEW_GEOMETRY_REQUIRED"
                ),
                "mapping_approval_authorized": False,
                "canonical_change_authorized": False,
                "database_writes_attempted": False,
            }
        )

    return result


def main() -> int:
    args = parse_args()
    input_hash = sha256(args.input_rows)
    input_rows = read_jsonl(args.input_rows)
    targets = district_targets(input_rows)
    probe_rows = load_probe_rows(targets)

    counts_by_status = Counter(
        row["evidence_status"] for row in probe_rows
    )
    districts_with_evidence = sum(
        row["matched_canonical_village_count"] > 0
        for row in probe_rows
    )
    complete_districts = sum(
        row["evidence_status"]
        == "NWDP_COMPLETE_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
        for row in probe_rows
    )
    partial_districts = sum(
        row["evidence_status"]
        == "NWDP_PARTIAL_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
        for row in probe_rows
    )
    no_evidence_districts = sum(
        row["evidence_status"]
        == "NWDP_NO_VILLAGE_CODE_RECONCILIATION_EVIDENCE"
        for row in probe_rows
    )

    checks = {
        "input_sha256_pinned": (
            input_hash == EXPECTED_INPUT_SHA256
        ),
        "input_row_count_exact": (
            len(input_rows) == EXPECTED_INPUT_ROW_COUNT
        ),
        "target_district_count_exact": (
            len(targets) == EXPECTED_DISTRICT_COUNT
        ),
        "probe_row_count_exact": (
            len(probe_rows) == EXPECTED_DISTRICT_COUNT
        ),
        "target_identity_unique": (
            len(
                {
                    (
                        row["state_lgd_code"],
                        row["district_lgd_code"],
                    )
                    for row in probe_rows
                }
            )
            == len(probe_rows)
        ),
        "canonical_districts_resolved": all(
            row["canonical_active_village_count"] > 0
            for row in probe_rows
        ),
        "source_parent_counts_reconcile": all(
            row["nwdp_source_parent_count"]
            == len(row["nwdp_source_parents"])
            for row in probe_rows
        ),
        "no_database_writes": True,
        "not_authorized": True,
        "nwdp_not_treated_as_authoritative": all(
            row["recommended_use"]
            != "AUTHORITATIVE_MAPPING_SOURCE"
            for row in probe_rows
        ),
    }
    healthy = all(checks.values())

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_probe_rows.jsonl"
    )
    csv_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_probe.csv"
    )
    summary_path = args.output_dir / (
        "geography_core_layer_nwdp_district_reconciliation_probe.json"
    )

    with rows_path.open("w", encoding="utf-8") as handle:
        for row in probe_rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

    flat_rows = []
    for row in probe_rows:
        flat = dict(row)
        flat["nwdp_source_parents"] = json.dumps(
            row["nwdp_source_parents"],
            ensure_ascii=False,
            sort_keys=True,
        )
        flat_rows.append(flat)

    fieldnames = sorted(
        {field for row in flat_rows for field in row}
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)

    core_summary = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "NWDP_RECONCILIATION_EVIDENCE_PROBED_NOT_AUTHORIZED"
            if healthy
            else "NWDP_RECONCILIATION_PROBE_INVALID"
        ),
        "healthy": healthy,
        "database_writes_attempted": False,
        "input": str(args.input_rows.resolve()),
        "input_sha256": input_hash,
        "target_district_count": len(targets),
        "districts_with_nwdp_evidence": districts_with_evidence,
        "complete_evidence_district_count": complete_districts,
        "partial_evidence_district_count": partial_districts,
        "no_evidence_district_count": no_evidence_districts,
        "counts_by_evidence_status": dict(
            sorted(counts_by_status.items())
        ),
        "checks": checks,
        "policy": {
            "lgd_remains_canonical": True,
            "nwdp_is_non_authoritative_reconciliation_evidence": True,
            "nwdp_geometry_can_seed_authoritative_research": True,
            "automatic_parent_reconciliation_authorized": False,
            "canonical_geography_changes_authorized": False,
            "core_mapping_approval_authorized": False,
            "database_apply_authorized": False,
            "runtime_activation_authorized": False,
            "android_behavior_change_authorized": False,
        },
    }

    summary = {
        **core_summary,
        "rows": str(rows_path.resolve()),
        "rows_sha256": sha256(rows_path),
        "csv": str(csv_path.resolve()),
        "csv_sha256": sha256(csv_path),
        "summary_checksum": canonical_sha256(core_summary),
    }
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
