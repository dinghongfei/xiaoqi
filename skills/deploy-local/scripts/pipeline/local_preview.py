"""Local Hugo build + copy public/ to preview/."""

from __future__ import annotations

from config import Settings
from last_job import load_last_job, update_last_job
from pipeline.deploy_local import deploy_public
from pipeline.hugo_build import run_hugo_build
from pipeline.step_result import StepResult
from urls import site_page_url


def deploy_local_preview(settings: Settings) -> StepResult:
    hugo_toml = settings.hugo_root / "hugo.toml"
    if not hugo_toml.is_file():
        return StepResult(
            status="error",
            message=(
                f"缺少 {hugo_toml}。本步不会执行 hugo new site；"
                "请使用仓库自带的 site/ 演示站。"
            ),
        )

    build = run_hugo_build(settings)
    if not build.ok:
        return build

    deploy = deploy_public(settings)
    if not deploy.ok:
        return deploy

    job = load_last_job(settings) or {}
    preview = site_page_url(
        settings.site_base_url,
        str(job.get("section") or ""),
        str(job.get("slug") or ""),
        str(job.get("lang") or ""),
    )
    if preview:
        update_last_job(settings, site_preview=preview)
        return StepResult(
            status="ok",
            message=f"本地预览已更新：{deploy.message}\n官网预览={preview}",
        )
    return StepResult(
        status="ok",
        message=f"本地预览已更新：{deploy.message}",
    )
