import logging
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    # Sin clave, el pipeline corre igual (ingesta y detección) y se salta el agente.
    # Es la única variable sin prefijo: ANTHROPIC_API_KEY es el nombre estándar.
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "DATAWATCH_ANTHROPIC_API_KEY")
    )
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "high"
    umbral_anomalia: float = 3.5
    log_level: str = "INFO"

    data_path: Path = BASE_DIR / "data" / "OnlineRetail.xlsx"
    db_path: Path = BASE_DIR / "data" / "datawatch_enterprise.db"
    reportes_dir: Path = BASE_DIR / "reportes"

    # Prefijo DATAWATCH_: sin él, `claude_effort` leía la CLAUDE_EFFORT que define
    # Claude Code en su terminal, y el agente corría con otro esfuerzo sin avisar.
    model_config = SettingsConfigDict(
        env_prefix="DATAWATCH_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()

settings.db_path.parent.mkdir(parents=True, exist_ok=True)
settings.reportes_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Datawatch")
