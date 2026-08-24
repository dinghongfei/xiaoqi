"""Turn Feishu markdown into Hugo-ready article body."""

from __future__ import annotations

import re

from parser.xml_styles import overlay_xml_styles

_LEADING_H1 = re.compile(r"^(?:\s*\n)*#[^#\n][^\n]*(?:\n+|$)")
_FENCE_TITLE = re.compile(
    r"^```([^\n`]*?)\s+title=\"([^\"]*)\"\s*$",
    re.MULTILINE,
)
_CALLOUT = re.compile(
    r"<callout\b([^>]*)>(.*?)</callout>"
    r"(?:\s*(?:!\[([^\]]*)\]\(([^)]+)\)|\{\{<\s*figure\s+([^>]*?)\s*>\}\}))?",
    re.IGNORECASE | re.DOTALL,
)
_ATTR = re.compile(r'(\w+)="([^"]*)"')


def strip_leading_atx_h1(body: str) -> str:
    """Drop the document title. Hugo already renders front matter title."""
    return _LEADING_H1.sub("", body, count=1)


def hugoize_fence_titles(body: str) -> str:
    def repl(match: re.Match[str]) -> str:
        info, title = match.group(1).strip(), match.group(2)
        if "{" in info:
            return match.group(0)
        return f'```{info} {{title="{title}"}}'

    return _FENCE_TITLE.sub(repl, body)


def _attrs(blob: str | None) -> dict[str, str]:
    if not blob:
        return {}
    return {m.group(1): m.group(2) for m in _ATTR.finditer(blob)}


def rewrite_callouts(body: str) -> str:
    def repl(match: re.Match[str]) -> str:
        attr_blob, inner = match.group(1), match.group(2).strip()
        md_alt, md_src, figure_attrs = match.group(3), match.group(4), match.group(5)
        attrs = _attrs(attr_blob)
        emoji = attrs.get("emoji") or "📌"
        cover = md_src or ""
        caption = (md_alt or "").strip()
        if figure_attrs:
            fattrs = _attrs(figure_attrs)
            cover = cover or fattrs.get("src", "")
            caption = caption or fattrs.get("caption", "") or fattrs.get("alt", "")
        is_video = emoji in {"🎬", "🎥"} or "视频" in inner
        parts = [f'{{{{< callout emoji="{emoji}"']
        if is_video:
            parts.append(' video="true"')
        if cover:
            parts.append(f' cover="{cover}"')
        if caption:
            caption = caption.replace('"', '\\"')
            parts.append(f' caption="{caption}"')
        parts.append(" >}}\n")
        parts.append(inner)
        parts.append("\n{{< /callout >}}")
        return "".join(parts)

    return _CALLOUT.sub(repl, body)


def prepare_hugo_body(body: str, xml_text: str = "") -> str:
    if xml_text.strip():
        body = overlay_xml_styles(body, xml_text)
    body = hugoize_fence_titles(body)
    body = rewrite_callouts(body)
    body = strip_leading_atx_h1(body)
    return body.strip() + "\n"
