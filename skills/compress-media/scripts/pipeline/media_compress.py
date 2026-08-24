"""Batch-compress static images and videos. Missing ffmpeg is a skip, not a crash."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from config import Settings
from media.compress import (
    IMAGE_COMPRESS_SUFFIXES,
    MediaCompressor,
    MediaCompressError,
    VIDEO_SOURCE_SUFFIXES,
    is_video_derivative,
    video_stem,
)
from pipeline.step_result import StepResult

logger = logging.getLogger(__name__)


def compress_static_media(
    settings: Settings,
    *,
    force: bool = False,
    image_dir: Path | None = None,
    video_dir: Path | None = None,
) -> StepResult:
    if not force and not settings.media_compress_enabled:
        return StepResult(status="ok", message="已跳过：MEDIA_COMPRESS_ENABLED=false")

    ffmpeg = shutil.which(settings.ffmpeg_bin) or (
        settings.ffmpeg_bin if Path(settings.ffmpeg_bin).is_file() else None
    )
    if not ffmpeg:
        return StepResult(
            status="ok",
            message="已跳过：未安装 ffmpeg，图片/视频保持原样。安装 ffmpeg 后可再运行本 Skill。",
        )

    compressor = MediaCompressor.from_settings(settings)
    compressor.enabled = True
    image_dir = Path(image_dir) if image_dir else settings.image_dir
    video_dir = Path(video_dir) if video_dir else settings.video_dir

    try:
        video_count = _compress_videos(compressor, video_dir)
        image_count = _compress_images(compressor, image_dir)
    except MediaCompressError as exc:
        return StepResult(status="error", message=str(exc))

    message = f"已压缩 images={image_count}, videos={video_count}"
    logger.info("Static media compression finished: %s", message)
    return StepResult(status="ok", message=message)


def _compress_videos(compressor: MediaCompressor, video_dir: Path) -> int:
    if not compressor.video_compress_active():
        return 0
    if not video_dir.is_dir():
        return 0

    count = 0
    for path in sorted(video_dir.iterdir()):
        if not path.is_file():
            continue
        if is_video_derivative(path):
            continue
        if path.suffix.lower() not in VIDEO_SOURCE_SUFFIXES:
            continue
        digest = video_stem(path)
        if compressor.video_derivatives_ready(digest, video_dir):
            continue
        compressor.compress_video(path, digest, video_dir)
        count += 1
    return count


def _compress_images(compressor: MediaCompressor, image_dir: Path) -> int:
    if not image_dir.is_dir():
        return 0

    count = 0
    for path in sorted(image_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_COMPRESS_SUFFIXES:
            continue
        digest = path.stem
        ext = path.suffix.lower()
        if ext == ".jpeg":
            ext = ".jpg"
        output_path = image_dir / f"{digest}{ext}"
        if output_path.exists() and output_path.stat().st_mtime >= path.stat().st_mtime:
            continue
        compressor.compress_image(path, digest, image_dir)
        count += 1
    return count
