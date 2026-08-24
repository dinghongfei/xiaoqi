"""Content-hash based media file naming and deduplication."""

import hashlib
import mimetypes
from pathlib import Path

from media.compress import MediaCompressor

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


def content_hash(data: bytes, length: int = 16) -> str:
    return hashlib.sha256(data).hexdigest()[:length]


def guess_extension(content_type: str | None, data: bytes) -> str:
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct in CONTENT_TYPE_EXT:
            return CONTENT_TYPE_EXT[ct]

    # Magic bytes fallback
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"GIF8":
        return ".gif"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return ".mp4"
    if data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
        return ".webp"

    guessed = mimetypes.guess_extension(content_type or "")
    return guessed or ".bin"


def media_type_from_content_type(content_type: str | None) -> str:
    if content_type and content_type.lower().startswith("video/"):
        return "video"
    return "image"


def save_media(
    data: bytes,
    content_type: str | None,
    image_dir: Path,
    video_dir: Path,
    *,
    compressor: MediaCompressor | None = None,
) -> tuple[str, Path]:
    """Save media with hash filename. Returns (web_path, filesystem_path)."""
    media_type = media_type_from_content_type(content_type)
    ext = guess_extension(content_type, data)
    digest = content_hash(data)
    filename = f"{digest}{ext}"

    target_dir = video_dir if media_type == "video" else image_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename

    if not target.exists():
        target.write_bytes(data)

    if compressor and compressor.enabled:
        if media_type == "video":
            if not compressor.video_compress_active():
                web_prefix = "/video"
                return f"{web_prefix}/{filename}", target
            if compressor.video_derivatives_ready(digest, video_dir):
                return compressor.video_web_path(digest), video_dir / f"{digest}.mp4"
            final_path = compressor.compress_video(target, digest, video_dir)
            return compressor.video_web_path(digest), final_path
        if ext.lower() not in (".svg",):
            output_ext = compressor._image_output_ext(target)
            output = image_dir / f"{digest}{output_ext}"
            if output.exists():
                return compressor.image_web_path(digest, output_ext), output
            web_path, final_path = compressor.compress_image(target, digest, image_dir)
            return web_path, final_path

    web_prefix = "/video" if media_type == "video" else "/image"
    return f"{web_prefix}/{filename}", target
