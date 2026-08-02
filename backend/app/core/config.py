from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized app configuration. All values are read from environment
    variables (see .env.example). Never hardcode secrets here.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    # Database
    database_url: str = (
        "postgresql+asyncpg://support_saas:support_saas_dev@localhost:5432/support_saas"
    )

    # Redis / Celery (used starting phase 2)
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # LLM (used starting phase 3/4)
    anthropic_api_key: str = ""

    # Embeddings (used starting phase 2)
    voyage_api_key: str = ""
    embedding_model: str = "voyage-3"
    embedding_dimension: int = 1024

    # File storage
    upload_dir: str = "/app/uploads"
    max_upload_size_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Chunking
    chunk_size_chars: int = 3000  # ~750 tokens at ~4 chars/token
    chunk_overlap_chars: int = 300

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
