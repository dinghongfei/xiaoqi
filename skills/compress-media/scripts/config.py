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
    # <root>/skills/<skill>/scripts/config.py -> parents[3] == root
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
    feishu_encrypt_key: str = ""
    feishu_verification_token: str = ""

    hugo_root: Path = BOT_ROOT / "site"
    hugo_deploy_dir: Optional[Path] = BOT_ROOT / "preview"
    site_base_url: str = "http://127.0.0.1:1314"

    state_db_path: Path = BOT_ROOT / "data" / "state.db"
    last_job_path: Path = BOT_ROOT / "data" / "last-job.json"
    jobs_dir: Path = BOT_ROOT / "data" / "jobs"

    lark_cli_bin: str = "lark-cli"
    lark_cli_identity: str = "bot"
    lark_cli_profile: str = "xiaoqi"
    lark_cli_sync_config: bool = True

    publish_secret_key: str = ""
    publish_timeout: int = 300
    git_push_enabled: bool = False

    hugo_bin: Optional[Path] = None
    hugo_build_timeout: int = 120

    ossutil_bin: str = "aliyun ossutil"
    oss_bucket: str = ""
    ossutil_config: Optional[Path] = None

    git_remote: str = "origin"
    git_branch: str = "main"
    git_commit_message: str = "chore: publish content"
    git_user_name: str = ""
    git_user_email: str = ""

    media_compress_enabled: bool = True
    video_compress_enabled: bool = True
    ffmpeg_bin: str = "ffmpeg"
    ffmpeg_timeout: int = 600
    video_max_width: int = 1280
    video_crf_h264: int = 23
    video_crf_av1: int = 30
    video_crf_vp9: int = 30
    image_max_width: int = 1920
    image_webp_quality: int = 80

    llm_provider: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout: int = 120

    agent_bin: str = ""
    agent_timeout: int = 600

    preview_host: str = "127.0.0.1"
    preview_port: int = 1314

    @field_validator("hugo_bin", "hugo_deploy_dir", "ossutil_config", mode="before")
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
    def resolved_hugo_bin(self) -> Path:
        root = self.hugo_root.resolve()
        if self.hugo_bin is not None:
            bin_path = Path(self.hugo_bin)
            if bin_path.is_absolute():
                return bin_path
            return (root / bin_path).resolve()
        bundled = root / "hugo"
        if bundled.is_file():
            return bundled
        return Path("hugo")

    @property
    def public_dir(self) -> Path:
        return self.hugo_root / "public"

    @property
    def content_dir(self) -> Path:
        return self.hugo_root / "content"

    @property
    def static_dir(self) -> Path:
        return self.hugo_root / "static"

    @property
    def image_dir(self) -> Path:
        return self.static_dir / "image"

    @property
    def video_dir(self) -> Path:
        return self.static_dir / "video"

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
