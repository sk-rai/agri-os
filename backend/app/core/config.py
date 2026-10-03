from pathlib import Path

from pydantic_settings import BaseSettings


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Agri-OS"
    VERSION: str = "0.1.0"

    # Database
    DB_USER: str = "agrios_user"
    DB_PASSWORD: str = "agrios_dev_2026"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "agrios_dev"

    # Soil enrichment providers
    SOILGRIDS_BASE_URL: str = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    SOILGRIDS_TIMEOUT_SECONDS: int = 20

    # External provider credentials and safety controls
    WEATHER_PROVIDER_API_KEY: str | None = None
    WEATHER_PROVIDER_API_SECRET: str | None = None
    WEATHER_PROVIDER_LIVE_EXECUTION_ENABLED: bool = False
    SOIL_PROVIDER_API_KEY: str | None = None
    SOIL_PROVIDER_API_SECRET: str | None = None
    SOIL_PROVIDER_LIVE_EXECUTION_ENABLED: bool = False

    # Fail-closed until separately authorized.
    NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED: bool = False
    NWDP_BOUNDARY_RUNTIME_LOOKUP_STATEMENT_TIMEOUT_MS: int = 2000

    # Distributed rate limiting remains independently disabled until
    # Redis operations and multi-worker tests are complete.
    NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED: bool = False
    NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_REDIS_URL: str | None = None
    NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE: str = (
        "agrios:nwdp-runtime-lookup:v1"
    )
    NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_WINDOW_SECONDS: int = 60
    NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_GLOBAL_REQUESTS: int = 600

    # Server-side tenant tiers. The tier is read from tenants.config;
    # it is never accepted from a request header.
    NWDP_BOUNDARY_RUNTIME_LOOKUP_FREE_ACTOR_REQUESTS: int = 10
    NWDP_BOUNDARY_RUNTIME_LOOKUP_FREE_TENANT_REQUESTS: int = 30
    NWDP_BOUNDARY_RUNTIME_LOOKUP_STANDARD_ACTOR_REQUESTS: int = 30
    NWDP_BOUNDARY_RUNTIME_LOOKUP_STANDARD_TENANT_REQUESTS: int = 120
    NWDP_BOUNDARY_RUNTIME_LOOKUP_PRO_ACTOR_REQUESTS: int = 120
    NWDP_BOUNDARY_RUNTIME_LOOKUP_PRO_TENANT_REQUESTS: int = 600
    NWDP_BOUNDARY_RUNTIME_LOOKUP_ENTERPRISE_ACTOR_REQUESTS: int = 600
    NWDP_BOUNDARY_RUNTIME_LOOKUP_ENTERPRISE_TENANT_REQUESTS: int = 3000

    # Project village resolution applies remain separately gated.
    PROJECT_VILLAGE_RESOLUTION_CANONICAL_APPLY_ENABLED: bool = False

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    class Config:
        env_file = str(PROJECT_ENV_FILE)
        case_sensitive = True


settings = Settings()
