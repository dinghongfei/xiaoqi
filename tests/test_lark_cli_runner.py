"""Tests for lark-cli runner wrapper."""

import json
from unittest.mock import MagicMock, patch

import pytest

from lark_cli.config_sync import ensure_lark_cli_config
from lark_cli.runner import (
    LarkCliError,
    LarkCliRunner,
    _parse_cli_stdout,
    _shorten_lark_error_message,
)


def test_run_always_passes_profile():
    runner = LarkCliRunner(bin_path="lark-cli", identity="bot", profile="xiaoqi")
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


def test_run_uses_configured_profile_name():
    runner = LarkCliRunner(
        bin_path="lark-cli",
        identity="bot",
        profile="bot-prod",
    )
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
    runner = LarkCliRunner(bin_path="lark-cli", identity="bot", profile="xiaoqi")
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
    runner = LarkCliRunner(bin_path="missing-cli", identity="bot", profile="xiaoqi")

    with patch(
        "lark_cli.runner.subprocess.run",
        side_effect=FileNotFoundError(),
    ):
        with pytest.raises(LarkCliError, match="未找到 lark-cli"):
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
        )

    show_args = mock_run.call_args_list[0].args[0]
    init_args = mock_run.call_args_list[1].args[0]
    assert show_args[:3] == ["lark-cli", "--profile", "xiaoqi"]
    assert show_args[3:] == ["config", "show"]
    assert init_args[:3] == ["lark-cli", "--profile", "xiaoqi"]
    assert init_args[3:5] == ["config", "init"]
    assert "--name" in init_args
    assert init_args[init_args.index("--name") + 1] == "xiaoqi"
