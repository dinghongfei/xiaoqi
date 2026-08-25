"""Tests for lark-cli runner wrapper."""

import json
from unittest.mock import MagicMock, patch

import pytest

from config import Settings
from feishu.factory import create_feishu_client
from lark_cli.config_sync import ensure_lark_cli_config
from lark_cli.runner import (
    CliCapabilities,
    LarkCliError,
    LarkCliRunner,
    _parse_cli_stdout,
    _shorten_lark_error_message,
    probe_lark_cli,
)

FULL = CliCapabilities.full()
RESTRICTED = CliCapabilities.none()


def _runner(**kwargs) -> LarkCliRunner:
    kwargs.setdefault("bin_path", "lark-cli")
    kwargs.setdefault("identity", "bot")
    kwargs.setdefault("profile", "xiaoqi")
    kwargs.setdefault("capabilities", FULL)
    return LarkCliRunner(**kwargs)


def test_run_always_passes_profile():
    runner = _runner()
    payload = {"ok": True, "data": {"value": 1}}

    with patch("lark_cli.runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload).encode(),
            stderr=b"",
        )
        result = runner.run(["docs", "+fetch"])

    assert result == payload
    args = mock_run.call_args.args[0]
    assert args[:3] == ["lark-cli", "--profile", "xiaoqi"]
    assert "--as" in args
    assert args[args.index("--as") + 1] == "bot"
    assert "--json" in args
    assert mock_run.call_args.kwargs.get("env") is None


def test_run_uses_configured_profile_name():
    runner = _runner(profile="bot-prod")
    payload = {"ok": True, "data": {}}

    with patch("lark_cli.runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload).encode(),
            stderr=b"",
        )
        runner.run(["im", "+messages-reply"])

    args = mock_run.call_args.args[0]
    assert args[:3] == ["lark-cli", "--profile", "bot-prod"]
    assert "--as" in args
    assert "--json" in args


def test_missing_profile_raises():
    with pytest.raises(LarkCliError, match="LARK_CLI_PROFILE"):
        LarkCliRunner(bin_path="lark-cli", identity="bot", profile="  ")


def test_run_api_error():
    runner = _runner()
    payload = {"ok": False, "error": {"message": "permission denied"}}

    with patch("lark_cli.runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=json.dumps(payload).encode(),
            stderr=b"",
        )
        with pytest.raises(LarkCliError, match="permission denied"):
            runner.run(["docs", "+fetch"])


def test_run_missing_binary():
    runner = _runner(bin_path="missing-cli")

    with patch(
        "lark_cli.runner.subprocess.run",
        side_effect=FileNotFoundError(),
    ):
        with pytest.raises(LarkCliError, match="未找到 lark-cli"):
            runner.run(["docs", "+fetch"])


def test_restricted_omits_profile_as_and_injects_env():
    runner = _runner(
        capabilities=RESTRICTED,
        app_id="cli_app",
        app_secret="app_secret",
    )
    payload = {"ok": True, "data": {}}

    with patch("lark_cli.runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload).encode(),
            stderr=b"",
        )
        runner.run(["docs", "+fetch"])

    args = mock_run.call_args.args[0]
    assert args == ["lark-cli", "docs", "+fetch"]
    env = mock_run.call_args.kwargs["env"]
    assert env["LARK_APP_ID"] == "cli_app"
    assert env["LARK_APP_SECRET"] == "app_secret"
    assert env["LARKSUITE_CLI_APP_ID"] == "cli_app"
    assert env["LARKSUITE_CLI_APP_SECRET"] == "app_secret"
    assert env["LARKSUITE_CLI_BRAND"] == "feishu"
    assert env["LARKSUITE_CLI_DEFAULT_AS"] == "bot"


def test_restricted_keeps_json_when_supported():
    runner = _runner(
        capabilities=CliCapabilities(
            has_profile=False,
            has_as=False,
            has_config=False,
            has_json=True,
        ),
        app_id="cli_app",
        app_secret="app_secret",
    )
    with patch("lark_cli.runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b'{"ok": true, "data": {}}',
            stderr=b"",
        )
        runner.run(["docs", "+fetch"])
    assert mock_run.call_args.args[0] == ["lark-cli", "docs", "+fetch", "--json"]
    runner = _runner(capabilities=RESTRICTED)
    with pytest.raises(LarkCliError, match="FEISHU_APP_ID"):
        runner.run(["docs", "+fetch"])


def test_parse_cli_stdout_with_progress_prefix():
    payload = _parse_cli_stdout('Downloading: media abc\n{"ok": true, "data": {}}')
    assert payload["ok"] is True


def test_shorten_permission_error_message():
    raw = (
        'HTTP 400: {"code":99991672,"msg":"Access denied. One of the following scopes '
        'is required: [board:whiteboard:node:read].应用尚未开通所需的应用身份权限"}'
    )
    short = _shorten_lark_error_message(raw)
    assert "board:whiteboard:node:read" in short


def test_lark_cli_error_permission_flag():
    err = LarkCliError(
        "Access denied",
        details={"permission_violations": [{"subject": "board:whiteboard:node:read"}]},
    )
    assert err.is_permission_denied


def test_probe_detects_full_help():
    probe_lark_cli.cache_clear()
    top = "Usage:\n  lark-cli --profile NAME --as bot --json\n  config  Manage config"
    cfg = "Usage: lark-cli config\n  init\n  show"
    with patch("lark_cli.runner._run_help", side_effect=[top, cfg]):
        caps = probe_lark_cli("full-cli")
    assert caps.has_profile
    assert caps.has_as
    assert caps.has_json
    assert caps.has_config
    probe_lark_cli.cache_clear()


def test_probe_restricted_help():
    probe_lark_cli.cache_clear()
    top = "Usage: lark-cli docs +fetch\nConfigure LARK_APP_ID"
    cfg = "config 不支持"
    with patch("lark_cli.runner._run_help", side_effect=[top, cfg]):
        caps = probe_lark_cli("sandbox-cli")
    assert not caps.has_profile
    assert not caps.has_as
    assert not caps.has_json
    assert not caps.has_config
    probe_lark_cli.cache_clear()


def test_config_sync_always_passes_profile():
    show = MagicMock(
        returncode=0,
        stdout=b'{"ok": true, "appId": "old"}\n',
        stderr=b"",
    )
    init = MagicMock(returncode=0, stdout=b'{"ok": true}\n', stderr=b"")

    with patch("lark_cli.config_sync.subprocess.run", side_effect=[show, init]) as mock_run:
        ensure_lark_cli_config(
            "cli_new",
            "secret",
            cli_bin="lark-cli",
            profile="xiaoqi",
            capabilities=FULL,
        )

    show_args = mock_run.call_args_list[0].args[0]
    init_args = mock_run.call_args_list[1].args[0]
    assert show_args[:3] == ["lark-cli", "--profile", "xiaoqi"]
    assert show_args[3:] == ["config", "show"]
    assert init_args[:3] == ["lark-cli", "--profile", "xiaoqi"]
    assert init_args[3:5] == ["config", "init"]
    assert "--name" in init_args
    assert init_args[init_args.index("--name") + 1] == "xiaoqi"


def test_config_sync_skips_without_config_capability():
    with patch("lark_cli.config_sync.subprocess.run") as mock_run:
        ensure_lark_cli_config(
            "cli_new",
            "secret",
            cli_bin="lark-cli",
            profile="xiaoqi",
            capabilities=RESTRICTED,
        )
    mock_run.assert_not_called()


def test_factory_skips_config_when_probe_has_no_config():
    settings = Settings(
        feishu_app_id="cli_x",
        feishu_app_secret="sec",
        lark_cli_bin="lark-cli",
        lark_cli_identity="bot",
        lark_cli_profile="xiaoqi",
        lark_cli_sync_config=True,
    )
    with patch("feishu.factory.probe_lark_cli", return_value=RESTRICTED):
        with patch("feishu.factory.ensure_lark_cli_config") as sync:
            create_feishu_client(settings)
            sync.assert_not_called()
