from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_version_file() -> str:
    for candidate in (REPO_ROOT / "VERSION", Path("/app/VERSION")):
        try:
            return candidate.read_text().strip()
        except OSError:
            continue
    return "dev"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_version: str = ""
    build_time: str = ""

    # SQLite by default. Point at Postgres (postgresql+psycopg://...) for heavier use.
    database_url: str = "sqlite:////data/family.db"

    # Encrypts stored Google OAuth tokens and signs OAuth state. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_key: str = "dev-insecure-change-me"

    google_client_id: str = ""
    google_client_secret: str = ""
    public_base_url: str = "http://localhost:8080"

    sync_interval_seconds: int = 300
    push_interval_seconds: int = 15
    sync_past_days: int = 90
    sync_enabled: bool = True

    cors_origins: str = "*"

    @property
    def version(self) -> str:
        return self.app_version or _read_version_file()

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/api/accounts/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
