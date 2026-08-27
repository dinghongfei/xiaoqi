"""Read WeChat source markdown from processed.md (属性表 + --- + 正文)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TABLE_ROW = re.compile(r"^\|")
_IMAGE_HEADING = re.compile(r"^#\s*图片\s*$")
_COVER_MD = re.compile(r"!\[[^\]]*\]\((/image/[^)\s]+|https?://[^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")
_COVER_SRC = re.compile(r"""(?:src|featured_image)\s*=\s*['\"](/image/[^'\"]+|https?://[^'\"]+)['\"]""")


@dataclass
class WeChatSource:
    body: str
    title: str = ""
    slug: str = ""
    lang: str = ""
    author: str = ""
    summary: str = ""
    cover_image: str = ""


def normalize_wechat_lang(lang: str) -> str:
    raw = (lang or "").strip().lower()
    if raw in {"zh", "zh-cn", "zh_cn"}:
        return "zh-cn"
    if raw in {"en", "en-us", "en_us"}:
        return "en"
    return raw


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


def _first_cover_src(text: str) -> str:
    """Pick a site-path or http(s) image; skip cover-prompt text."""
    match = _COVER_MD.search(text or "") or _COVER_SRC.search(text or "")
    return match.group(1).strip() if match else ""


def extract_cover_image(metadata_region: str) -> str:
    """Cover lives under「# 图片」; fall back to any image in the metadata region."""
    lines = (metadata_region or "").splitlines()
    start = None
    for i, line in enumerate(lines):
        if _IMAGE_HEADING.match(line.strip()):
            start = i + 1
            break
    if start is not None:
        found = _first_cover_src("\n".join(lines[start:]))
        if found:
            return found
    return _first_cover_src(metadata_region)


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
        cover_image=extract_cover_image(region),
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
