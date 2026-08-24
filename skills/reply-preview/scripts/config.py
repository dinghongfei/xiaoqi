"""Portable workspace settings (no dependency on the host project package)."""

from __future__ import annotations

import os
from pathlib import Path

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

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    last_job_path: Path = BOT_ROOT / "data" / "last-job.json"


def resolve_env_file(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    return DEFAULT_ENV_FILE


def get_settings(env_file: str | Path | None = None) -> Settings:
    path = resolve_env_file(env_file)
    if path.exists():
        return Settings(_env_file=path)
    return Settings()
