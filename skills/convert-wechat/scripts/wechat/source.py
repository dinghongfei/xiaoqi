"""Read WeChat source markdown from processed.md (属性表 + --- + 正文)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TABLE_ROW = re.compile(r"^\|")


@dataclass
class WeChatSource:
    body: str
    title: str = ""
    slug: str = ""
    lang: str = ""


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
    )


def fallback_hugo_title(text: str) -> str:
    match = re.search(r"^title\s*=\s*(['\"])(.*)\1\s*$", text or "", re.MULTILINE)
    return match.group(2).strip() if match else ""
