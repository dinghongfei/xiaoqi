"""Helpers for running external commands in pipeline steps."""

from __future__ import annotations

import logging
import subprocess

from pipeline.step_result import StepResult

logger = logging.getLogger(__name__)


def _tail_output(completed: subprocess.CompletedProcess[str], *, limit: int = 200) -> str:
    detail = (completed.stderr or completed.stdout or "").strip()
    if not detail:
        return ""
    return detail.splitlines()[-1][:limit]


def run_command(
    cmd: list[str],
    *,
    cwd: str,
    timeout: int,
    step_name: str,
) -> StepResult:
    logger.info("Running %s: %s (cwd=%s)", step_name, cmd, cwd)
    try:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return StepResult(
            status="error",
            message=f"{step_name} 执行超时（>{timeout}s）⏳",
        )
    except OSError as exc:
        return StepResult(status="error", message=f"{step_name} 启动失败：{exc} 💥")

    if completed.returncode != 0:
        detail = _tail_output(completed)
        if detail:
            return StepResult(
                status="error",
                message=f"{step_name} 失败（退出码 {completed.returncode}）：{detail} 😵",
            )
        return StepResult(
            status="error",
            message=f"{step_name} 失败（退出码 {completed.returncode}）😵",
        )

    logger.info("%s succeeded", step_name)
    return StepResult(status="ok", message="")
