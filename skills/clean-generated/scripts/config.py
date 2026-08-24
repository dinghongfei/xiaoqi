"""Portable workspace settings (no dependency on the host project package)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _detect_root() -> Path:
    env = (os.environ.get("BOT_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    cwd = Path.cwd().resolve()
    if (cwd / "site" / "hugo.toml").is_file() or (cwd / "hugo.toml").is_file():
        return cwd
    try:
        maybe = Path(__file__).resolve().parents[3]
        if (maybe / "site" / "hugo.toml").is_file():
            return maybe
    except IndexError:
        pass
    return cwd


BOT_ROOT = _detect_root()
DEFAULT_ENV_FILE = BOT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hugo_deploy_dir: Optional[Path] = BOT_ROOT / "preview"
    last_job_path: Path = BOT_ROOT / "data" / "last-job.json"
    jobs_dir: Path = BOT_ROOT / "data" / "jobs"

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
