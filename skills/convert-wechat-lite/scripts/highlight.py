"""Highlight fenced code for WeChat HTML (inline styles so paste keeps colors)."""

from __future__ import annotations

import html
import re

_TITLE = re.compile(r'title=(["\'])(.*?)\1')


def parse_fence_info(info: str) -> tuple[str, str]:
    """Return (language, title) from a fence info string."""
    raw = (info or "").strip()
    title = ""
    match = _TITLE.search(raw)
    if match:
        title = match.group(2).strip()
        raw = (raw[: match.start()] + raw[match.end() :]).strip()
    lang = raw.split()[0] if raw else ""
    return lang, title


_TAG_OR_TEXT = re.compile(r"(<[^>]+>)")


def preserve_wechat_code_spaces(fragment: str) -> str:
    """WeChat's editor drops plain spaces sitting between inline spans."""
    parts: list[str] = []
    for index, chunk in enumerate(_TAG_OR_TEXT.split(fragment)):
        if index % 2 == 1:
            parts.append(chunk)
            continue
        chunk = chunk.replace("\t", "    ").replace(" ", "&nbsp;")
        parts.append(chunk)
    return "".join(parts)


def highlight_code(code: str, lang: str) -> str:
    """Return HTML for code contents. Falls back to escaped text."""
    text = code.replace("\r\n", "\n")
    if not lang:
        return preserve_wechat_code_spaces(html.escape(text))
    try:
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import get_lexer_by_name
        from pygments.util import ClassNotFound
    except ImportError:
        return preserve_wechat_code_spaces(html.escape(text))
    try:
        lexer = get_lexer_by_name(lang, stripall=False)
    except ClassNotFound:
        return preserve_wechat_code_spaces(html.escape(text))
    formatter = HtmlFormatter(nowrap=True, noclasses=True)
    return preserve_wechat_code_spaces(highlight(text, lexer, formatter).rstrip("\n"))
