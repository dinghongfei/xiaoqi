"""Reply to a Feishu message with a preview card (OpenAPI, bot identity)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from feishu.card import build_preview_card, card_as_text
from feishu.openapi import OpenAPIError, get_tenant_access_token, reply_interactive, reply_text
from pipeline.step_result import StepResult

logger = logging.getLogger(__name__)


def _load_last_job(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def reply_preview(
    settings,
    message_id: str,
    *,
    site_preview: str = "",
    wechat_preview: str = "",
    summary: str = "",
) -> StepResult:
    message_id = (message_id or "").strip()
    if not message_id:
        return StepResult(status="error", message="缺少 --message-id。")

    app_id = (settings.feishu_app_id or "").strip()
    app_secret = (settings.feishu_app_secret or "").strip()
    if not app_id or not app_secret:
        return StepResult(status="error", message="请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")

    site = (site_preview or "").strip()
    wechat = (wechat_preview or "").strip()
    if not site and not wechat:
        job = _load_last_job(Path(settings.last_job_path))
        site = str(job.get("site_preview") or "").strip()
        wechat = str(job.get("wechat_preview") or "").strip()

    card = build_preview_card(
        site_preview=site,
        wechat_preview=wechat,
        summary=(summary or "").strip(),
    )
    try:
        token = get_tenant_access_token(app_id, app_secret)
    except OpenAPIError as exc:
        return StepResult(status="error", message=str(exc))

    try:
        reply_interactive(message_id, card, token=token)
        return StepResult(status="ok", message="已回复预览卡片。")
    except OpenAPIError:
        logger.exception("Interactive card reply failed; falling back to text")
    try:
        reply_text(
            message_id,
            card_as_text(site_preview=site, wechat_preview=wechat, summary=(summary or "").strip()),
            token=token,
        )
        return StepResult(status="ok", message="交互卡片失败，已回文本。")
    except OpenAPIError as exc:
        return StepResult(status="error", message=str(exc))
