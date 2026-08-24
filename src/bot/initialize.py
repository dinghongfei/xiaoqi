"""Install-time project initialization: write .env, detect local agents, symlink skills/."""

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

# 与 agent_runner.which_agent 一致：飞书宿主只拉起这三项。
FEISHU_AGENT_NAMES = frozenset({"claude", "opencode", "codex"})


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


EXIT_MISSING_CREDENTIALS = 2

MISSING_CREDENTIALS = """还没有飞书应用凭证，没法完成安装。

请到 https://open.feishu.cn/app 创建「企业自建应用」，把 App ID 和 App Secret 发给我。
不要编造，也不要从别的文件夹拷贝密钥。"""


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


def read_env_value(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, raw = stripped.partition("=")
        if name.strip() != key:
            continue
        return raw.strip().strip("'\"")
    return ""


def apply_project_config(
    root: Path,
    *,
    app_id: str = "",
    app_secret: str = "",
    agents: list[AgentKind] | None = None,
) -> int:
    """Write Feishu credentials into .env and symlink skills/. Called by ./install.sh."""
    root = Path(root).resolve()
    os.environ["BOT_ROOT"] = str(root)
    env_path = root / ".env"
    app_id = (app_id or os.environ.get("FEISHU_APP_ID") or "").strip()
    app_secret = (app_secret or os.environ.get("FEISHU_APP_SECRET") or "").strip()
    if not app_id:
        app_id = read_env_value(env_path, "FEISHU_APP_ID")
    if not app_secret:
        app_secret = read_env_value(env_path, "FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        print(MISSING_CREDENTIALS, file=sys.stderr)
        return EXIT_MISSING_CREDENTIALS
    if not (root / "site" / "hugo.toml").is_file():
        print("✗ 仓库里缺少 site/hugo.toml，演示站应随代码提供，不要 hugo new site。", file=sys.stderr)
        return 1
    try:
        upsert_env_file(root, {"FEISHU_APP_ID": app_id, "FEISHU_APP_SECRET": app_secret})
    except FileNotFoundError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    print("✓ 已写入 .env（不会去读其它目录的生产密钥）")
    try:
        kinds = link_detected_agents(root, agents=agents)
    except FileNotFoundError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    if kinds:
        for kind in kinds:
            print(f"✓ {kind.display}：{kind.skills_link} → skills/")
        if not any(kind.name in FEISHU_AGENT_NAMES for kind in kinds):
            print(
                "⚠ 飞书里收消息还需要已登录的 Claude Code / OpenCode / Codex 之一；"
                "现在只链上了 IDE，本地预览仍可用。"
            )
    else:
        print("⚠ 未探测到 Cursor / Claude Code / Trae / OpenCode / Codex，跳过项目级 skills 链接。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="写入 .env 并为已装 Agent 软链 skills/")
    parser.add_argument("--root", default="")
    parser.add_argument("--app-id", default="")
    parser.add_argument("--app-secret", default="")
    args = parser.parse_args(argv)
    raw_root = (args.root or os.environ.get("BOT_ROOT") or "").strip()
    root = Path(raw_root).resolve() if raw_root else Path.cwd()
    return apply_project_config(root, app_id=args.app_id, app_secret=args.app_secret)


if __name__ == "__main__":
    raise SystemExit(main())
