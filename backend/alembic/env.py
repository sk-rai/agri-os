import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add backend directory to path so 'app' package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base
from app.core.config import settings

# Import all models so they register with Base.metadata
from app.modules.workflow.models import (  # noqa: F401
    CropCycle,
    CropStageInstance,
    CropActivity,
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkflowTemplateStage,
    WorkflowTemplateRecommendation,
    WorkflowTemplateEnablement,
    WorkflowTemplateOverride,
    WorkflowTemplateAuditEvent,
)

from app.modules.auth.models import TenantUserAccessAuditEvent  # noqa: F401
from app.modules.farmer.models import FarmerProjectEnrollment  # noqa: F401
from app.modules.sync.models import (  # noqa: F401
    CropActivityCommandBinding,
    CropActivitySyncEventBinding,
)

from app.modules.master_data.models import (  # noqa: F401
    GeographyState,
    GeographyDistrict,
    GeographyBlock,
    GeographyVillage,
    GeographyClimateRegion,
    GeographyClimateRegionMapping,
    SoilType,
    Season,
    CropCategory,
    Crop,
    CropVariety,
    CropLifecycleTemplate,
    CropTaxonomyNode,
    CropTaxonomyEdge,
    CropTaxonomyAssignment,
    CropPropagationType,
    CropPropagationOption,
    CropClimateSuitabilityRule,
    CropClimateSuitabilityOverride,
    InputCategory,
    Manufacturer,
    AgriculturalInput,
    AgriculturalInputAuditEvent,
    ProjectInputAssignment,
    ProjectInputAssignmentAuditEvent,
    InputCatalogImportBatch,
    AgriculturalProduct,
    AgriculturalProductPackage,
    ProjectProductApproval,
    ProductCatalogAuditEvent,
    CropStageInputRule,
    CropStageInputRuleAuditEvent,
)

config = context.config
supplied_connection = config.attributes.get("connection")

if supplied_connection is None:
    # Preserve the normal application migration path. A verifier-supplied
    # connection has already been admitted and must not be replaced or have its
    # logging configuration reinitialized here.
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    def run(connection) -> None:
        options = dict(
            connection=connection,
            target_metadata=target_metadata,
        )
        version_table_schema = config.attributes.get("version_table_schema")
        if version_table_schema is not None:
            options["version_table_schema"] = version_table_schema
        context.configure(**options)
        with context.begin_transaction():
            context.run_migrations()

    if supplied_connection is not None:
        if not supplied_connection.engine.hide_parameters:
            raise RuntimeError("SUPPLIED_CONNECTION_MUST_HIDE_PARAMETERS")
        run(supplied_connection)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
