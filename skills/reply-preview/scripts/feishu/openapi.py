"""OpenAPI helpers for IM replies (bot app identity)."""

from __future__ import annotations

import json

import httpx

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
REPLY_URL = "https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"


class OpenAPIError(Exception):
    pass


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    try:
        resp = httpx.post(
            TOKEN_URL,
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=30,
        )
        data = resp.json()
    except Exception as exc:
        raise OpenAPIError(f"获取 tenant_access_token 失败：{exc}") from exc
    token = data.get("tenant_access_token")
    if resp.status_code >= 400 or not token:
        raise OpenAPIError(f"获取 tenant_access_token 失败：{data}")
    return token


def _reply(message_id: str, *, msg_type: str, content: str, token: str) -> None:
    try:
        resp = httpx.post(
            REPLY_URL.format(message_id=message_id),
            headers={"Authorization": f"Bearer {token}"},
            json={"msg_type": msg_type, "content": content},
            timeout=30,
        )
        payload = resp.json()
    except Exception as exc:
        raise OpenAPIError(f"回复消息失败：{exc}") from exc
    if resp.status_code >= 400 or payload.get("code"):
        raise OpenAPIError(f"回复消息失败：{payload}")


def reply_interactive(message_id: str, card: dict, *, token: str) -> None:
    _reply(
        message_id,
        msg_type="interactive",
        content=json.dumps(card, ensure_ascii=False),
        token=token,
    )


def reply_text(message_id: str, text: str, *, token: str) -> None:
    _reply(
        message_id,
        msg_type="text",
        content=json.dumps({"text": text}, ensure_ascii=False),
        token=token,
    )
