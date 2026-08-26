"""Send the immediate「收到」ack via OpenAPI. Result cards are the reply-preview Skill."""

from __future__ import annotations

from bot.config import Settings
from bot.feishu.openapi import get_tenant_access_token, reply_text

RECEIVED_ACK = "收到啦，正在交给豆包工作 Agent 处理，请稍候～"


def send_received_ack(settings: Settings, message_id: str) -> None:
    token = get_tenant_access_token(settings.feishu_app_id, settings.feishu_app_secret)
    reply_text(message_id, RECEIVED_ACK, token=token)
