"""Build a FeishuClient from settings."""

from __future__ import annotations

from config import Settings
from feishu.client import FeishuClient
from lark_cli.config_sync import ensure_lark_cli_config
from lark_cli.runner import probe_lark_cli


class SettingsError(ValueError):
    pass


def require_feishu_settings(settings: Settings) -> None:
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise SettingsError("请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
    if not settings.lark_cli_bin or not settings.lark_cli_identity:
        raise SettingsError("请设置 LARK_CLI_BIN 和 LARK_CLI_IDENTITY")
    if not (settings.lark_cli_profile or "").strip():
        raise SettingsError("请设置 LARK_CLI_PROFILE")


def create_feishu_client(settings: Settings, *, sync_config: bool | None = None) -> FeishuClient:
    require_feishu_settings(settings)
    profile = settings.lark_cli_profile.strip()
    caps = probe_lark_cli(settings.lark_cli_bin)
    do_sync = settings.lark_cli_sync_config if sync_config is None else sync_config
    if do_sync and caps.has_config and caps.has_profile:
        ensure_lark_cli_config(
            settings.feishu_app_id,
            settings.feishu_app_secret,
            cli_bin=settings.lark_cli_bin,
            profile=profile,
            capabilities=caps,
        )
    return FeishuClient(
        settings.feishu_app_id,
        settings.feishu_app_secret,
        cli_bin=settings.lark_cli_bin,
        cli_identity=settings.lark_cli_identity,
        cli_profile=profile,
    )
