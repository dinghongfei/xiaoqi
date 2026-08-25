"""Sync bot app credentials into lark-cli configuration."""

from __future__ import annotations

import json
import logging
import subprocess

from lark_cli.runner import CliCapabilities, looks_like_flag_failure, probe_lark_cli

logger = logging.getLogger(__name__)


def ensure_lark_cli_config(
    app_id: str,
    app_secret: str,
    *,
    cli_bin: str,
    profile: str,
    capabilities: CliCapabilities | None = None,
) -> None:
    """Ensure lark-cli uses the same app credentials as the bot.

    Always target ``LARK_CLI_PROFILE``: ``config show`` / ``config init``
    pass ``--profile``, and init also uses ``--name`` so it appends/updates
    that named profile without switching the globally active one.

    Skip entirely when this binary has no ``config`` subcommand (sandbox CLIs),
    or when ``CLI management:`` lists ``profile`` but ``--profile`` cannot
    actually be executed.
    """
    if not app_id or not app_secret:
        return

    caps = capabilities if capabilities is not None else probe_lark_cli(cli_bin)
    if not caps.has_config or not caps.has_profile:
        logger.debug("skip lark-cli config sync: no executable config/profile")
        return

    profile_name = (profile or "").strip()
    if not profile_name:
        raise ValueError("请设置 LARK_CLI_PROFILE")
    current_app_id = _read_configured_app_id(cli_bin, profile=profile_name)
    if current_app_id == app_id:
        logger.debug(
            "lark-cli config already matches bot app_id (profile=%s)",
            profile_name,
        )
        return

    logger.info(
        "Syncing lark-cli config to bot app_id %s (was %s) profile=%s",
        app_id,
        current_app_id or "<unset>",
        profile_name,
    )
    cmd = [
        cli_bin,
        "--profile",
        profile_name,
        "config",
        "init",
        "--app-id",
        app_id,
        "--app-secret-stdin",
        "--brand",
        "feishu",
        "--name",
        profile_name,
    ]

    try:
        subprocess.run(
            cmd,
            input=app_secret.encode(),
            check=True,
            capture_output=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        combined = (
            (exc.stdout or b"").decode("utf-8", errors="replace")
            + "\n"
            + (exc.stderr or b"").decode("utf-8", errors="replace")
        )
        if looks_like_flag_failure(combined):
            logger.warning("skip lark-cli config sync: %s", combined.strip()[:200])
            return
        raise


def _parse_config_show_stdout(stdout: str) -> dict:
    """Parse ``config show`` output (JSON object, may have trailing text)."""
    text = stdout.strip()
    if not text:
        raise ValueError("empty config show output")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text)
    if not isinstance(obj, dict):
        raise ValueError("config show did not return a JSON object")
    return obj


def _read_configured_app_id(
    cli_bin: str,
    *,
    profile: str,
) -> str | None:
    cmd = [cli_bin, "--profile", profile, "config", "show"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return None
        data = _parse_config_show_stdout(proc.stdout.decode())
        if data.get("ok") is False:
            return None
        app_id = data.get("appId")
        return app_id if isinstance(app_id, str) and app_id else None
    except Exception:
        return None
