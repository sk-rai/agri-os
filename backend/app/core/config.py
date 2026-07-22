from pydantic_settings import BaseSettings


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

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
