"""Normalize Feishu markdown export (title tag → H1)."""

from __future__ import annotations

import re

LEADING_TITLE_TAG_PATTERN = re.compile(
    r"\A\s*<title>\s*(.*?)\s*</title>\s*",
    re.IGNORECASE | re.DOTALL,
)
_ATX_H1_TEXT = re.compile(r"^#[^#\n](.*)$")
_ATX_H1_LINE = re.compile(r"^#[^#\n](.*)$", re.MULTILINE)


def unescape_feishu_text(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text.strip())


def feishu_title_tag_to_atx_h1(text: str) -> str:
    if not text:
        return ""
    match = LEADING_TITLE_TAG_PATTERN.match(text)
    if not match:
        return text
    title = unescape_feishu_text(match.group(1)).strip()
    rest = text[match.end() :].lstrip("\n")
    if not title:
        return rest
    lines = rest.splitlines(keepends=True)
    if lines:
        first = lines[0].rstrip("\r\n")
        heading = _ATX_H1_TEXT.match(first)
        if heading and heading.group(1).strip() == title:
            rest = "".join(lines[1:]).lstrip("\n")
    if rest:
        return f"# {title}\n\n{rest}"
    return f"# {title}"


def prepare_feishu_markdown(raw: str) -> str:
    return feishu_title_tag_to_atx_h1(raw).strip()


def extract_title(markdown_text: str, *, fallback: str = "") -> str:
    """Title from leading <title> or first ATX H1."""
    match = LEADING_TITLE_TAG_PATTERN.match(markdown_text or "")
    if match:
        title = unescape_feishu_text(match.group(1)).strip()
        if title:
            return title
    prepared = prepare_feishu_markdown(markdown_text or "")
    h1 = _ATX_H1_LINE.search(prepared)
    if h1:
        return h1.group(1).strip()
    return (fallback or "").strip()


_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_HTML_TAG = re.compile(r"<[^>]+>")
_SHORTCODE = re.compile(r"\{\{<[^>]*>\}\}")
_HEADING = re.compile(r"^#{1,6}\s+")


def extract_summary(markdown_text: str, *, max_chars: int = 100) -> str:
    """Fallback: take leading body text, capped at max_chars (默认 100 字)."""
    text = prepare_feishu_markdown(markdown_text or "")
    # drop leading title H1
    lines = text.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start < len(lines) and _ATX_H1_TEXT.match(lines[start]):
        start += 1
    chunks: list[str] = []
    for line in lines[start:]:
        raw = line.strip()
        if not raw:
            if chunks:
                break
            continue
        if _HEADING.match(raw):
            if chunks:
                break
            continue
        if raw.startswith((">", "-", "*", "|", "```")):
            continue
        if _MD_IMAGE.search(raw) or raw.startswith("{{<"):
            continue
        cleaned = _SHORTCODE.sub("", raw)
        cleaned = _MD_IMAGE.sub("", cleaned)
        cleaned = _HTML_TAG.sub("", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"[*_`~]+", "", cleaned).strip()
        if cleaned:
            chunks.append(cleaned)
            joined = "".join(chunks)
            if len(joined) >= max_chars:
                break
    return clamp_summary("".join(chunks), max_chars=max_chars)


def clamp_summary(text: str, *, max_chars: int = 100) -> str:
    """Normalize and enforce ≤ max_chars for 公众号摘要."""
    summary = re.sub(r"\s+", " ", (text or "").strip())
    if not summary:
        return ""
    if len(summary) > max_chars:
        return summary[: max_chars - 1].rstrip() + "…"
    return summary
