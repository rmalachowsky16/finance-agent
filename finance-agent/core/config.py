"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All runtime configuration. Values are read from environment / .env file."""

    # Anthropic
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")

    # Supabase
    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_key: str = Field(..., alias="SUPABASE_KEY")

    # Upstash Redis
    upstash_redis_url: str = Field(..., alias="UPSTASH_REDIS_URL")
    upstash_redis_token: str = Field(..., alias="UPSTASH_REDIS_TOKEN")

    # External data providers
    newsapi_key: str = Field(..., alias="NEWSAPI_KEY")
    fred_api_key: str = Field(..., alias="FRED_API_KEY")

    # SEC EDGAR identity (required by EDGAR fair-access policy)
    edgar_company_name: str = Field("FinanceAgent", alias="EDGAR_COMPANY_NAME")
    edgar_email: str = Field("agent@example.com", alias="EDGAR_EMAIL")

    # Chunker defaults
    chunk_size_tokens: int = Field(3000, alias="CHUNK_SIZE_TOKENS")
    chunk_overlap_tokens: int = Field(200, alias="CHUNK_OVERLAP_TOKENS")

    model_config = {"env_file": ".env", "populate_by_name": True}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (loaded once at startup)."""
    return Settings()  # type: ignore[call-arg]
