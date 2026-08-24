"""Process media references in Feishu markdown content."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from feishu.client import FeishuClient
from media.hasher import save_media
from media.compress import MediaCompressor, video_stem
from media.index import MediaIndex
from parser.feishu_text import unescape_feishu_text
from state.store import StateStore

logger = logging.getLogger(__name__)

# Feishu docs/v1/content may export <image token="..."/> or <img src="token" .../>
IMAGE_TAG_PATTERN = re.compile(
    r"<image\s+([^>]*?)\s*/?>",
    re.IGNORECASE,
)
IMG_TAG_PATTERN = re.compile(
    r"<img\s+([^>]*?)\s*/?>",
    re.IGNORECASE,
)
FILE_TAG_PATTERN = re.compile(
    r"<file\s+([^>]*?)\s*/?>",
    re.IGNORECASE,
)
VIDEO_TAG_PATTERN = re.compile(
    r"<video\s+([^>]*?)\s*/?>",
    re.IGNORECASE,
)
FIGURE_TAG_PATTERN = re.compile(
    r"<figure\b[^>]*>(.*?)</figure>",
    re.IGNORECASE | re.DOTALL,
)
SOURCE_TAG_PATTERN = re.compile(
    r"<source\s+([^>]*?)\s*/?>",
    re.IGNORECASE,
)
WHITEBOARD_TAG_PATTERN = re.compile(
    r'<whiteboard\s+[^>]*token="([^"]+)"[^>]*/?>',
    re.IGNORECASE,
)
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
ATTR_PATTERN = re.compile(r'(\w+)="([^"]*)"')
FEISHU_MEDIA_URL_PATTERN = re.compile(
    r"https?://[^/]*feishu\.cn/",
    re.IGNORECASE,
)


@dataclass
class ImageRef:
    token: str
    alt: str = ""
    caption: str = ""


def parse_tag_attrs(attr_string: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in ATTR_PATTERN.finditer(attr_string)}


def image_ref_from_attrs(tag_name: str, attrs: dict[str, str]) -> ImageRef | None:
    token = attrs.get("token") if tag_name in ("image", "video", "source") else attrs.get("src")
    if not token or token.startswith("http://") or token.startswith("https://"):
        return None
    return ImageRef(
        token=token,
        alt=attrs.get("alt", ""),
        caption=attrs.get("caption", ""),
    )


def is_video_source_attrs(attrs: dict[str, str]) -> bool:
    mime = attrs.get("mime", "").lower()
    return mime.startswith("video/")


def media_ref_from_figure(inner_html: str) -> tuple[ImageRef | None, str]:
    """Return (media_ref, kind) from figure inner HTML; kind is 'video' or 'image'."""
    source_match = SOURCE_TAG_PATTERN.search(inner_html)
    if not source_match:
        return None, "image"

    attrs = parse_tag_attrs(source_match.group(1))
    media_ref = image_ref_from_attrs("source", attrs)
    if not media_ref:
        return None, "image"

    kind = "video" if is_video_source_attrs(attrs) else "image"
    return media_ref, kind


def format_video_markdown(web_path: str, caption: str = "") -> str:
    caption = unescape_feishu_text(caption).strip()
    if caption:
        return (
            f'{{{{< video src="{web_path}" '
            f'caption="{_escape_shortcode_attr(caption)}" >}}}}'
        )
    return f'{{{{< video src="{web_path}" >}}}}'


def format_image_markdown(web_path: str, caption: str = "") -> str:
    caption = unescape_feishu_text(caption).strip()

    if caption:
        return (
            f'{{{{< figure src="{web_path}" '
            f'caption="{_escape_shortcode_attr(caption)}" >}}}}'
        )

    return f"![]({web_path})"


def _escape_shortcode_attr(value: str) -> str:
    return value.replace('"', '\\"')


VIDEO_CAPTION_MAX_CHARS = 60
VIDEO_CAPTION_PREFIX_MAX_CHARS = 120
VIDEO_FILENAME_SUFFIXES = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi")
VIDEO_CAPTION_PREFIX = re.compile(r"^(Figure|Fig\.|Video|视频|图)\s", re.IGNORECASE)
FIGURE_CAPTION_LINE = re.compile(r"^Figure\b", re.IGNORECASE)


def _normalize_figure_caption_line(line: str) -> str:
    text = unescape_feishu_text(line).strip()
    if len(text) >= 2 and text.startswith("*") and text.endswith("*"):
        inner = text[1:-1].strip()
        if inner and not inner.startswith("*"):
            text = inner
    return text


def _is_figure_caption_line(line: str) -> bool:
    text = _normalize_figure_caption_line(line)
    if not text:
        return False
    if text.startswith(("#", "!", "<", "{", "|", "```")):
        return False
    if re.match(r"^\d+\.\s", text):
        return False
    return bool(FIGURE_CAPTION_LINE.match(text))


def _is_probable_caption_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith(("#", "-", "*", ">", "!", "<", "{", "|", "```")):
        return False
    if re.match(r"^\d+\.\s", s):
        return False
    if (
        IMAGE_TAG_PATTERN.search(s)
        or IMG_TAG_PATTERN.search(s)
        or VIDEO_TAG_PATTERN.search(s)
        or FIGURE_TAG_PATTERN.search(s)
        or SOURCE_TAG_PATTERN.search(s)
        or FILE_TAG_PATTERN.search(s)
    ):
        return False
    if MARKDOWN_IMAGE_PATTERN.search(s):
        return False
    return True


def _is_probable_video_caption_line(line: str) -> bool:
    if not _is_probable_caption_line(line):
        return False
    s = line.strip()
    if VIDEO_CAPTION_PREFIX.match(s):
        return len(s) <= VIDEO_CAPTION_PREFIX_MAX_CHARS
    return len(s) <= VIDEO_CAPTION_MAX_CHARS


def _is_video_filename(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in VIDEO_FILENAME_SUFFIXES)


def _update_grid_depth(line: str, depth: int) -> int:
    lower = line.lower()
    depth += lower.count("<grid")
    depth -= lower.count("</grid>")
    return max(0, depth)


def _next_non_empty_line(lines: list[str], start: int) -> tuple[str, int] | tuple[None, None]:
    for j in range(start, len(lines)):
        text = lines[j].strip()
        if text:
            return text, j
    return None, None


def _caption_from_next_line(
    lines: list[str],
    index: int,
    *,
    for_video: bool = False,
    for_image: bool = False,
    in_grid: bool = False,
) -> tuple[str, int]:
    if for_video and in_grid:
        return "", index
    next_text, next_index = _next_non_empty_line(lines, index + 1)
    if not next_text:
        return "", index
    if for_video:
        if not _is_probable_video_caption_line(next_text):
            return "", index
    elif for_image:
        if not _is_figure_caption_line(next_text):
            return "", index
        return _normalize_figure_caption_line(next_text), next_index
    elif not _is_probable_caption_line(next_text):
        return "", index
    return unescape_feishu_text(next_text), next_index


def _is_local_media_path(src: str) -> bool:
    return src.startswith("/image/") or src.startswith("/video/")


def _is_feishu_media_url(src: str) -> bool:
    return bool(FEISHU_MEDIA_URL_PATTERN.search(src))


@dataclass
class MediaProcessor:
    client: FeishuClient
    image_dir: object
    video_dir: object
    media_index: MediaIndex = field(default_factory=MediaIndex)
    token_cache: dict[str, str] | None = None
    url_cache: dict[str, str] | None = None
    compressor: MediaCompressor | None = None
    token_store: StateStore | None = None

    def __post_init__(self) -> None:
        if self.token_cache is None:
            self.token_cache = {}
        if self.url_cache is None:
            self.url_cache = {}

    def _media_path_exists(self, web_path: str) -> bool:
        if web_path.startswith("/video/"):
            video_dir = Path(self.video_dir)
            fs_path = video_dir / Path(web_path).name
            digest = video_stem(fs_path)
            if self.compressor and self.compressor.video_compress_active():
                return self.compressor.video_derivatives_ready(digest, video_dir)
            return fs_path.exists()

        if web_path.startswith("/image/"):
            return (Path(self.image_dir) / Path(web_path).name).exists()

        return False

    def _remember_token_path(self, token: str, media_type: str, web_path: str) -> None:
        cache_key = f"{media_type}:{token}"
        self.token_cache[cache_key] = web_path
        if self.token_store is not None:
            self.token_store.set_media_path(token, media_type, web_path)

    def _lookup_cached_token_path(self, token: str, media_type: str) -> str | None:
        cache_key = f"{media_type}:{token}"
        if cache_key in self.token_cache:
            web_path = self.token_cache[cache_key]
            if self._media_path_exists(web_path):
                return web_path

        if self.token_store is None:
            return None

        web_path = self.token_store.get_media_path(token, media_type)
        if web_path and self._media_path_exists(web_path):
            logger.info(
                "Reuse cached media token=%s type=%s path=%s",
                token[:8],
                media_type,
                web_path,
            )
            self.token_cache[cache_key] = web_path
            return web_path
        return None

    def resolve_token(self, token: str, *, media_type: str = "media") -> str:
        cached = self._lookup_cached_token_path(token, media_type)
        if cached:
            return cached

        data, content_type = self.client.download_media(
            token,
            media_type="whiteboard" if media_type == "whiteboard" else "media",
        )
        web_path, _ = save_media(
            data,
            content_type,
            self.image_dir,
            self.video_dir,
            compressor=self.compressor,
        )
        self._remember_token_path(token, media_type, web_path)
        return web_path

    def resolve_url(self, url: str) -> str:
        if url in self.url_cache:
            cached = self.url_cache[url]
            if self._media_path_exists(cached):
                return cached

        token = self.media_index.lookup_by_url(url)
        if token:
            return self.resolve_token(token)

        data, content_type = self.client.download_media_url(url)
        web_path, _ = save_media(
            data,
            content_type,
            self.image_dir,
            self.video_dir,
            compressor=self.compressor,
        )
        self.url_cache[url] = web_path
        return web_path

    def resolve_image_src(self, src: str) -> str | None:
        src = src.strip()
        if _is_local_media_path(src):
            return src

        token = self.media_index.lookup_by_url(src)
        if not token and not src.startswith("http"):
            token = self.media_index.lookup_by_relative_path(src)

        if token:
            return self.resolve_token(token)

        if src.startswith("http") and _is_feishu_media_url(src):
            return self.resolve_url(src)

        if src.startswith("http"):
            logger.warning("Skipping non-Feishu remote image URL: %s", src[:120])
            return None

        logger.warning("Could not resolve local image path without media index: %s", src)
        return None

    def _render_image(self, image_ref: ImageRef) -> str:
        web_path = self.resolve_token(image_ref.token)
        return format_image_markdown(web_path, image_ref.caption)

    def _render_video(self, media_ref: ImageRef) -> str:
        web_path = self.resolve_token(media_ref.token)
        return format_video_markdown(web_path, media_ref.caption)

    def _render_figure(self, inner_html: str, *, caption: str = "") -> str:
        media_ref, kind = media_ref_from_figure(inner_html)
        if not media_ref:
            return inner_html
        if kind == "video":
            return self._render_video(
                ImageRef(token=media_ref.token, caption=caption or media_ref.caption)
            )
        return self._render_image(
            ImageRef(
                token=media_ref.token,
                alt=media_ref.alt,
                caption=caption or media_ref.caption,
            )
        )

    def _render_file(self, token: str, *, caption: str = "", name: str = "") -> str:
        web_path = self.resolve_token(token)
        label = caption or name
        if web_path.startswith("/video/"):
            return format_video_markdown(web_path, label)
        if web_path.startswith("/image/"):
            return format_image_markdown(web_path, caption=label)
        logger.warning("Unsupported file attachment token=%s saved as %s", token, web_path)
        return f"\n> ⚠️ 不支持的附件类型 (token: {token})\n"

    def _replace_image_line(
        self,
        line: str,
        lines: list[str],
        index: int,
        *,
        in_grid: bool = False,
    ) -> tuple[str, int]:
        markdown_match = MARKDOWN_IMAGE_PATTERN.search(line)
        if markdown_match:
            src = markdown_match.group(2).strip()
            web_path = src if _is_local_media_path(src) else self.resolve_image_src(src)
            if web_path:
                skip_until = index
                alt = unescape_feishu_text(markdown_match.group(1)).strip()
                caption, skip_until = _caption_from_next_line(
                    lines,
                    index,
                    for_image=True,
                )
                if not caption:
                    caption = alt
                replacement = format_image_markdown(web_path, caption=caption)
                new_line = MARKDOWN_IMAGE_PATTERN.sub(replacement, line, count=1)
                return new_line, skip_until

        figure_match = FIGURE_TAG_PATTERN.search(line)
        if figure_match:
            inner_html = figure_match.group(1)
            media_ref, kind = media_ref_from_figure(inner_html)
            if media_ref:
                skip_until = index
                caption = media_ref.caption
                if not caption:
                    caption, skip_until = _caption_from_next_line(
                        lines,
                        index,
                        for_video=kind == "video",
                        for_image=kind == "image",
                        in_grid=in_grid,
                    )
                rendered = self._render_figure(inner_html, caption=caption)
                new_line = FIGURE_TAG_PATTERN.sub(rendered, line, count=1)
                return new_line, skip_until

        for pattern, tag_name in (
            (IMG_TAG_PATTERN, "img"),
            (IMAGE_TAG_PATTERN, "image"),
            (VIDEO_TAG_PATTERN, "video"),
            (SOURCE_TAG_PATTERN, "source"),
        ):
            match = pattern.search(line)
            if not match:
                continue

            attrs = parse_tag_attrs(match.group(1))
            image_ref = image_ref_from_attrs(tag_name, attrs)
            if not image_ref:
                continue

            skip_until = index
            if not image_ref.caption:
                is_video = tag_name == "video" or (
                    tag_name == "source" and is_video_source_attrs(attrs)
                )
                caption, skip_until = _caption_from_next_line(
                    lines,
                    index,
                    for_video=is_video,
                    for_image=not is_video,
                    in_grid=in_grid,
                )
                if caption:
                    image_ref.caption = caption

            if tag_name == "video" or (
                tag_name == "source" and is_video_source_attrs(attrs)
            ):
                rendered = self._render_video(image_ref)
            elif tag_name == "source":
                rendered = self._render_image(image_ref)
            else:
                rendered = self._render_image(image_ref)
            new_line = pattern.sub(rendered, line, count=1)
            return new_line, skip_until

        file_match = FILE_TAG_PATTERN.search(line)
        if file_match:
            attrs = parse_tag_attrs(file_match.group(1))
            token = attrs.get("token")
            if token:
                skip_until = index
                caption = attrs.get("caption", "")
                name = attrs.get("name", "")
                if not caption:
                    caption, skip_until = _caption_from_next_line(
                        lines,
                        index,
                        for_video=_is_video_filename(name),
                        for_image=not _is_video_filename(name),
                        in_grid=in_grid,
                    )
                rendered = self._render_file(token, caption=caption, name=name)
                new_line = FILE_TAG_PATTERN.sub(rendered, line, count=1)
                return new_line, skip_until

        return line, index

    def process_body(self, body: str) -> str:
        lines = body.split("\n")
        output: list[str] = []
        i = 0
        grid_depth = 0

        while i < len(lines):
            line = lines[i]
            in_grid = grid_depth > 0 or "<grid" in line.lower()
            new_line, skip_until = self._replace_image_line(
                line, lines, i, in_grid=in_grid
            )
            output.append(new_line)
            grid_depth = _update_grid_depth(line, grid_depth)
            i = skip_until + 1

        result = "\n".join(output)

        for match in FIGURE_TAG_PATTERN.finditer(result):
            inner_html = match.group(1)
            media_ref, _kind = media_ref_from_figure(inner_html)
            if not media_ref:
                continue
            replacement = self._render_figure(inner_html, caption=media_ref.caption)
            result = result.replace(match.group(0), replacement, 1)

        for pattern in (
            IMAGE_TAG_PATTERN,
            IMG_TAG_PATTERN,
            VIDEO_TAG_PATTERN,
            SOURCE_TAG_PATTERN,
            FILE_TAG_PATTERN,
        ):
            for match in pattern.finditer(result):
                if pattern is FILE_TAG_PATTERN:
                    attrs = parse_tag_attrs(match.group(1))
                    token = attrs.get("token")
                    if not token:
                        continue
                    replacement = self._render_file(
                        token,
                        caption=attrs.get("caption", ""),
                        name=attrs.get("name", ""),
                    )
                else:
                    tag_name = (
                        "image"
                        if pattern is IMAGE_TAG_PATTERN
                        else "video"
                        if pattern is VIDEO_TAG_PATTERN
                        else "source"
                        if pattern is SOURCE_TAG_PATTERN
                        else "img"
                    )
                    attrs = parse_tag_attrs(match.group(1))
                    media_ref = image_ref_from_attrs(tag_name, attrs)
                    if not media_ref:
                        continue
                    if tag_name == "video" or (
                        tag_name == "source" and is_video_source_attrs(attrs)
                    ):
                        replacement = self._render_video(media_ref)
                    else:
                        replacement = self._render_image(media_ref)

                result = result.replace(match.group(0), replacement, 1)

        for match in WHITEBOARD_TAG_PATTERN.finditer(result):
            token = match.group(1)
            replacement = self._render_whiteboard(token, match.group(0))
            result = result.replace(match.group(0), replacement, 1)

        return result

    def _render_whiteboard(self, token: str, original: str) -> str:
        try:
            web_path = self.resolve_token(token, media_type="whiteboard")
            return format_image_markdown(web_path)
        except Exception as exc:
            logger.warning("Failed to download whiteboard token=%s: %s", token, exc)
            return f"\n> ⚠️ 画板内容需手动处理 (token: {token})\n"

    def find_first_image(self, text: str) -> str | None:
        """Return resolved web path for the first image reference in *text*."""
        for pattern in (IMG_TAG_PATTERN, IMAGE_TAG_PATTERN, MARKDOWN_IMAGE_PATTERN):
            match = pattern.search(text)
            if not match:
                continue
            if pattern is MARKDOWN_IMAGE_PATTERN:
                src = match.group(2).strip()
                return self.resolve_image_src(src)
            attrs = parse_tag_attrs(match.group(1))
            tag_name = "img" if pattern is IMG_TAG_PATTERN else "image"
            image_ref = image_ref_from_attrs(tag_name, attrs)
            if image_ref:
                return self.resolve_token(image_ref.token)
        return None

    def resolve_featured_image(self, metadata_region: str, body: str) -> str | None:
        """Pick cover image: metadata region first, else first image in full doc."""
        featured = self.find_first_image(metadata_region)
        if featured:
            return featured

        full_doc = metadata_region
        if body:
            full_doc = f"{metadata_region}\n{body}"
        return self.find_first_image(full_doc)
