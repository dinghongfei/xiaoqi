"""Tests for Hugo path helpers."""

from pathlib import Path

from hugo.paths import find_existing_section


def test_find_existing_section(tmp_path: Path):
    slug = "vla-robot-brain"
    path = tmp_path / "content" / "zh-cn" / "blog" / f"{slug}.md"
    path.parent.mkdir(parents=True)
    path.write_text("test", encoding="utf-8")

    assert find_existing_section(tmp_path, slug) == "blog"
    assert find_existing_section(tmp_path, "missing") is None
