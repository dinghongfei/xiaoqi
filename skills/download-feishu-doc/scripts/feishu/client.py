"""Feishu document helpers for XML enrichment (no lark-cli subprocess)."""

from __future__ import annotations

import html
import logging
import re
from typing import Any

from parser.message import DocRef
from parser.metadata import DEFAULT_FIELD_HINTS, REQUIRED_METADATA_FIELDS

logger = logging.getLogger(__name__)

_VOID_XML_TAGS = frozenset({"hr", "img", "image", "br", "source"})
_ATTR_HEADING_RE = re.compile(
    r"<h1\b([^>]*)>\s*属性\s*</h1>",
    re.IGNORECASE,
)
_BLOCK_OPEN_RE = re.compile(r"<([a-zA-Z0-9_-]+)(\s[^>]*)?>", re.IGNORECASE)


class FeishuAPIError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def doc_ref_url(doc_ref: DocRef) -> str:
    return f"https://open.feishu.cn/{doc_ref.kind}/{doc_ref.token}"


def _xml_escape(text: str) -> str:
    return html.escape(text, quote=False)


def is_edit_permission_error(exc: BaseException | str) -> bool:
    """True when a Feishu write-back failed because the identity cannot edit the doc."""
    text = str(exc or "")
    lowered = text.lower()
    return (
        "4030004" in text
        or "no permission" in lowered
        or "lacks view or edit" in lowered
        or "没有权限" in text
        or ("编辑" in text and "权限" in text)
        or "edit access" in lowered
    )


def auth_result_from_payload(payload: dict[str, Any]) -> bool | None:
    """Extract drive permission.members auth result. None if the payload is inconclusive."""
    data = payload.get("data")
    candidates: list[dict[str, Any]] = []
    if isinstance(data, dict):
        candidates.append(data)
        nested = data.get("data")
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        for key in ("auth_result", "is_permitted", "has_perm"):
            if key in candidate:
                return bool(candidate[key])
    return None


def format_docs_update_failure(payload: dict[str, Any]) -> str:
    """Turn docs +update failed/partial payload into a user-facing error."""
    data = payload.get("data") or {}
    result = data.get("result")
    warnings = data.get("warnings") or []
    joined = "；".join(str(item) for item in warnings if item)
    text = joined or f"result={result!r}"
    if is_edit_permission_error(text):
        return (
            "没有该文档的编辑权限。"
            "请在飞书文档/知识库把当前登录身份加为「可编辑」协作者后重试写回"
        )
    return f"写回文档失败：{text[:500]}"


def ensure_docs_update_ok(payload: dict[str, Any]) -> None:
    """Raise when lark-cli reports ok=true but data.result indicates failure."""
    data = payload.get("data") or {}
    result = data.get("result")
    if result in (None, "success"):
        return
    if result == "partial_success":
        warnings = data.get("warnings") or []
        logger.warning("docs +update partial_success warnings=%s", warnings)
        return
    message = format_docs_update_failure(payload)
    logger.error("docs +update rejected result=%s: %s", result, message)
    raise FeishuAPIError(message)


def _block_id_from_attrs(attrs: str) -> str:
    match = re.search(r'\bid="([^"]+)"', attrs or "")
    return match.group(1) if match else ""


def list_top_level_block_ids(xml: str) -> list[str]:
    """Collect true top-level block ids (does not include nested table cells)."""
    text = re.sub(r"<title\b[^>]*>.*?</title>", "", xml, flags=re.IGNORECASE | re.DOTALL)
    ids: list[str] = []
    pos = 0
    n = len(text)
    while pos < n:
        while pos < n and text[pos].isspace():
            pos += 1
        if pos >= n:
            break
        if text[pos] != "<":
            pos += 1
            continue
        open_match = _BLOCK_OPEN_RE.match(text, pos)
        if not open_match:
            pos += 1
            continue
        tag = open_match.group(1).lower()
        attrs = open_match.group(2) or ""
        open_end = open_match.end()
        open_raw = text[pos:open_end]
        block_id = _block_id_from_attrs(attrs)
        self_closing = (
            open_raw.rstrip().endswith("/>")
            or tag in _VOID_XML_TAGS
        )
        if self_closing:
            if block_id:
                ids.append(block_id)
            pos = open_end
            continue

        depth = 1
        cursor = open_end
        while cursor < n and depth > 0:
            next_open = re.search(rf"<{tag}\b[^>]*>", text[cursor:], re.IGNORECASE)
            next_close = re.search(rf"</{tag}\s*>", text[cursor:], re.IGNORECASE)
            if next_close is None:
                break
            open_rel = next_open.start() if next_open else None
            close_rel = next_close.start()
            if open_rel is not None and open_rel < close_rel:
                open_tag = next_open.group(0)
                if open_tag.rstrip().endswith("/>"):
                    cursor += next_open.end()
                    continue
                depth += 1
                cursor += next_open.end()
            else:
                depth -= 1
                cursor += next_close.end()
        if block_id:
            ids.append(block_id)
        pos = cursor if cursor > open_end else open_end
    return ids


def find_enrichment_block_ids(xml: str) -> list[str]:
    """Locate top-level blocks starting at h1「属性」through document end."""
    match = _ATTR_HEADING_RE.search(xml)
    if not match:
        return []
    heading_id = _block_id_from_attrs(match.group(1))
    rest_ids = list_top_level_block_ids(xml[match.end() :])
    ids = ([heading_id] if heading_id else []) + rest_ids
    seen: set[str] = set()
    ordered: list[str] = []
    for block_id in ids:
        if block_id and block_id not in seen:
            seen.add(block_id)
            ordered.append(block_id)
    return ordered


def lang_for_metadata_table(lang: str) -> str:
    """Convert normalized Hugo lang back to user-facing zh/en for the table."""
    raw = (lang or "").strip().lower()
    if raw in ("zh-cn", "zh"):
        return "zh"
    return "en"


def value_for_metadata_table(field: str, value) -> str:
    """Format normalized metadata values for the Feishu three-column table."""
    if field == "lang":
        return lang_for_metadata_table(str(value or ""))
    if field == "date":
        text = str(value or "").strip()
        return text[:10] if len(text) >= 10 else text
    if field == "categories":
        if isinstance(value, list):
            return "，".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "").strip()
    return str(value) if value is not None else ""


def build_enrichment_xml(
    metadata: dict,
    *,
    cover_prompt: str | None = None,
    include_image_heading: bool = True,
) -> str:
    """Build write-back XML: 属性(h1) → table → [图片(h1)? → prompt → hr].

    横线只跟在封面提示词后面；已有封面图、不写提示词时，表格下方不写 hr。
    """
    rows: list[str] = []
    for field in REQUIRED_METADATA_FIELDS:
        value = value_for_metadata_table(field, metadata.get(field, ""))
        hint = DEFAULT_FIELD_HINTS.get(field, field)
        rows.append(
            "<tr>"
            f"<td><p>{_xml_escape(field)}</p></td>"
            f"<td><p>{_xml_escape(hint)}</p></td>"
            f"<td><p>{_xml_escape(value)}</p></td>"
            "</tr>"
        )

    parts = [
        "<h1>属性</h1>",
        "<table>",
        '<colgroup><col width="120"/><col width="280"/><col width="360"/></colgroup>',
        "<tbody>",
        *rows,
        "</tbody>",
        "</table>",
    ]
    prompt = (cover_prompt or "").strip()
    if prompt:
        if include_image_heading:
            parts.append("<h1>图片</h1>")
        parts.append(f"<p>{_xml_escape(prompt)}</p>")
        parts.append("<hr/>")
    return "".join(parts)
