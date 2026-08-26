"""Parse lark-cli docs +fetch JSON or pass through already-extracted content."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n(.*)\n```\s*$",
    re.IGNORECASE | re.DOTALL,
)


def document_from_fetch(text: str) -> tuple[str, str]:
    """Return (content, document_id).

    Accepts either the document body (markdown/xml) or lark-cli JSON stdout
    with ``data.document.content`` (``--api-version v2`` / ``--format json``).
    """
    original = text or ""
    raw = original.strip().lstrip("\ufeff").strip()
    if not raw:
        return "", ""
    raw = _unwrap_fence(raw)
    payload = _parse_json_payload(raw)
    if payload is None:
        return original, ""
    content, document_id = _extract_document(payload)
    if not content:
        return original, document_id
    nested = _parse_json_payload(content.strip()) if content.lstrip().startswith("{") else None
    if nested is not None:
        inner, inner_id = _extract_document(nested)
        if inner:
            return inner, inner_id or document_id
    return content, document_id


def _unwrap_fence(text: str) -> str:
    match = _FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text


def _parse_json_payload(text: str) -> dict[str, Any] | None:
    """Parse a JSON object, including NDJSON / trailing logs around the envelope."""
    decoder = json.JSONDecoder()
    rest = text.strip().lstrip("\ufeff").strip()
    if not rest.startswith("{"):
        return None
    last: dict[str, Any] | None = None
    while rest.startswith("{"):
        try:
            obj, end = decoder.raw_decode(rest)
        except json.JSONDecodeError:
            return last
        if isinstance(obj, dict):
            content, _doc_id = _extract_document(obj)
            if content:
                return obj
            last = obj
        rest = rest[end:].strip()
    return last


def _extract_document(payload: dict[str, Any]) -> tuple[str, str]:
    data = payload.get("data")
    document: Any = {}
    if isinstance(data, dict):
        inner = data.get("document")
        document = inner if isinstance(inner, dict) else data
    elif isinstance(payload.get("document"), dict):
        document = payload["document"]
    if not isinstance(document, dict):
        return "", ""
    content = document.get("content")
    if not isinstance(content, str) or not content:
        return "", ""
    document_id = document.get("document_id") or payload.get("document_id") or ""
    if isinstance(data, dict) and not document_id:
        document_id = data.get("document_id") or ""
    return content, str(document_id or "")
