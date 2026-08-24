"""Tests for Hugo markdown writer."""

from pathlib import Path

import pytest

from hugo.writer import build_markdown, write_content_file


def test_build_markdown():
    metadata = {
        "date": "2026-02-14T10:00:00+08:00",
        "draft": False,
        "title": "Test Title",
        "categories": ["Research"],
        "author": "Author",
        "summary": "Summary text",
        "featured_image": "/image/abc123.png",
    }
    md = build_markdown(metadata, "test-slug", "## Body\n\nContent.")
    assert "translationKey = 'test-slug'" in md
    assert "title = 'Test Title'" in md
    assert "categories = ['Research']" in md
    assert "## Body" in md


def test_write_content_file(tmp_path: Path):
    metadata = {
        "date": "2026-02-14T10:00:00+08:00",
        "draft": False,
        "title": "Test",
        "author": "A",
        "summary": "S",
        "categories": ["Research"],
    }
    path = write_content_file(
        hugo_root=tmp_path,
        section="blog",
        lang="zh-cn",
        slug="my-article",
        metadata=metadata,
        body="Hello",
    )
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "translationKey = 'my-article'" in content
    assert "Hello" in content


def test_write_content_file_overwrites_existing(tmp_path: Path):
    metadata = {
        "date": "2026-02-14T10:00:00+08:00",
        "draft": False,
        "title": "Test",
    }
    write_content_file(
        hugo_root=tmp_path,
        section="blog",
        lang="en",
        slug="dup",
        metadata=metadata,
        body="First",
    )
    path = write_content_file(
        hugo_root=tmp_path,
        section="blog",
        lang="en",
        slug="dup",
        metadata=metadata,
        body="Second",
    )
    assert path.read_text(encoding="utf-8").endswith("Second\n")
