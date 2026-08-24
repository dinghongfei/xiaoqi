"""Feishu interactive card: two preview buttons."""

from __future__ import annotations


def build_preview_card(
    *,
    site_preview: str = "",
    wechat_preview: str = "",
    summary: str = "",
) -> dict:
    lines: list[str] = []
    if summary:
        lines.append(summary)
    if site_preview:
        lines.append(f"官网：{site_preview}")
    if wechat_preview:
        lines.append(f"公众号：{wechat_preview}")
    if not lines:
        lines.append("任务已结束，但没有解析到预览链接。")

    actions: list[dict] = []
    if site_preview:
        actions.append(
            {
                "tag": "button",
                "type": "primary",
                "text": {"tag": "plain_text", "content": "官网预览"},
                "url": site_preview,
            }
        )
    if wechat_preview:
        actions.append(
            {
                "tag": "button",
                "type": "default",
                "text": {"tag": "plain_text", "content": "公众号预览"},
                "url": wechat_preview,
            }
        )

    elements: list[dict] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(lines)},
        }
    ]
    if actions:
        elements.append({"tag": "action", "actions": actions})

    header_text = "预览已就绪" if (site_preview or wechat_preview) else "处理结果"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": header_text},
            "template": "blue",
        },
        "elements": elements,
    }


def card_as_text(*, site_preview: str = "", wechat_preview: str = "", summary: str = "") -> str:
    """Plain-text fallback when interactive reply is unavailable."""
    parts: list[str] = []
    if summary:
        parts.append(summary)
    if site_preview:
        parts.append(f"官网预览：{site_preview}")
    if wechat_preview:
        parts.append(f"公众号预览：{wechat_preview}")
    if not parts:
        parts.append("没有解析到预览链接。")
    return "\n".join(parts)
