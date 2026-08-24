"""Delete generated preview/jobs only. Never git reset."""

from __future__ import annotations

import shutil
from pathlib import Path

from pipeline.step_result import StepResult


def clean_generated(settings) -> StepResult:
    removed: list[str] = []
    preview = settings.preview_dir
    wechat = preview / "_wechat"
    if wechat.exists():
        shutil.rmtree(wechat)
        removed.append(str(wechat))

    jobs = Path(settings.jobs_dir)
    if jobs.exists():
        shutil.rmtree(jobs)
        removed.append(str(jobs))

    last_job = Path(settings.last_job_path)
    if last_job.exists():
        last_job.unlink()
        removed.append(str(last_job))

    if not removed:
        return StepResult(status="ok", message="没有需要清理的生成稿。")
    return StepResult(
        status="ok",
        message="已清理生成稿（未执行 git reset）：" + "、".join(removed),
    )
