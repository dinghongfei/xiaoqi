"""Tests for media hash naming."""

from pathlib import Path

from media.hasher import content_hash, guess_extension, save_media


def test_content_hash_deterministic():
    data = b"hello world"
    assert content_hash(data) == content_hash(data)
    assert len(content_hash(data)) == 16


def test_guess_extension_png():
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    assert guess_extension("image/png", png_header) == ".png"


def test_save_media_deduplication(tmp_path: Path):
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    image_dir = tmp_path / "image"
    video_dir = tmp_path / "video"

    path1, file1 = save_media(data, "image/png", image_dir, video_dir)
    path2, file2 = save_media(data, "image/png", image_dir, video_dir)

    assert path1 == path2
    assert file1 == file2
    assert file1.exists()
    assert path1.startswith("/image/")


def test_save_media_video(tmp_path: Path):
    data = b"\x00" * 8 + b"ftypmp42" + b"\x00" * 20
    image_dir = tmp_path / "image"
    video_dir = tmp_path / "video"

    path, file_path = save_media(data, "video/mp4", image_dir, video_dir)

    assert path.startswith("/video/")
    assert path.endswith(".mp4")
    assert file_path.parent == video_dir
    assert file_path.exists()
