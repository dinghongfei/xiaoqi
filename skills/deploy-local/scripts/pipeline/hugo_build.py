"""Run Hugo static site build."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from config import Settings
from pipeline.step_result import StepResult
from pipeline.subprocess_util import run_command


def _is_linux_elf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def resolve_hugo_executable(settings: Settings) -> Path | None:
    """Pick a Hugo binary that exists and can run on the current machine."""
    root = settings.hugo_root.resolve()
    candidates: list[Path] = [settings.resolved_hugo_bin]

    which = shutil.which("hugo")
    if which:
        candidates.append(Path(which))

    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not resolved.is_file():
            continue
        if platform.system() == "Darwin" and _is_linux_elf(resolved):
            continue
        if os.access(resolved, os.X_OK):
            return resolved
    return None


def run_hugo_build(settings: Settings) -> StepResult:
    hugo_bin = resolve_hugo_executable(settings)
    if hugo_bin is None:
        return StepResult(
            status="error",
            message=(
                "Hugo 可执行文件不可用（请配置 HUGO_BIN 或安装 Hugo Extended，"
                "macOS 开发勿使用仓库内 Linux 版 hugo）👻"
            ),
        )

    return run_command(
        [str(hugo_bin), "--minify", "--cleanDestinationDir"],
        cwd=str(settings.hugo_root.resolve()),
        timeout=settings.hugo_build_timeout,
        step_name="Hugo 构建",
    )
