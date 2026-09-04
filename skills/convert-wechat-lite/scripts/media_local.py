"""Download Feishu images/videos next to raw.md / raw.xml (same work dir)."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

IMAGE_TAG_PATTERN = re.compile(r"<image\s+([^>]*?)\s*/?>", re.IGNORECASE)
IMG_TAG_PATTERN = re.compile(r"<img\s+([^>]*?)\s*/?>", re.IGNORECASE)
VIDEO_TAG_PATTERN = re.compile(r"<video\s+([^>]*?)\s*/?>", re.IGNORECASE)
SOURCE_TAG_PATTERN = re.compile(r"<source\s+([^>]*?)\s*/?>", re.IGNORECASE)
FILE_TAG_PATTERN = re.compile(r"<file\s+([^>]*?)\s*/?>", re.IGNORECASE)
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
ATTR_PATTERN = re.compile(r'(\w+)="([^"]*)"')
HTTP_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

CONTENT_TYPE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}

# Markdown often has https://feishu.cn/file/<TOKEN> which needs login over HTTP.
_FEISHU_FILE_URL = re.compile(
    r"https?://(?:[\w.-]+\.)?(?:feishu\.cn|larksuite\.com)/file/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


def file_token_from_url(url: str) -> str:
    """Extract Feishu/Lark file token from /file/<token> URLs."""
    match = _FEISHU_FILE_URL.search(url or "")
    return match.group(1) if match else ""


def _is_feishu_file_url(url: str) -> bool:
    return bool(file_token_from_url(url))


class MediaMissingError(Exception):
    def __init__(self, token: str, media_type: str = "media"):
        self.token = token
        self.media_type = media_type
        super().__init__(token)


@dataclass
class MediaRef:
    """A media reference found in markdown or XML."""

    key: str  # http URL or file token
    kind: str = "image"  # image | video
    alt: str = ""
    caption: str = ""
    file_token: str = ""  # Feishu token when known (for lark-cli)


@dataclass
class MediaIndex:
    """Map URL ↔ file token from XML."""

    url_to_token: dict[str, str] = field(default_factory=dict)
    token_to_url: dict[str, str] = field(default_factory=dict)


def parse_tag_attrs(attr_string: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in ATTR_PATTERN.finditer(attr_string)}


def _is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _is_local_name(src: str) -> bool:
    """True for a bare filename in the work dir (e.g. abc.png), not URL/path."""
    s = (src or "").strip()
    if s.startswith("./"):
        s = s[2:]
    if not s or _is_http_url(s) or "/" in s or "\\" in s:
        return False
    return True


def content_hash(data: bytes, length: int = 16) -> str:
    return hashlib.sha256(data).hexdigest()[:length]


def guess_extension(content_type: str | None, data: bytes) -> str:
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct in CONTENT_TYPE_EXT:
            return CONTENT_TYPE_EXT[ct]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"GIF8":
        return ".gif"
    if data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
        return ".webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return ".mp4"
    return mimetypes.guess_extension(content_type or "") or ".bin"


def build_media_index_from_xml(xml: str) -> MediaIndex:
    index = MediaIndex()
    patterns = (
        IMG_TAG_PATTERN,
        IMAGE_TAG_PATTERN,
        VIDEO_TAG_PATTERN,
        SOURCE_TAG_PATTERN,
        FILE_TAG_PATTERN,
    )
    for pattern in patterns:
        for match in pattern.finditer(xml or ""):
            attrs = parse_tag_attrs(match.group(1))
            token = (attrs.get("token") or "").strip()
            href = (attrs.get("href") or "").strip()
            src = (attrs.get("src") or "").strip()
            urls = [u for u in (href, src) if u and _is_http_url(u)]
            if token and not _is_http_url(token):
                for url in urls:
                    index.url_to_token[url] = token
                    index.token_to_url[token] = url
            elif token and _is_http_url(token):
                index.url_to_token[token] = token
            for url in urls:
                index.url_to_token.setdefault(url, token if token and not _is_http_url(token) else url)
    return index


def _ref_from_attrs(tag_name: str, attrs: dict[str, str]) -> MediaRef | None:
    token = (attrs.get("token") or "").strip()
    href = (attrs.get("href") or "").strip()
    src = (attrs.get("src") or "").strip()
    mime = (attrs.get("mime") or "").lower()
    is_video = (
        tag_name == "video"
        or mime.startswith("video/")
        or any(src.lower().endswith(ext) for ext in VIDEO_EXTS)
    )
    kind = "video" if is_video else "image"
    url = ""
    for candidate in (href, src, token):
        if candidate and _is_http_url(candidate):
            url = candidate
            break
    file_token = token if token and not _is_http_url(token) else ""
    if not file_token:
        file_token = file_token_from_url(url) or file_token_from_url(src) or file_token_from_url(href)
    key = url or file_token or src or token
    if not key:
        return None
    return MediaRef(
        key=key,
        kind=kind,
        alt=attrs.get("alt", ""),
        caption=attrs.get("caption", ""),
        file_token=file_token,
    )


def collect_media_refs(markdown: str, xml: str = "") -> list[MediaRef]:
    """Collect image/video refs from markdown and XML (stable order, deduped)."""
    seen: set[str] = set()
    refs: list[MediaRef] = []

    def add(ref: MediaRef | None) -> None:
        if ref is None or ref.key in seen:
            return
        seen.add(ref.key)
        refs.append(ref)

    for match in MARKDOWN_IMAGE_PATTERN.finditer(markdown or ""):
        src = match.group(2).strip()
        add(
            MediaRef(
                key=src,
                kind="image",
                alt=match.group(1),
                file_token=file_token_from_url(src),
            )
        )

    for pattern, tag in (
        (IMG_TAG_PATTERN, "img"),
        (IMAGE_TAG_PATTERN, "image"),
        (VIDEO_TAG_PATTERN, "video"),
        (SOURCE_TAG_PATTERN, "source"),
        (FILE_TAG_PATTERN, "file"),
    ):
        for match in pattern.finditer(markdown or ""):
            add(_ref_from_attrs(tag, parse_tag_attrs(match.group(1))))

    for pattern, tag in (
        (IMG_TAG_PATTERN, "img"),
        (IMAGE_TAG_PATTERN, "image"),
        (VIDEO_TAG_PATTERN, "video"),
        (SOURCE_TAG_PATTERN, "source"),
        (FILE_TAG_PATTERN, "file"),
    ):
        for match in pattern.finditer(xml or ""):
            add(_ref_from_attrs(tag, parse_tag_attrs(match.group(1))))

    return refs


def format_image_markdown(filename: str, caption: str = "") -> str:
    caption = (caption or "").strip()
    if caption:
        safe = caption.replace('"', '\\"')
        return f'{{{{< figure src="{filename}" caption="{safe}" >}}}}'
    return f"![]({filename})"


def format_video_markdown(filename: str, caption: str = "") -> str:
    caption = (caption or "").strip()
    if caption:
        safe = caption.replace('"', '\\"')
        return f'{{{{< video src="{filename}" caption="{safe}" >}}}}'
    return f'{{{{< video src="{filename}" >}}}}'


@dataclass
class MediaProcessor:
    """Download media into work_dir (same folder as raw.md / raw.xml)."""

    work_dir: Path
    media_index: MediaIndex = field(default_factory=MediaIndex)
    url_cache: dict[str, str] = field(default_factory=dict)

    def _find_existing(self, stem: str) -> Path | None:
        exact = self.work_dir / stem
        if exact.is_file():
            return exact
        matches = sorted(self.work_dir.glob(f"{stem}.*"))
        return matches[0] if matches else None

    def _download_http(self, url: str) -> tuple[bytes, str | None]:
        resp = httpx.get(
            url,
            timeout=120,
            follow_redirects=True,
            headers=HTTP_DOWNLOAD_HEADERS,
        )
        resp.raise_for_status()
        content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()
        data = resp.content
        if not data or content_type.startswith("text/html"):
            raise MediaMissingError(url, "url")
        return data, content_type or None

    def _download_via_lark(self, file_token: str, *, whiteboard: bool = False) -> Path:
        from lark_fetch import media_download_to

        self.work_dir.mkdir(parents=True, exist_ok=True)
        dest = self.work_dir / file_token
        path = media_download_to(file_token, dest, whiteboard=whiteboard)
        if path is None or not path.is_file():
            raise MediaMissingError(file_token, "media")
        return path

    def _save_bytes(self, key: str, data: bytes, content_type: str | None) -> str:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        stem = content_hash(key.encode())
        existing = self._find_existing(stem)
        if existing is not None:
            return existing.name
        ext = guess_extension(content_type, data)
        dest = self.work_dir / f"{stem}{ext}"
        dest.write_bytes(data)
        return dest.name

    def resolve(self, ref: MediaRef) -> str:
        """Download if needed; return filename in work_dir."""
        if ref.key in self.url_cache:
            return self.url_cache[ref.key]

        # Already a local filename
        if _is_local_name(ref.key):
            name = ref.key[2:] if ref.key.startswith("./") else ref.key
            path = self.work_dir / name
            if path.is_file():
                self.url_cache[ref.key] = name
                return name

        file_token = (
            ref.file_token
            or file_token_from_url(ref.key)
            or self.media_index.url_to_token.get(ref.key, "")
        )
        if file_token and _is_http_url(file_token):
            file_token = file_token_from_url(file_token) or ""
        if not file_token and not _is_http_url(ref.key):
            file_token = ref.key

        # Prefer existing lark-cli download named by token
        if file_token:
            existing = self._find_existing(file_token)
            if existing is not None:
                name = existing.name
                self.url_cache[ref.key] = name
                return name

        url = ref.key if _is_http_url(ref.key) else self.media_index.token_to_url.get(file_token, "")

        # feishu.cn/file/<token> always needs auth — use lark-cli first
        if file_token and (not url or _is_feishu_file_url(url) or _is_feishu_file_url(ref.key)):
            try:
                path = self._download_via_lark(file_token)
                data = path.read_bytes()
                name = self._save_bytes(file_token, data, None)
                self.url_cache[ref.key] = name
                self.url_cache[file_token] = name
                return name
            except Exception as exc:
                logger.warning("lark-cli 下载失败 token=%s: %s", file_token[:24], exc)
                # fall through to HTTP only if not a feishu file URL
                if _is_feishu_file_url(url or ref.key):
                    raise MediaMissingError(file_token, ref.kind) from exc

        # Public / CDN HTTP download
        if url and not _is_feishu_file_url(url):
            try:
                data, content_type = self._download_http(url)
                name = self._save_bytes(url, data, content_type)
                self.url_cache[ref.key] = name
                if file_token:
                    self.url_cache[file_token] = name
                return name
            except Exception as exc:
                logger.warning("HTTP 下载失败，尝试 lark-cli：%s (%s)", url[:80], exc)

        if file_token and not _is_http_url(file_token):
            try:
                path = self._download_via_lark(file_token)
                data = path.read_bytes()
                name = self._save_bytes(file_token, data, None)
                self.url_cache[ref.key] = name
                self.url_cache[file_token] = name
                return name
            except Exception as exc:
                logger.warning("lark-cli 下载失败 token=%s: %s", file_token[:24], exc)
                raise MediaMissingError(file_token, ref.kind) from exc

        raise MediaMissingError(ref.key, ref.kind)

    def process_body(self, body: str, *, xml_text: str = "") -> str:
        self.media_index = build_media_index_from_xml(xml_text)
        refs = collect_media_refs(body, xml_text)
        mapping: dict[str, MediaRef] = {}
        for ref in refs:
            filename = self.resolve(ref)
            mapping[ref.key] = MediaRef(
                key=filename,
                kind=ref.kind,
                alt=ref.alt,
                caption=ref.caption,
                file_token=ref.file_token,
            )
            # also map URL variants
            if ref.file_token:
                mapping[ref.file_token] = mapping[ref.key]

        def repl_md(match: re.Match[str]) -> str:
            alt, src = match.group(1), match.group(2).strip()
            resolved = mapping.get(src)
            if not resolved:
                return match.group(0)
            if resolved.kind == "video":
                return format_video_markdown(resolved.key, caption=alt)
            return format_image_markdown(resolved.key, caption=alt)

        body = MARKDOWN_IMAGE_PATTERN.sub(repl_md, body)

        def repl_tag(pattern: re.Pattern[str], tag: str) -> None:
            nonlocal body

            def _repl(match: re.Match[str]) -> str:
                attrs = parse_tag_attrs(match.group(1))
                ref = _ref_from_attrs(tag, attrs)
                if not ref:
                    return match.group(0)
                resolved = mapping.get(ref.key) or mapping.get(ref.file_token)
                if not resolved:
                    # try resolve on the fly
                    try:
                        name = self.resolve(ref)
                    except MediaMissingError:
                        return match.group(0)
                    resolved = MediaRef(key=name, kind=ref.kind, alt=ref.alt, caption=ref.caption)
                cap = resolved.caption or ref.caption or ref.alt
                if resolved.kind == "video" or ref.kind == "video":
                    return format_video_markdown(resolved.key, caption=cap)
                return format_image_markdown(resolved.key, caption=cap)

            body = pattern.sub(_repl, body)

        repl_tag(IMG_TAG_PATTERN, "img")
        repl_tag(IMAGE_TAG_PATTERN, "image")
        repl_tag(VIDEO_TAG_PATTERN, "video")
        repl_tag(SOURCE_TAG_PATTERN, "source")
        repl_tag(FILE_TAG_PATTERN, "file")
        return body


def file_to_data_uri(path: Path) -> str:
    import base64

    data = path.read_bytes()
    ext = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
    }.get(ext, "application/octet-stream")
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def embed_local_media_in_html(html: str, base_dir: Path) -> str:
    """Embed same-dir image files as data URIs so single-file preview works."""

    def repl(match: re.Match[str]) -> str:
        prefix, src, suffix = match.group(1), match.group(2), match.group(3)
        if src.startswith("data:") or _is_http_url(src):
            return match.group(0)
        name = src.split("?")[0].lstrip("./")
        if "/" in name:
            return match.group(0)
        path = (base_dir / name).resolve()
        if not path.is_file():
            return match.group(0)
        if path.suffix.lower() in VIDEO_EXTS:
            return match.group(0)
        try:
            uri = file_to_data_uri(path)
        except OSError:
            return match.group(0)
        return f"{prefix}{uri}{suffix}"

    return re.sub(r'(src=")([^"]+)(")', repl, html, flags=re.IGNORECASE)
