#!/usr/bin/env python3
"""Set-based throughput primitives for validation-metadata rollout V2.

This module is intentionally disconnected from campaign execution. It defines
the reviewed throughput envelope and SQL that will replace the V1 per-row loop
after fixture, rollback, and benchmark approval.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable

from sqlalchemy import text


SOURCE_TABLE = "geography_boundary_source_features"
EVENT_TABLE = "geography_boundary_validation_metadata_events"

DEFAULT_ROWS_PER_STATE_TRANSACTION = 25_000
MAXIMUM_ROWS_PER_STATE_TRANSACTION = 50_000
DEFAULT_WRITER_COUNT = 1
MAXIMUM_WRITER_COUNT = 2


@dataclass(frozen=True)
class ThroughputProfile:
    rows_per_state_transaction: int = (
        DEFAULT_ROWS_PER_STATE_TRANSACTION
    )
    writer_count: int = DEFAULT_WRITER_COUNT

    def validate(self) -> None:
        if not (
            1
            <= self.rows_per_state_transaction
            <= MAXIMUM_ROWS_PER_STATE_TRANSACTION
        ):
            raise ValueError(
                "V2_TRANSACTION_ROW_LIMIT_INVALID"
            )
        if not (
            1 <= self.writer_count <= MAXIMUM_WRITER_COUNT
        ):
            raise ValueError("V2_WRITER_COUNT_INVALID")


def apply_statements() -> tuple[str, str, str, str]:
    """Return set-based SQL for one atomic state transaction."""

    stage = """
        create temporary table validation_metadata_v2_input
        on commit drop as
        select *
        from jsonb_to_recordset(cast(:rows as jsonb)) as row(
          event_id uuid,
          source_feature_id uuid,
          source_feature_index integer,
          source_geometry_hash text,
          source_bbox jsonb,
          transformed_bbox jsonb,
          transformed_centroid jsonb
        )
    """

    insert_events = f"""
        insert into {EVENT_TABLE} (
          id,
          source_feature_id,
          import_batch_id,
          source_system,
          state_or_ut,
          source_feature_index,
          source_sha256,
          plan_checksum,
          geometry_hash_algorithm,
          rollback_token,
          apply_status,
          before_values,
          planned_values,
          after_values,
          apply_report,
          rollback_report,
          metadata,
          applied_by,
          applied_at,
          is_active,
          version
        )
        select
          input.event_id,
          source.id,
          source.import_batch_id,
          'NWDP_GSI_VILLAGE_BOUNDARY',
          :state_or_ut,
          source.source_feature_index,
          :source_sha256,
          :plan_checksum,
          'NWDP_GEOJSON_GEOMETRY_CANONICAL_V1',
          :rollback_token,
          'PLANNED',
          jsonb_build_object(
            'source_geometry_hash',
              source.source_geometry_hash,
            'source_bbox',
              source.source_bbox,
            'transformed_bbox',
              source.transformed_bbox,
            'transformed_centroid',
              source.transformed_centroid,
            'geometry_validation_status',
              source.geometry_validation_status,
            'eligible_for_runtime_after_promotion',
              source.eligible_for_runtime_after_promotion,
            'metadata',
              source.metadata
          ),
          jsonb_build_object(
            'source_feature_id',
              input.source_feature_id,
            'source_feature_index',
              input.source_feature_index,
            'source_geometry_hash',
              input.source_geometry_hash,
            'source_bbox',
              input.source_bbox,
            'transformed_bbox',
              input.transformed_bbox,
            'transformed_centroid',
              input.transformed_centroid,
            'runtime_eligibility_change_planned',
              false
          ),
          '{{}}'::jsonb,
          '{{}}'::jsonb,
          '{{}}'::jsonb,
          cast(:event_metadata as jsonb),
          :applied_by,
          now(),
          false,
          'v1.0'
        from validation_metadata_v2_input input
        join {SOURCE_TABLE} source
          on source.id = input.source_feature_id
        where source.import_batch_id =
                cast(:import_batch_id as uuid)
          and source.source_feature_index =
                input.source_feature_index
          and source.geometry_validation_status =
                'NOT_VALIDATED'
          and source.eligible_for_runtime_after_promotion =
                false
        order by source.source_feature_index
        for update of source
        returning id
    """

    update_sources = f"""
        update {SOURCE_TABLE} source
        set
          source_geometry_hash =
            input.source_geometry_hash,
          source_bbox =
            input.source_bbox,
          transformed_bbox =
            input.transformed_bbox,
          transformed_centroid =
            input.transformed_centroid,
          geometry_validation_status =
            'VALIDATED',
          metadata =
            coalesce(source.metadata, '{{}}'::jsonb)
            || jsonb_build_object(
              :marker,
              jsonb_build_object(
                'event_id',
                  input.event_id,
                'plan_checksum',
                  :plan_checksum,
                'rollback_token',
                  :rollback_token
              )
            )
        from validation_metadata_v2_input input
        where source.id = input.source_feature_id
          and source.geometry_validation_status =
                'NOT_VALIDATED'
          and source.eligible_for_runtime_after_promotion =
                false
        returning source.id
    """

    activate_events = f"""
        update {EVENT_TABLE} event
        set
          apply_status = 'APPLIED',
          after_values = jsonb_build_object(
            'source_geometry_hash',
              source.source_geometry_hash,
            'source_bbox',
              source.source_bbox,
            'transformed_bbox',
              source.transformed_bbox,
            'transformed_centroid',
              source.transformed_centroid,
            'geometry_validation_status',
              source.geometry_validation_status,
            'eligible_for_runtime_after_promotion',
              source.eligible_for_runtime_after_promotion,
            'metadata',
              source.metadata
          ),
          apply_report =
            cast(:apply_report as jsonb),
          is_active = true,
          updated_at = now()
        from validation_metadata_v2_input input
        join {SOURCE_TABLE} source
          on source.id = input.source_feature_id
        where event.id = input.event_id
          and event.apply_status = 'PLANNED'
          and event.is_active = false
        returning event.id
    """

    return (
        stage,
        insert_events,
        update_sources,
        activate_events,
    )


def rollback_statements() -> tuple[str, str]:
    """Return set-based restoration and event finalization SQL."""

    restore_sources = f"""
        update {SOURCE_TABLE} source
        set
          source_geometry_hash =
            event.before_values->>'source_geometry_hash',
          source_bbox =
            event.before_values->'source_bbox',
          transformed_bbox =
            event.before_values->'transformed_bbox',
          transformed_centroid =
            event.before_values->'transformed_centroid',
          geometry_validation_status =
            event.before_values
              ->>'geometry_validation_status',
          eligible_for_runtime_after_promotion =
            cast(
              event.before_values
                ->>'eligible_for_runtime_after_promotion'
              as boolean
            ),
          metadata =
            event.before_values->'metadata'
        from {EVENT_TABLE} event
        where source.id = event.source_feature_id
          and event.plan_checksum = :plan_checksum
          and event.rollback_token = :rollback_token
          and event.apply_status = 'APPLIED'
          and event.is_active = true
        returning source.id
    """

    finalize_events = f"""
        update {EVENT_TABLE}
        set
          apply_status = 'ROLLED_BACK',
          rollback_report =
            cast(:rollback_report as jsonb),
          rolled_back_by = :operator,
          rolled_back_at = now(),
          is_active = false,
          updated_at = now()
        where plan_checksum = :plan_checksum
          and rollback_token = :rollback_token
          and apply_status = 'APPLIED'
          and is_active = true
        returning id
    """

    return restore_sources, finalize_events

def validate_authorized_rows(
    rows: list[dict[str, Any]],
    authorized_row_count: int,
) -> None:
    """Validate exact count and identity uniqueness before SQL execution."""

    if not (
        1
        <= authorized_row_count
        <= MAXIMUM_ROWS_PER_STATE_TRANSACTION
    ):
        raise ValueError(
            "V2_AUTHORIZED_ROW_COUNT_INVALID"
        )

    if len(rows) != authorized_row_count:
        raise ValueError(
            "V2_AUTHORIZED_ROW_COUNT_MISMATCH"
        )

    identity_fields = (
        "event_id",
        "source_feature_id",
        "source_feature_index",
    )

    for field in identity_fields:
        values = [row.get(field) for row in rows]

        if any(value in (None, "") for value in values):
            raise ValueError(
                f"V2_ROW_IDENTITY_MISSING:{field}"
            )

        if len(values) != len(set(values)):
            raise ValueError(
                f"V2_ROW_IDENTITY_NOT_UNIQUE:{field}"
            )


def _returned_count(result: Any) -> int:
    """Count RETURNING rows without relying on driver rowcount semantics."""

    return len(result.fetchall())


def execute_apply_transaction(
    conn: Any,
    *,
    rows: list[dict[str, Any]],
    authorized_row_count: int,
    parameters: dict[str, Any],
    after_phase: Callable[[str], None] | None = None,
) -> dict[str, int | str]:
    """Execute a V2 apply inside the caller-owned database transaction.

    The caller must open the transaction and roll it back on any exception.
    """

    validate_authorized_rows(
        rows,
        authorized_row_count,
    )

    feature_ids = [
        row["source_feature_id"]
        for row in rows
    ]

    existing = conn.execute(text(f"""
        select
          count(*) as event_count,
          count(distinct source_feature_id)
            as source_feature_count,
          count(*) filter (
            where apply_status = 'APPLIED'
              and is_active = true
          ) as active_applied_count,
          count(*) filter (
            where source_feature_id =
              any(cast(:source_feature_ids as uuid[]))
          ) as matching_source_count
        from {EVENT_TABLE}
        where plan_checksum = :plan_checksum
          and rollback_token = :rollback_token
    """), {
        "plan_checksum": parameters["plan_checksum"],
        "rollback_token": parameters["rollback_token"],
        "source_feature_ids": feature_ids,
    }).mappings().one()

    existing_counts = {
        key: int(value or 0)
        for key, value in existing.items()
    }

    if existing_counts["event_count"] > 0:
        if all(
            existing_counts[key] == authorized_row_count
            for key in (
                "event_count",
                "source_feature_count",
                "active_applied_count",
                "matching_source_count",
            )
        ):
            return {
                "status": "IDEMPOTENT_NO_OP",
                "staged_row_count": 0,
                "inserted_event_count": 0,
                "updated_source_count": 0,
                "activated_event_count": 0,
            }

        raise RuntimeError(
            "V2_PARTIAL_OR_CONFLICTING_EVENT_SET"
        )

    stage, insert_events, update_sources, activate_events = (
        apply_statements()
    )

    conn.execute(
        text(stage),
        {"rows": json.dumps(rows)},
    )

    staged = conn.execute(text("""
        select
          count(*) as row_count,
          count(distinct event_id) as event_count,
          count(distinct source_feature_id)
            as source_feature_count,
          count(distinct source_feature_index)
            as source_index_count
        from validation_metadata_v2_input
    """)).mappings().one()

    staged_counts = {
        key: int(value or 0)
        for key, value in staged.items()
    }

    if any(
        value != authorized_row_count
        for value in staged_counts.values()
    ):
        raise RuntimeError(
            "V2_STAGED_IDENTITY_COUNT_MISMATCH"
        )

    inserted = _returned_count(
        conn.execute(
            text(insert_events),
            parameters,
        )
    )
    if inserted != authorized_row_count:
        raise RuntimeError(
            "V2_EVENT_INSERT_COUNT_MISMATCH"
        )

    if after_phase is not None:
        after_phase("EVENT_INSERT")

    updated = _returned_count(
        conn.execute(
            text(update_sources),
            parameters,
        )
    )
    if updated != authorized_row_count:
        raise RuntimeError(
            "V2_SOURCE_UPDATE_COUNT_MISMATCH"
        )

    if after_phase is not None:
        after_phase("SOURCE_UPDATE")

    activated = _returned_count(
        conn.execute(
            text(activate_events),
            parameters,
        )
    )
    if activated != authorized_row_count:
        raise RuntimeError(
            "V2_EVENT_ACTIVATION_COUNT_MISMATCH"
        )

    if after_phase is not None:
        after_phase("EVENT_ACTIVATION")

    return {
        "status": "APPLIED",
        "staged_row_count": authorized_row_count,
        "inserted_event_count": inserted,
        "updated_source_count": updated,
        "activated_event_count": activated,
    }


def execute_rollback_transaction(
    conn: Any,
    *,
    authorized_row_count: int,
    parameters: dict[str, Any],
) -> dict[str, int]:
    """Execute set-based rollback in the caller-owned transaction."""

    if not (
        1
        <= authorized_row_count
        <= MAXIMUM_ROWS_PER_STATE_TRANSACTION
    ):
        raise ValueError(
            "V2_AUTHORIZED_ROW_COUNT_INVALID"
        )

    restore_sources, finalize_events = (
        rollback_statements()
    )

    restored = _returned_count(
        conn.execute(
            text(restore_sources),
            parameters,
        )
    )
    if restored != authorized_row_count:
        raise RuntimeError(
            "V2_ROLLBACK_SOURCE_COUNT_MISMATCH"
        )

    finalized = _returned_count(
        conn.execute(
            text(finalize_events),
            parameters,
        )
    )
    if finalized != authorized_row_count:
        raise RuntimeError(
            "V2_ROLLBACK_EVENT_COUNT_MISMATCH"
        )

    return {
        "restored_source_count": restored,
        "rolled_back_event_count": finalized,
    }

