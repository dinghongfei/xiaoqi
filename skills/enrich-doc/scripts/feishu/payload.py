"""Parse lark-cli docs +fetch JSON or pass through already-extracted content."""

from __future__ import annotations

import json
from typing import Any


def document_from_fetch(text: str) -> tuple[str, str]:
    """Return (content, document_id).

    Accepts either the document body (markdown/xml) or lark-cli JSON stdout
    with ``data.document.content``.
    """
    raw = (text or "").strip()
    if not raw:
        return "", ""
    if raw.startswith("{"):
        try:
            payload: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            return text, ""
        document = (payload.get("data") or {}).get("document") or {}
        if not isinstance(document, dict):
            return text, ""
        content = document.get("content") or ""
        document_id = document.get("document_id") or ""
        if content:
            return str(content), str(document_id)
    return text, ""
