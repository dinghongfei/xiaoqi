"""Call sandbox-preinstalled lark-cli (no --profile / --as)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_TOKEN_FROM_URL = re.compile(
    r"/(?:docx|wiki|doc)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


def extract_token(url_or_token: str) -> tuple[str, str]:
    """Return (kind, token). kind is docx or wiki."""
    raw = (url_or_token or "").strip()
    if not raw:
        return "docx", ""
    match = _TOKEN_FROM_URL.search(raw)
    if match:
        kind = "wiki" if "/wiki/" in raw.lower() else "docx"
        return kind, match.group(1)
    if raw.startswith("http://") or raw.startswith("https://"):
        return "docx", ""
    return "docx", raw


def _lark_bin() -> str:
    path = shutil.which("lark-cli")
    if not path:
        raise RuntimeError("未找到 lark-cli，请确认豆包工作沙箱已预装")
    return path


def run_lark(args: list[str], *, timeout: int = 120) -> str:
    cmd = [_lark_bin(), *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"lark-cli 失败：{' '.join(args)}\n{err}")
    return proc.stdout


def resolve_docx_token(token: str, *, kind: str = "docx") -> str:
    if kind != "wiki":
        return token
    out = run_lark(["drive", "+inspect", "--url", token, "--type", "wiki"])
    data = _parse_json(out)
    resolved = ""
    if isinstance(data, dict):
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        if isinstance(inner, dict):
            resolved = str(inner.get("token") or inner.get("obj_token") or "")
    if not resolved:
        raise RuntimeError(f"无法从 wiki token 解析底层文档：{token}")
    return resolved


def fetch_markdown(docx_token: str) -> str:
    return run_lark(
        [
            "docs",
            "+fetch",
            "--api-version",
            "v2",
            "--doc",
            docx_token,
            "--doc-format",
            "markdown",
        ]
    )


def fetch_xml(docx_token: str) -> str:
    return run_lark(
        [
            "docs",
            "+fetch",
            "--api-version",
            "v2",
            "--doc",
            docx_token,
            "--doc-format",
            "xml",
            "--detail",
            "full",
        ]
    )


def media_download_to(
    file_token: str,
    output: Path,
    *,
    whiteboard: bool = False,
    timeout: int = 180,
) -> Path | None:
    """Download a Feishu media token into output path via lark-cli.

    ``output`` may be a file path (token as filename) or directory.
    Returns the resulting file path.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "docs",
        "+media-download",
        "--token",
        file_token,
        "--output",
        str(output),
    ]
    if whiteboard:
        args.extend(["--type", "whiteboard"])
    run_lark(args, timeout=timeout)
    if output.is_file():
        return output
    if output.is_dir():
        matches = sorted(output.glob(f"{file_token}*"))
        return matches[0] if matches else None
    # lark-cli sometimes writes output / output.ext
    matches = sorted(output.parent.glob(f"{output.name}*"))
    files = [p for p in matches if p.is_file()]
    return files[0] if files else None


def _parse_json(text: str) -> Any:
    raw = (text or "").strip().lstrip("\ufeff").strip()
    if not raw.startswith("{"):
        return None
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(raw)
        return obj
    except json.JSONDecodeError:
        return None
