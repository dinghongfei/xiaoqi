"""Tests for ffmpeg media compression."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from media.compress import (
    MediaCompressor,
    MediaCompressError,
    is_video_derivative,
    video_stem,
)
from media.hasher import save_media
from pipeline.media_compress import compress_static_media


@pytest.fixture
def compressor(tmp_path: Path) -> MediaCompressor:
    return MediaCompressor(
        ffmpeg_bin="ffmpeg",
        timeout=30,
        enabled=True,
    )


def test_video_stem():
    assert video_stem(Path("abc123.mp4")) == "abc123"
    assert video_stem(Path("abc123.av1.mp4")) == "abc123"
    assert video_stem(Path("abc123.webm")) == "abc123"


def test_is_video_derivative():
    assert is_video_derivative(Path("abc.av1.mp4"))
    assert is_video_derivative(Path("abc.webm"))
    assert not is_video_derivative(Path("abc.mp4"))


def test_compress_video_writes_three_formats(compressor: MediaCompressor, tmp_path: Path):
    source = tmp_path / "video" / "abc123.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")

    def fake_run(cmd, **kwargs):
        output = Path(cmd[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"encoded")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("media.compress.subprocess.run", side_effect=fake_run):
        result = compressor.compress_video(source, "abc123", tmp_path / "video")

    video_dir = tmp_path / "video"
    assert (video_dir / "abc123.av1.mp4").exists()
    assert (video_dir / "abc123.webm").exists()
    assert (video_dir / "abc123.mp4").exists()
    assert result == video_dir / "abc123.mp4"


def test_compress_video_skips_when_derivatives_exist(
    compressor: MediaCompressor, tmp_path: Path
):
    video_dir = tmp_path / "video"
    video_dir.mkdir()
    source = video_dir / "abc123.mov"
    source.write_bytes(b"source")
    (video_dir / "abc123.mp4").write_bytes(b"mp4")
    (video_dir / "abc123.av1.mp4").write_bytes(b"av1")
    (video_dir / "abc123.webm").write_bytes(b"webm")

    with patch("media.compress.subprocess.run") as run:
        result = compressor.compress_video(source, "abc123", video_dir)

    run.assert_not_called()
    assert result == video_dir / "abc123.mp4"
    assert not source.exists()


def test_compress_video_skipped_when_video_compress_disabled(tmp_path: Path):
    compressor = MediaCompressor(enabled=True, video_enabled=False)
    source = tmp_path / "video" / "abc123.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")

    with patch("media.compress.subprocess.run") as run:
        result = compressor.compress_video(source, "abc123", tmp_path / "video")

    run.assert_not_called()
    assert result == source


def test_save_media_skips_video_compress_when_disabled(tmp_path: Path):
    compressor = MediaCompressor(enabled=True, video_enabled=False)
    data = b"\x00" * 8 + b"ftypmp42" + b"\x00" * 20

    with patch("media.compress.subprocess.run") as run:
        web_path, final = save_media(
            data,
            "video/mp4",
            tmp_path / "image",
            tmp_path / "video",
            compressor=compressor,
        )

    run.assert_not_called()
    assert web_path.endswith(".mp4")
    assert final.exists()


def test_compress_static_media_skips_videos_when_disabled(tmp_path: Path, monkeypatch):
    from config import Settings

    video_dir = tmp_path / "static" / "video"
    video_dir.mkdir(parents=True)
    (video_dir / "feedface.mp4").write_bytes(b"source")

    settings = Settings(
        _env_file=None,
        hugo_root=tmp_path,
        media_compress_enabled=True,
        video_compress_enabled=False,
    )

    called: list[str] = []

    def fake_compress(self, source, digest, video_dir):
        called.append(digest)
        return source

    monkeypatch.setattr(MediaCompressor, "compress_video", fake_compress)
    monkeypatch.setattr(
        "pipeline.media_compress.shutil.which",
        lambda _name: "/usr/bin/ffmpeg",
    )
    result = compress_static_media(settings)
    assert result.ok
    assert called == []


def test_compress_video_ffmpeg_failure(compressor: MediaCompressor, tmp_path: Path):
    source = tmp_path / "video" / "abc123.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")

    with patch(
        "media.compress.subprocess.run",
        return_value=MagicMock(returncode=1, stdout="", stderr="boom"),
    ):
        with pytest.raises(MediaCompressError, match="video h264"):
            compressor.compress_video(source, "abc123", tmp_path / "video")


def test_compress_image_to_webp(compressor: MediaCompressor, tmp_path: Path):
    source = tmp_path / "image" / "abc123.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"png")

    def fake_run(cmd, **kwargs):
        output = Path(cmd[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"compressed")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("media.compress.subprocess.run", side_effect=fake_run):
        web_path, final = compressor.compress_image(source, "abc123", tmp_path / "image")

    assert web_path == "/image/abc123.png"
    assert final == tmp_path / "image" / "abc123.png"
    assert final.exists()


def test_save_media_with_video_compressor(tmp_path: Path):
    compressor = MediaCompressor(enabled=True)

    def fake_run(cmd, **kwargs):
        output = Path(cmd[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"encoded")
        return MagicMock(returncode=0, stdout="", stderr="")

    data = b"\x00" * 8 + b"ftypmp42" + b"\x00" * 20
    with patch("media.compress.subprocess.run", side_effect=fake_run):
        web_path, final = save_media(
            data,
            "video/mp4",
            tmp_path / "image",
            tmp_path / "video",
            compressor=compressor,
        )

    assert web_path.endswith(".mp4")
    assert final.name.endswith(".mp4")


def test_compress_static_media_disabled(tmp_path: Path):
    settings = MagicMock(media_compress_enabled=False)
    result = compress_static_media(settings)
    assert result.ok
    assert "MEDIA_COMPRESS_ENABLED=false" in result.message


def test_compress_static_media_batch(tmp_path: Path, monkeypatch):
    from config import Settings

    video_dir = tmp_path / "static" / "video"
    video_dir.mkdir(parents=True)
    (video_dir / "feedface.mp4").write_bytes(b"source")

    settings = Settings(
        _env_file=None,
        hugo_root=tmp_path,
        media_compress_enabled=True,
    )

    called: list[str] = []

    def fake_compress(self, source, digest, video_dir):
        called.append(digest)
        (video_dir / f"{digest}.mp4").write_bytes(b"mp4")
        (video_dir / f"{digest}.av1.mp4").write_bytes(b"av1")
        (video_dir / f"{digest}.webm").write_bytes(b"webm")
        return video_dir / f"{digest}.mp4"

    monkeypatch.setattr(MediaCompressor, "compress_video", fake_compress)
    monkeypatch.setattr(
        "pipeline.media_compress.shutil.which",
        lambda _name: "/usr/bin/ffmpeg",
    )
    result = compress_static_media(settings)
    assert result.ok
    assert called == ["feedface"]
