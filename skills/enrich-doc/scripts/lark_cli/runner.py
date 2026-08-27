"""Subprocess wrapper for lark-cli commands."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCOPE_HINTS = {
    "board:whiteboard:node:read": "画板读取（board:whiteboard:node:read）",
    "docs:document.media:download": "文档媒体下载（docs:document.media:download）",
}


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


class LarkCliRunner:
    def __init__(
        self,
        bin_path: str,
        identity: str,
        *,
        profile: str,
    ):
        self.bin_path = bin_path
        self.identity = identity
        self.profile = (profile or "").strip()
        if not self.profile:
            raise LarkCliError("请设置 LARK_CLI_PROFILE")

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
        cmd = [self.bin_path, "--profile", self.profile, *args, "--as", identity, "--json"]
        logger.debug("lark-cli: %s", " ".join(cmd))

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                input=input_text.encode() if input_text else None,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise LarkCliError(
                f"未找到 lark-cli（{self.bin_path}），请先安装：npx @larksuite/cli@latest install"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise LarkCliError(f"lark-cli 命令超时: {' '.join(args)}") from exc

        stdout = proc.stdout.decode("utf-8", errors="replace").strip()
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()

        if not stdout:
            message = stderr or f"lark-cli 退出码 {proc.returncode}"
            raise LarkCliError(message)

        try:
            payload = _parse_cli_stdout(stdout)
        except json.JSONDecodeError as exc:
            raise LarkCliError(
                f"lark-cli 返回非 JSON 输出: {stdout[:200]}",
                details={"stderr": stderr, "returncode": proc.returncode},
            ) from exc

        if not payload.get("ok"):
            error = payload.get("error") or {}
            raw_message = error.get("message") or stderr or "lark-cli 请求失败"
            message = _shorten_lark_error_message(raw_message)
            raise LarkCliError(message, details=error)

        return payload
