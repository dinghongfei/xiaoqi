"""Tests for host Agent skill linking."""

from pathlib import Path

from bot.initialize import (
    detect_agents,
    ensure_skills_symlink,
    link_detected_agents,
    AGENTS,
)


def test_detects_cursor_from_home_marker(tmp_path: Path):
    (tmp_path / ".cursor").mkdir()
    found = detect_agents(which=lambda _n: None, home=tmp_path, env={})
    assert [item.name for item in found] == ["cursor"]


def test_detects_claude_from_path():
    found = detect_agents(
        which=lambda name: "/usr/bin/claude" if name == "claude" else None,
        home=Path("/no-such-home"),
        env={},
    )
    assert [item.name for item in found] == ["claude"]


def test_detects_agent_bin_override(tmp_path: Path):
    found = detect_agents(
        which=lambda _n: None,
        home=tmp_path,
        env={"AGENT_BIN": "/opt/codex"},
    )
    assert [item.name for item in found] == ["codex"]


def test_ensure_skills_symlink_replaces_per_skill_links(tmp_path: Path):
    skills = tmp_path / "skills"
    (skills / "enrich-doc").mkdir(parents=True)
    (skills / "enrich-doc" / "SKILL.md").write_text("# enrich\n", encoding="utf-8")
    old = tmp_path / ".cursor" / "skills"
    old.mkdir(parents=True)
    (old / "enrich-doc").symlink_to(skills / "enrich-doc")

    dest = ensure_skills_symlink(tmp_path, ".cursor/skills")

    assert dest.is_symlink()
    assert dest.resolve() == skills.resolve()
    assert (dest / "enrich-doc" / "SKILL.md").is_file()


def test_link_detected_agents_writes_relative_links(tmp_path: Path):
    (tmp_path / "skills").mkdir()
    cursor = next(item for item in AGENTS if item.name == "cursor")
    linked = link_detected_agents(tmp_path, agents=[cursor])
    assert linked == [cursor]
    dest = tmp_path / ".cursor" / "skills"
    assert dest.is_symlink()
    assert dest.readlink() == Path("../skills")
