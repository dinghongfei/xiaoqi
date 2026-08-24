"""Deploy Hugo public/ output to the local preview directory."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from config import Settings
from pipeline.step_result import StepResult

logger = logging.getLogger(__name__)


def deploy_public(settings: Settings) -> StepResult:
    deploy_dir = settings.hugo_deploy_dir
    if deploy_dir is None:
        return StepResult(
            status="error",
            message="未配置 HUGO_DEPLOY_DIR，无法部署 public/ 目录。",
        )

    deploy_path = Path(deploy_dir)
    public_dir = settings.public_dir
    if not public_dir.is_dir():
        return StepResult(
            status="error",
            message="public/ 目录不存在，请先完成 Hugo 构建。",
        )

    wechat_backup: Path | None = None
    wechat_src = deploy_path / "_wechat"
    tmp_parent: Path | None = None
    try:
        if wechat_src.is_dir():
            tmp_parent = Path(tempfile.mkdtemp(prefix="bot-wechat-"))
            wechat_backup = tmp_parent / "_wechat"
            shutil.copytree(wechat_src, wechat_backup)

        if deploy_path.exists():
            shutil.rmtree(deploy_path)
        shutil.copytree(public_dir, deploy_path)

        if wechat_backup is not None:
            shutil.copytree(wechat_backup, deploy_path / "_wechat")
    except OSError as exc:
        logger.exception("Failed to deploy public/ to %s", deploy_path)
        return StepResult(
            status="error",
            message=f"部署 public/ 到 {deploy_path} 失败：{exc}",
        )
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    logger.info("Deployed public/ to %s", deploy_path)
    return StepResult(status="ok", message=str(deploy_path))
