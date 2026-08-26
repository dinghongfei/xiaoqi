"""Read WeChat source markdown from processed.md (属性表 + --- + 正文)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TABLE_ROW = re.compile(r"^\|")
_IMAGE_HEADING_RE = re.compile(
    r"(?:^#{1,6}\s*图片\s*$)|(?:<h[1-6][^>]*>\s*图片\s*</h[1-6]>)",
    re.IGNORECASE | re.MULTILINE,
)
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_HTML_SRC_RE = re.compile(r'\bsrc="([^"]+)"', re.IGNORECASE)


@dataclass
class WeChatSource:
    body: str
    title: str = ""
    slug: str = ""
    lang: str = ""
    author: str = ""
    summary: str = ""
    featured_image: str = ""


def normalize_wechat_lang(lang: str) -> str:
    raw = (lang or "").strip().lower()
    if raw in {"zh", "zh-cn", "zh_cn"}:
        return "zh-cn"
    if raw in {"en", "en-us", "en_us"}:
        return "en"
    return raw


def pick_cover_image(metadata_region: str) -> str:
    """First image in the「图片」section; body illustrations are ignored."""
    text = metadata_region or ""
    heading = _IMAGE_HEADING_RE.search(text)
    section = text[heading.end() :] if heading else ""
    if not section.strip():
        return ""
    next_heading = re.search(r"^#{1,6}\s+\S+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    md = _MD_IMAGE_RE.search(section)
    if md:
        return md.group(2).strip()
    html_src = _HTML_SRC_RE.search(section)
    if html_src:
        return html_src.group(1).strip()
    return ""


def _table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    inner = stripped.strip("|")
    return [cell.strip() for cell in inner.split("|")]


def _parse_metadata_region(region: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in region.splitlines():
        cells = _table_cells(line)
        if not cells or len(cells) < 3:
            continue
        key = cells[0].strip().lower()
        value = cells[2].strip()
        if key:
            data[key] = value
    return data


def parse_processed_markdown(text: str) -> WeChatSource | None:
    """Split processed.md into metadata + body. None if this is not that format."""
    lines = (text or "").splitlines()
    end_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None
    region = "\n".join(lines[:end_idx])
    if not any(_TABLE_ROW.match(line.strip()) for line in region.splitlines()):
        return None
    meta = _parse_metadata_region(region)
    if not meta.get("slug"):
        return None
    body = "\n".join(lines[end_idx + 1 :]).strip()
    return WeChatSource(
        body=body,
        title=meta.get("title", "").strip(),
        slug=meta.get("slug", "").strip().lower(),
        lang=normalize_wechat_lang(meta.get("lang", "")),
        author=meta.get("author", "").strip(),
        summary=meta.get("summary", "").strip(),
        featured_image=pick_cover_image(region),
    )


def fallback_hugo_field(text: str, key: str) -> str:
    match = re.search(
        rf"^{re.escape(key)}\s*=\s*(['\"])(.*)\1\s*$",
        text or "",
        re.MULTILINE,
    )
    return match.group(2).strip() if match else ""


def fallback_hugo_title(text: str) -> str:
    return fallback_hugo_field(text, "title")
