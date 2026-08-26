"""Install-time project initialization: write .env. Doubao Work Agent uses repo skills/."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentKind:
    name: str
    display: str
    bins: tuple[str, ...]
    home_markers: tuple[str, ...]
    skills_link: str


AGENTS: tuple[AgentKind, ...] = (
    AgentKind(
        name="cursor",
        display="Cursor",
        bins=("cursor",),
        home_markers=(".cursor",),
        skills_link=".cursor/skills",
    ),
    AgentKind(
        name="claude",
        display="Claude Code",
        bins=("claude",),
        home_markers=(".claude",),
        skills_link=".claude/skills",
    ),
    AgentKind(
        name="trae",
        display="Trae",
        bins=("trae",),
        home_markers=(".trae",),
        skills_link=".trae/skills",
    ),
    AgentKind(
        name="opencode",
        display="OpenCode",
        bins=("opencode",),
        home_markers=(".config/opencode",),
        skills_link=".opencode/skills",
    ),
    AgentKind(
        name="codex",
        display="Codex",
        bins=("codex",),
        home_markers=(".codex",),
        skills_link=".agents/skills",
    ),
)


def detect_agents(
    *,
    which=shutil.which,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> list[AgentKind]:
    home_path = Path(home) if home is not None else Path.home()
    environ = env if env is not None else os.environ
    found: list[AgentKind] = []
    extra = _names_from_agent_bin(environ.get("AGENT_BIN", ""))
    for kind in AGENTS:
        if kind.name in extra:
            found.append(kind)
            continue
        if any(which(bin_name) for bin_name in kind.bins):
            found.append(kind)
            continue
        if any((home_path / marker).exists() for marker in kind.home_markers):
            found.append(kind)
    return found


def _names_from_agent_bin(agent_bin: str) -> set[str]:
    raw = (agent_bin or "").strip()
    if not raw:
        return set()
    name = Path(raw).name.lower()
    matched: set[str] = set()
    for kind in AGENTS:
        if name == kind.name or any(name == bin_name or name.startswith(bin_name) for bin_name in kind.bins):
            matched.add(kind.name)
    return matched


def ensure_skills_symlink(project_root: Path, skills_link: str) -> Path:
    dest = Path(project_root) / skills_link
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest)
    elif dest.exists():
        dest.unlink()
    relative = Path(os.path.relpath(Path(project_root) / "skills", dest.parent))
    dest.symlink_to(relative)
    return dest


def link_detected_agents(project_root: Path, *, agents: list[AgentKind] | None = None) -> list[AgentKind]:
    root = Path(project_root).resolve()
    skills = root / "skills"
    if not skills.is_dir():
        raise FileNotFoundError(f"找不到 {skills}")
    kinds = list(agents) if agents is not None else detect_agents()
    for kind in kinds:
        ensure_skills_symlink(root, kind.skills_link)
    return kinds


def upsert_env_file(root: Path, updates: dict[str, str]) -> Path:
    root = Path(root)
    dest = root / ".env"
    example = root / ".env.example"
    if dest.exists():
        text = dest.read_text(encoding="utf-8")
    elif example.exists():
        text = example.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"找不到 {example}，无法生成 .env")
    for key, value in updates.items():
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, text, flags=re.MULTILINE):
            text = re.sub(pattern, replacement, text, count=1, flags=re.MULTILINE)
        else:
            if not text.endswith("\n"):
                text += "\n"
            text += replacement + "\n"
    dest.write_text(text, encoding="utf-8")
    return dest


def apply_project_config(
    root: Path,
    *,
    agents: list[AgentKind] | None = None,
) -> int:
    """Ensure .env exists (from .env.example). Called by ./install.sh."""
    del agents  # 本分支专供豆包工作 Agent，不再为其它 IDE 软链 skills/
    root = Path(root).resolve()
    os.environ["BOT_ROOT"] = str(root)
    if not (root / "site" / "hugo.toml").is_file():
        print("✗ 仓库里缺少 site/hugo.toml，演示站应随代码提供，不要 hugo new site。", file=sys.stderr)
        return 1
    try:
        upsert_env_file(root, {})
    except FileNotFoundError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    print("✓ 已写入 .env（不创建飞书应用，读写走环境已登录的 lark-cli）")
    print("✓ 豆包工作 Agent 直接使用仓库 skills/，无需项目级软链。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="写入 .env（豆包工作 Agent 使用仓库 skills/）")
    parser.add_argument("--root", default="")
    args = parser.parse_args(argv)
    raw_root = (args.root or os.environ.get("BOT_ROOT") or "").strip()
    root = Path(raw_root).resolve() if raw_root else Path.cwd()
    return apply_project_config(root)


if __name__ == "__main__":
    raise SystemExit(main())
