"""Compress images and videos with ffmpeg for web delivery."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

VIDEO_SOURCE_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
IMAGE_COMPRESS_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
SKIP_IMAGE_SUFFIXES = {".svg"}


class MediaCompressError(Exception):
    pass


@dataclass
class MediaCompressor:
    ffmpeg_bin: str = "ffmpeg"
    timeout: int = 600
    video_max_width: int = 1280
    video_crf_h264: int = 23
    video_crf_av1: int = 30
    video_crf_vp9: int = 30
    image_max_width: int = 1920
    image_webp_quality: int = 80
    enabled: bool = True
    video_enabled: bool = True

    @classmethod
    def from_settings(cls, settings) -> MediaCompressor:
        return cls(
            ffmpeg_bin=settings.ffmpeg_bin,
            timeout=settings.ffmpeg_timeout,
            video_max_width=settings.video_max_width,
            video_crf_h264=settings.video_crf_h264,
            video_crf_av1=settings.video_crf_av1,
            video_crf_vp9=settings.video_crf_vp9,
            image_max_width=settings.image_max_width,
            image_webp_quality=settings.image_webp_quality,
            enabled=settings.media_compress_enabled,
            video_enabled=settings.video_compress_enabled,
        )

    def video_compress_active(self) -> bool:
        return self.enabled and self.video_enabled

    def video_output_paths(self, digest: str, video_dir: Path) -> tuple[Path, Path, Path]:
        return (
            video_dir / f"{digest}.av1.mp4",
            video_dir / f"{digest}.webm",
            video_dir / f"{digest}.mp4",
        )

    def video_derivatives_ready(self, digest: str, video_dir: Path) -> bool:
        if not self.video_compress_active():
            for path in video_dir.iterdir():
                if not path.is_file() or is_video_derivative(path):
                    continue
                if video_stem(path) == digest:
                    return True
            return False

        av1_path, webm_path, mp4_path = self.video_output_paths(digest, video_dir)
        return av1_path.exists() and webm_path.exists() and mp4_path.exists()

    def video_web_path(self, digest: str) -> str:
        return f"/video/{digest}.mp4"

    def image_web_path(self, digest: str, ext: str) -> str:
        return f"/image/{digest}{ext}"

    def _image_output_ext(self, source: Path) -> str:
        ext = source.suffix.lower()
        if ext == ".jpeg":
            return ".jpg"
        return ext

    def _image_ffmpeg_args(self, ext: str, output: Path) -> list[str]:
        scale = self._scale_filter(self.image_max_width)
        args = ["-vf", scale]
        if ext in {".jpg"}:
            q = max(2, min(31, 31 - self.image_webp_quality // 4))
            args.extend(["-q:v", str(q)])
        elif ext == ".png":
            args.extend(["-compression_level", "6"])
        elif ext == ".webp":
            args.extend(["-quality", str(self.image_webp_quality)])
        args.append(str(output))
        return args

    def _run_ffmpeg(self, args: list[str], *, step: str) -> None:
        cmd = [self.ffmpeg_bin, *args]
        logger.info("Running %s: %s", step, cmd)
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaCompressError(f"{step} 超时（>{self.timeout}s）") from exc
        except OSError as exc:
            raise MediaCompressError(f"{step} 启动失败：{exc}") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()
            tail = detail[-1][:300] if detail else ""
            raise MediaCompressError(
                f"{step} 失败（退出码 {completed.returncode}）"
                + (f"：{tail}" if tail else "")
            )

    def _scale_filter(self, max_width: int) -> str:
        return f"scale='min({max_width},iw)':-2"

    def compress_video(self, source: Path, digest: str, video_dir: Path) -> Path:
        """Transcode source video to AV1, VP9, and H.264 MP4."""
        if not self.video_compress_active():
            return source

        video_dir.mkdir(parents=True, exist_ok=True)
        av1_path, webm_path, mp4_path = self.video_output_paths(digest, video_dir)

        if self.video_derivatives_ready(digest, video_dir):
            if source.exists() and source.resolve() != mp4_path.resolve():
                _remove_if_exists(source)
            return mp4_path

        if not source.exists():
            raise MediaCompressError(f"视频源文件不存在: {source}")

        scale = self._scale_filter(self.video_max_width)
        common_input = ["-y", "-i", str(source)]

        with tempfile.TemporaryDirectory(prefix="bot-video-") as tmp:
            tmp_mp4 = Path(tmp) / f"{digest}.mp4"
            self._run_ffmpeg(
                [
                    *common_input,
                    "-vf",
                    scale,
                    "-c:v",
                    "libx264",
                    "-crf",
                    str(self.video_crf_h264),
                    "-preset",
                    "medium",
                    "-movflags",
                    "+faststart",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    str(tmp_mp4),
                ],
                step=f"video h264 {digest}",
            )
            _atomic_replace(tmp_mp4, mp4_path)

            self._run_ffmpeg(
                [
                    *common_input,
                    "-vf",
                    scale,
                    "-c:v",
                    "libsvtav1",
                    "-crf",
                    str(self.video_crf_av1),
                    "-preset",
                    "6",
                    "-g",
                    "240",
                    "-pix_fmt",
                    "yuv420p10le",
                    "-svtav1-params",
                    "tune=0:enable-overlays=1",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "64k",
                    str(av1_path),
                ],
                step=f"video av1 {digest}",
            )

            self._run_ffmpeg(
                [
                    *common_input,
                    "-vf",
                    scale,
                    "-c:v",
                    "libvpx-vp9",
                    "-crf",
                    str(self.video_crf_vp9),
                    "-b:v",
                    "0",
                    "-row-mt",
                    "1",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "64k",
                    str(webm_path),
                ],
                step=f"video vp9 {digest}",
            )

        if source.resolve() != mp4_path.resolve():
            _remove_if_exists(source)

        return mp4_path

    def compress_image(self, source: Path, digest: str, image_dir: Path) -> tuple[str, Path]:
        """Compress raster image in place (keeps original extension for stable URLs)."""
        if not self.enabled:
            return f"/image/{source.name}", source

        ext = self._image_output_ext(source)
        if ext in SKIP_IMAGE_SUFFIXES:
            return f"/image/{source.name}", source

        image_dir.mkdir(parents=True, exist_ok=True)
        output = image_dir / f"{digest}{ext}"
        if output.exists() and output.stat().st_mtime >= source.stat().st_mtime:
            if source.resolve() != output.resolve():
                _remove_if_exists(source)
            return self.image_web_path(digest, ext), output

        with tempfile.TemporaryDirectory(prefix="bot-image-") as tmp:
            tmp_output = Path(tmp) / f"{digest}{ext}"
            self._run_ffmpeg(
                ["-y", "-i", str(source), *self._image_ffmpeg_args(ext, tmp_output)],
                step=f"image {ext.lstrip('.')} {digest}",
            )
            _atomic_replace(tmp_output, output)

        if source.resolve() != output.resolve():
            _remove_if_exists(source)

        return self.image_web_path(digest, ext), output

    def ensure_video(self, source: Path, video_dir: Path) -> Path:
        digest = video_stem(source)
        return self.compress_video(source, digest, video_dir)

    def ensure_image(self, source: Path, image_dir: Path) -> tuple[str, Path]:
        digest = source.stem
        return self.compress_image(source, digest, image_dir)


def video_stem(path: Path) -> str:
    name = path.name
    if name.endswith(".av1.mp4"):
        return name[: -len(".av1.mp4")]
    return path.stem


def is_video_derivative(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".av1.mp4") or name.endswith(".webm")


def _atomic_replace(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.move(str(src), str(dest))


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()
