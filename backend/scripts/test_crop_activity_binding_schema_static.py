#!/usr/bin/env python3
"""Static checks for migration 071 and its matching ORM schema."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic/versions/071_add_crop_activity_command_bindings.py"
SYNC_MODELS = ROOT / "app/modules/sync/models.py"
WORKFLOW_MODELS = ROOT / "app/modules/workflow/models.py"
ALEMBIC_ENV = ROOT / "alembic/env.py"


def require(source: str, fragment: str) -> None:
    assert fragment in source, f"missing static contract: {fragment}"


def main() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    sync_models = SYNC_MODELS.read_text(encoding="utf-8")
    workflow_models = WORKFLOW_MODELS.read_text(encoding="utf-8")
    alembic_env = ALEMBIC_ENV.read_text(encoding="utf-8")

    for fragment in (
        'revision: str = "071"',
        'down_revision: Union[str, None] = "070"',
        '"crop_activity_command_bindings"',
        '"crop_activity_sync_event_bindings"',
        '"irrigation_source"',
        '"duration_hours"',
        "ck_crop_activity_command_binding_origin_kind",
        "ck_crop_activity_command_binding_origin_event",
        "uq_crop_activity_sync_event_binding_activity",
        "fk_crop_activity_command_binding_activity",
        "fk_crop_activity_sync_event_binding_event",
        "071_DOWNGRADE_BLOCKED",
        "IN ACCESS EXCLUSIVE MODE",
        "has_bindings or has_irrigation_content",
    ):
        require(migration, fragment)

    for fragment in (
        "class CropActivityCommandBinding(Base):",
        "class CropActivitySyncEventBinding(Base):",
        'name="fk_crop_activity_command_binding_activity"',
        'name="fk_crop_activity_sync_event_binding_event"',
        'name="fk_crop_activity_sync_event_binding_activity"',
        "intent_sha256 = Column(CHAR(64), nullable=False)",
        "ck_crop_activity_command_binding_origin_event",
        "ck_crop_activity_sync_event_binding_outcome",
        "uq_crop_activity_sync_event_binding_activity",
    ):
        require(sync_models, fragment)

    require(workflow_models, "irrigation_source = Column(String(100))")
    require(workflow_models, "duration_hours = Column(DECIMAL(10, 2))")
    require(alembic_env, "CropActivityCommandBinding")
    require(alembic_env, "CropActivitySyncEventBinding")
    print("CROP_ACTIVITY_BINDING_SCHEMA_STATIC_OK")


if __name__ == "__main__":
    main()
