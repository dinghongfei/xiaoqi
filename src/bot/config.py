from pathlib import Path
from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BOT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = BOT_ROOT / ".env"


class SettingsError(ValueError):
    pass


class Settings(BaseSettings):
    """Host process settings. Skill-only keys in .env are ignored."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_encrypt_key: str = ""
    feishu_verification_token: str = ""

    hugo_deploy_dir: Optional[Path] = BOT_ROOT / "preview"
    last_job_path: Path = BOT_ROOT / "data" / "last-job.json"

    agent_bin: str = ""
    agent_timeout: int = 600

    preview_host: str = "127.0.0.1"
    preview_port: int = 1314

    @field_validator("hugo_deploy_dir", mode="before")
    @classmethod
    def empty_optional_path_to_none(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, Path) and not str(value).strip():
            return None
        return value

    @property
    def preview_dir(self) -> Path:
        if self.hugo_deploy_dir is not None:
            return Path(self.hugo_deploy_dir)
        return BOT_ROOT / "preview"


def resolve_env_file(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    return DEFAULT_ENV_FILE


def get_settings(env_file: str | Path | None = None) -> Settings:
    path = resolve_env_file(env_file)
    if path.exists():
        return Settings(_env_file=path)
    return Settings()


def require_feishu_settings(settings: Settings) -> None:
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise SettingsError("请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
