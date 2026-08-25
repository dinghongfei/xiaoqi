"""Scan preview/_wechat into index.json for the homepage list."""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_FRONT_MATTER_TITLE = re.compile(
    r"^title\s*=\s*(['\"])(.*)\1\s*$",
    re.MULTILINE,
)
_TRANSLATION_KEY = re.compile(
    r"^translationKey\s*=\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
_PLACEHOLDER_TITLE = re.compile(r"^公众号预览\s*·\s*")
_CATALOG_NAME = "index.json"


def _front_matter_title(text: str) -> str:
    match = _FRONT_MATTER_TITLE.search(text)
    return match.group(2).strip() if match else ""


def _title_from_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = _TITLE_RE.search(text)
    if not match:
        return ""
    return unescape(re.sub(r"\s+", " ", match.group(1))).strip()


def _is_placeholder_title(title: str) -> bool:
    return bool(title) and _PLACEHOLDER_TITLE.match(title) is not None


def _title_from_hugo(hugo_root: Path | None, lang: str, slug: str) -> str:
    if hugo_root is None:
        return ""
    root = Path(hugo_root)
    direct = root / "content" / lang / "blog" / f"{slug}.md"
    paths = [direct]
    if lang != "zh-cn":
        paths.append(root / "content" / "zh-cn" / "blog" / f"{slug}.md")
    for path in paths:
        if path.is_file():
            title = _front_matter_title(path.read_text(encoding="utf-8"))
            if title:
                return title
    content = root / "content"
    if not content.is_dir():
        return ""
    for blog in content.glob("*/blog"):
        if not blog.is_dir():
            continue
        for path in blog.glob("*.md"):
            if path.name.startswith("_"):
                continue
            text = path.read_text(encoding="utf-8")
            key = _TRANSLATION_KEY.search(text)
            if path.stem == slug or (key and key.group(1) == slug):
                title = _front_matter_title(text)
                if title:
                    return title
    return ""


def _article_title(
    page: Path,
    *,
    lang: str,
    slug: str,
    hugo_root: Path | None,
) -> str:
    hugo_title = _title_from_hugo(hugo_root, lang, slug)
    if hugo_title:
        return hugo_title
    html_title = _title_from_html(page)
    if html_title and not _is_placeholder_title(html_title):
        return html_title
    return slug


def scan_wechat_articles(
    preview_dir: Path,
    hugo_root: Path | None = None,
) -> list[dict[str, str]]:
    root = Path(preview_dir) / "_wechat"
    if not root.is_dir():
        return []
    pages: list[tuple[float, dict[str, str]]] = []
    for lang_dir in root.iterdir():
        if not lang_dir.is_dir() or lang_dir.name.startswith("."):
            continue
        for slug_dir in lang_dir.iterdir():
            if not slug_dir.is_dir() or slug_dir.name.startswith("."):
                continue
            page = slug_dir / "index.html"
            if not page.is_file():
                continue
            slug = slug_dir.name
            lang = lang_dir.name
            pages.append(
                (
                    page.stat().st_mtime,
                    {
                        "title": _article_title(
                            page, lang=lang, slug=slug, hugo_root=hugo_root
                        ),
                        "lang": lang,
                        "slug": slug,
                        "url": f"/_wechat/{lang}/{slug}/",
                    },
                )
            )
    pages.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in pages]


def write_wechat_catalog(
    preview_dir: Path,
    hugo_root: Path | None = None,
) -> Path:
    root = Path(preview_dir) / "_wechat"
    root.mkdir(parents=True, exist_ok=True)
    payload = {"articles": scan_wechat_articles(preview_dir, hugo_root)}
    out = root / _CATALOG_NAME
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out
