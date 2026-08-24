"""Upload preview/ to object storage. Git push is off by default."""

from __future__ import annotations

import secrets
import shlex
from pathlib import Path

from config import Settings
from pipeline.step_result import StepResult
from pipeline.subprocess_util import run_command


def verify_publish_secret(settings: Settings, provided: str) -> StepResult | None:
    secret = (provided or "").strip()
    expected = (settings.publish_secret_key or "").strip()
    if not secret:
        return StepResult(
            status="error",
            message="未提供 sk，已拒绝云端部署。请在用户明确说「发布」并附上 sk 后再调用。",
        )
    if not expected:
        return StepResult(
            status="error",
            message="未配置 PUBLISH_SECRET_KEY，无法校验 sk。",
        )
    if not secrets.compare_digest(secret, expected):
        return StepResult(
            status="error",
            message="sk 不正确，已拒绝云端部署。",
        )
    return None


def deploy_cloud(settings: Settings, *, secret_key: str) -> StepResult:
    auth = verify_publish_secret(settings, secret_key)
    if auth is not None:
        return auth

    bucket = settings.oss_bucket.strip()
    if not bucket:
        return StepResult(
            status="error",
            message="未开通：未配置对象存储（OSS_BUCKET 为空），仅本地预览。",
        )

    preview_dir = settings.preview_dir
    if not preview_dir.is_dir():
        return StepResult(
            status="error",
            message="preview/ 目录不存在，请先完成 deploy-local。",
        )

    bin_parts = shlex.split(settings.ossutil_bin)
    if not bin_parts:
        return StepResult(
            status="error",
            message="OSSUTIL_BIN 为空，请设置为对象存储命令行工具。",
        )

    cmd = [
        *bin_parts,
        "cp",
        "-r",
        "-f",
        f"{preview_dir.resolve()}/",
        bucket,
    ]
    config_path = settings.ossutil_config
    if config_path is not None and Path(config_path).is_file():
        cmd.extend(["--config-file", str(Path(config_path).resolve())])

    upload = run_command(
        cmd,
        cwd=str(preview_dir.resolve()),
        timeout=settings.publish_timeout,
        step_name="云端上传",
    )
    if not upload.ok:
        return upload

    if settings.git_push_enabled:
        return StepResult(
            status="ok",
            message="已上传 preview/。GIT_PUSH_ENABLED=true，但当前实现不会自动 git push，已跳过。",
        )
    return StepResult(status="ok", message="已上传 preview/ 到对象存储。")
