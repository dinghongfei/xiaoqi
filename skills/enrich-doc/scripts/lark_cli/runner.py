"""Subprocess wrapper for lark-cli commands."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCOPE_HINTS = {
    "board:whiteboard:node:read": "画板读取（board:whiteboard:node:read）",
    "docs:document.media:download": "文档媒体下载（docs:document.media:download）",
}

_UNSUPPORTED = (
    "unsupported",
    "unknown command",
    "unknown subcommand",
    "unknown flag",
    "unknown option",
    "unknown argument",
    "not support",
    "不支持",
)

_PROBE_PROFILE = "xiaoqi"


class LarkCliError(Exception):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}

    @property
    def is_permission_denied(self) -> bool:
        message = str(self)
        if "Access denied" in message or "99991672" in message:
            return True
        violations = self.details.get("permission_violations") or []
        return bool(violations)


@dataclass(frozen=True)
class CliCapabilities:
    has_profile: bool
    has_as: bool
    has_config: bool
    has_json: bool

    @classmethod
    def none(cls) -> CliCapabilities:
        return cls(
            has_profile=False,
            has_as=False,
            has_config=False,
            has_json=False,
        )

    @classmethod
    def full(cls) -> CliCapabilities:
        return cls(
            has_profile=True,
            has_as=True,
            has_config=True,
            has_json=True,
        )

    @property
    def needs_env_credentials(self) -> bool:
        return not self.has_profile or not self.has_as


def _parse_cli_stdout(stdout: str) -> dict[str, Any]:
    stdout = stdout.strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        raise


def _shorten_lark_error_message(message: str) -> str:
    http_match = re.match(r"HTTP \d+:\s*(.+)", message, re.DOTALL)
    if not http_match:
        return message[:500]

    body_text = http_match.group(1).strip()
    try:
        body = json.loads(body_text)
    except json.JSONDecodeError:
        return message[:500]

    msg = body.get("msg") or message
    for scope, label in SCOPE_HINTS.items():
        if scope in msg:
            return f"缺少应用权限 {label}，请在飞书开放平台开通后重新发布应用"
    return msg[:500]


def _run_help(cmd: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    text = (
        proc.stdout.decode("utf-8", errors="replace")
        + "\n"
        + proc.stderr.decode("utf-8", errors="replace")
    )
    return text


def _help_looks_unsupported(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _UNSUPPORTED) or "只支持" in text


def _rejects_flag(text: str, flag: str) -> bool:
    """True when output says this global flag cannot be used."""
    if not text:
        return False
    token = f"--{flag}"
    lowered = text.lower()
    mentioned = token.lower() in lowered
    if flag == "profile":
        mentioned = mentioned or "profile" in lowered
    if flag == "config":
        mentioned = mentioned or "config" in lowered
    if not mentioned:
        return False
    return _help_looks_unsupported(text)


def looks_like_flag_failure(text: str) -> bool:
    return _help_looks_unsupported(text)


def _accepts_global_args(bin_path: str, extra: list[str]) -> bool:
    """Help can list a flag that the wrapper still rejects on a real invocation.

    Probe without ``--help``: some sandboxes forward help to the official CLI
    (so help contains ``--profile``) but reject the flag on execute.
    """
    text = _run_help([bin_path, *extra])
    if text is None:
        return False
    flags = [arg[2:] for arg in extra if arg.startswith("--")]
    if any(_rejects_flag(text, flag) for flag in flags):
        return False
    return "不支持" not in text


def caps_after_flag_failure(
    caps: CliCapabilities,
    cmd: list[str],
    text: str,
) -> CliCapabilities | None:
    """Drop auth flags that were on the failing command; keep --json unless named."""
    if not looks_like_flag_failure(text):
        return None
    used_auth = "--profile" in cmd or "--as" in cmd
    used_json = "--json" in cmd
    if not used_auth and not used_json:
        return None
    has_json = caps.has_json
    if used_json and _rejects_flag(text, "json"):
        has_json = False
    new = CliCapabilities(
        has_profile=caps.has_profile and not used_auth,
        has_as=caps.has_as and not used_auth,
        has_config=caps.has_config and not used_auth,
        has_json=has_json,
    )
    if new == caps:
        return None
    return new


@lru_cache(maxsize=16)
def probe_lark_cli(bin_path: str) -> CliCapabilities:
    """Detect flags this binary can actually execute, not only list in --help."""
    top = _run_help([bin_path, "--help"])
    if top is None:
        return CliCapabilities.none()

    has_profile = "--profile" in top and _accepts_global_args(
        bin_path, ["--profile", _PROBE_PROFILE]
    )
    has_as = bool(re.search(r"--as(?:\s|=|$)", top)) and _accepts_global_args(
        bin_path, ["--as", "bot"]
    )
    has_json = "--json" in top and _accepts_global_args(bin_path, ["--json"])

    config_help = _run_help([bin_path, "config", "--help"])
    has_config = False
    if config_help is not None and not looks_like_flag_failure(config_help):
        low = config_help.lower()
        has_config = "init" in low or "show" in low or bool(
            re.search(r"(?m)^\s*config\b", top)
        )
    elif re.search(r"(?m)^\s*config\b", top) and not looks_like_flag_failure(top):
        has_config = True

    if has_config and not has_profile:
        has_config = False

    return CliCapabilities(
        has_profile=has_profile,
        has_as=has_as,
        has_config=has_config,
        has_json=has_json,
    )


def credential_env(app_id: str, app_secret: str) -> dict[str, str]:
    """Map workspace FEISHU_* credentials to names Trae / official CLI accept."""
    return {
        "LARK_APP_ID": app_id,
        "LARK_APP_SECRET": app_secret,
        "LARKSUITE_CLI_APP_ID": app_id,
        "LARKSUITE_CLI_APP_SECRET": app_secret,
        "LARKSUITE_CLI_BRAND": "feishu",
        "LARKSUITE_CLI_DEFAULT_AS": "bot",
    }


class LarkCliRunner:
    def __init__(
        self,
        bin_path: str,
        identity: str,
        *,
        profile: str,
        app_id: str = "",
        app_secret: str = "",
        capabilities: CliCapabilities | None = None,
    ):
        self.bin_path = bin_path
        self.identity = identity
        self.profile = (profile or "").strip()
        self.app_id = (app_id or "").strip()
        self.app_secret = (app_secret or "").strip()
        self._capabilities = capabilities
        self._downgraded = False
        if not self.profile:
            raise LarkCliError("请设置 LARK_CLI_PROFILE")

    @property
    def capabilities(self) -> CliCapabilities:
        if self._capabilities is None:
            self._capabilities = probe_lark_cli(self.bin_path)
        return self._capabilities

    def _build_cmd(self, args: list[str], identity: str) -> list[str]:
        caps = self.capabilities
        cmd = [self.bin_path]
        if caps.has_profile:
            cmd.extend(["--profile", self.profile])
        cmd.extend(args)
        if caps.has_as:
            cmd.extend(["--as", identity])
        if caps.has_json:
            cmd.append("--json")
        return cmd

    def _subprocess_env(self) -> dict[str, str] | None:
        caps = self.capabilities
        if not caps.needs_env_credentials:
            return None
        if not self.app_id or not self.app_secret:
            raise LarkCliError("请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        env = os.environ.copy()
        env.update(credential_env(self.app_id, self.app_secret))
        return env

    def _try_downgrade(self, cmd: list[str], text: str) -> bool:
        if self._downgraded:
            return False
        new = caps_after_flag_failure(self.capabilities, cmd, text)
        if new is None:
            return False
        logger.warning(
            "lark-cli rejected global flags; retrying without profile/as"
        )
        self._capabilities = new
        self._downgraded = True
        return True

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
        timeout: int = 120,
        as_identity: str | None = None,
    ) -> dict[str, Any]:
        identity = as_identity or self.identity
        while True:
            cmd = self._build_cmd(args, identity)
            logger.debug("lark-cli: %s", " ".join(cmd))
            env = self._subprocess_env()

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(cwd) if cwd else None,
                    input=input_text.encode() if input_text else None,
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                    env=env,
                )
            except FileNotFoundError as exc:
                raise LarkCliError(
                    f"未找到 lark-cli（{self.bin_path}），请先安装：npx @larksuite/cli@latest install"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise LarkCliError(f"lark-cli 命令超时: {' '.join(args)}") from exc

            stdout = proc.stdout.decode("utf-8", errors="replace").strip()
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            combined = f"{stdout}\n{stderr}".strip()

            if not stdout:
                message = stderr or f"lark-cli 退出码 {proc.returncode}"
                if self._try_downgrade(cmd, message):
                    continue
                raise LarkCliError(message)

            try:
                payload = _parse_cli_stdout(stdout)
            except json.JSONDecodeError as exc:
                if self._try_downgrade(cmd, combined):
                    continue
                raise LarkCliError(
                    f"lark-cli 返回非 JSON 输出: {stdout[:200]}",
                    details={"stderr": stderr, "returncode": proc.returncode},
                ) from exc

            if not payload.get("ok"):
                error = payload.get("error") or {}
                raw_message = error.get("message") or stderr or "lark-cli 请求失败"
                if self._try_downgrade(cmd, f"{raw_message}\n{stderr}"):
                    continue
                message = _shorten_lark_error_message(raw_message)
                raise LarkCliError(message, details=error)

            return payload
