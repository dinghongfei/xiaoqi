"""Build media token indexes from Feishu doc XML."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

IMG_TAG_PATTERN = re.compile(r"<img\b([^>]*)/?>", re.IGNORECASE)
SRC_ATTR_PATTERN = re.compile(r'\bsrc="([^"]+)"', re.IGNORECASE)
TOKEN_ATTR_PATTERN = re.compile(r'\btoken="([^"]+)"', re.IGNORECASE)
HREF_ATTR_PATTERN = re.compile(r'\bhref="([^"]+)"', re.IGNORECASE)
VIDEO_TAG_PATTERN = re.compile(r"<video\b([^>]*)/?>", re.IGNORECASE)
SOURCE_TAG_PATTERN = re.compile(r"<source\b([^>]*)/?>", re.IGNORECASE)
FILE_TAG_PATTERN = re.compile(r"<file\b([^>]*)/?>", re.IGNORECASE)
WHITEBOARD_TAG_PATTERN = re.compile(
    r'<whiteboard[^>]*\stoken="([^"]+)"',
    re.IGNORECASE,
)


def _is_http(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


@dataclass
class MediaIndex:
    by_url: dict[str, str] = field(default_factory=dict)
    by_prefix: dict[str, str] = field(default_factory=dict)

    def lookup_by_url(self, url: str) -> str | None:
        if url in self.by_url:
            return self.by_url[url]

        for known_url, token in self.by_url.items():
            if known_url in url or url in known_url:
                return token
        return None

    def lookup_by_relative_path(self, path: str) -> str | None:
        name = path.rsplit("/", 1)[-1]
        stem = name.rsplit(".", 1)[0]
        if "-" in stem:
            prefix = stem.split("-", 1)[1]
            if prefix in self.by_prefix:
                return self.by_prefix[prefix]
        return self.by_prefix.get(stem)


def _register_token(index: MediaIndex, token: str, href: str | None = None) -> None:
    if href:
        index.by_url[href] = token
    if _is_http(token):
        index.by_url[token] = token
        return
    index.by_prefix[token] = token
    index.by_prefix[token[:8]] = token


def _register_attrs(index: MediaIndex, attrs: str, *, token: str | None = None) -> None:
    href_match = HREF_ATTR_PATTERN.search(attrs)
    href = href_match.group(1) if href_match else None
    src_match = SRC_ATTR_PATTERN.search(attrs)
    src = src_match.group(1) if src_match else None
    if token and not _is_http(token):
        _register_token(index, token, href or (src if src and _is_http(src) else None))
        if src and _is_http(src):
            index.by_url[src] = token
        return
    for url in (href, src, token):
        if url and _is_http(url):
            _register_token(index, url, url)


def build_media_index_from_xml(xml: str) -> MediaIndex:
    index = MediaIndex()

    for match in IMG_TAG_PATTERN.finditer(xml):
        attrs = match.group(1)
        src_match = SRC_ATTR_PATTERN.search(attrs)
        token_match = TOKEN_ATTR_PATTERN.search(attrs)
        token = (token_match.group(1) if token_match else None) or (
            src_match.group(1) if src_match else None
        )
        if not token:
            continue
        _register_attrs(index, attrs, token=token)

    for match in WHITEBOARD_TAG_PATTERN.finditer(xml):
        _register_token(index, match.group(1))

    for pattern in (VIDEO_TAG_PATTERN, SOURCE_TAG_PATTERN, FILE_TAG_PATTERN):
        for match in pattern.finditer(xml):
            attrs = match.group(1)
            token_match = TOKEN_ATTR_PATTERN.search(attrs)
            src_match = SRC_ATTR_PATTERN.search(attrs)
            token = (token_match.group(1) if token_match else None) or (
                src_match.group(1) if src_match else None
            )
            if not token:
                continue
            _register_attrs(index, attrs, token=token)

    return index
