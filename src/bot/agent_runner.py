"""Thin local subprocess bridge for Feishu orchestration.

Only Claude Code / OpenCode / Codex are spawned (claude → opencode → codex).
Cursor and Trae are IDE skill-discovery targets, not Feishu host CLIs.
Result cards are the reply-preview Skill.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from bot.config import BOT_ROOT, Settings
from bot.last_job import load_last_job

logger = logging.getLogger(__name__)

NO_AGENT_MESSAGE = (
    "请先安装 Claude Code、OpenCode 或 Codex，并登录。"
    "飞书机器人与 Agent CLI 必须跑在同一台机器、同一个项目根目录。"
)


@dataclass
class AgentSpec:
    name: str
    binary: str
    argv: list[str]


@dataclass
class AgentRunResult:
    status: str  # ok | error
    message: str
    stdout: str = ""
    stderr: str = ""
    argv: list[str] = field(default_factory=list)


def which_agent(settings: Settings | None = None) -> AgentSpec | None:
    """Resolve AGENT_BIN or PATH for Feishu host: claude, then opencode, then codex."""
    override = ""
    if settings is not None:
        override = (settings.agent_bin or "").strip()
    if not override:
        override = (os.environ.get("AGENT_BIN") or "").strip()

    if override:
        path = Path(override)
        name = path.name.lower()
        binary = override
        if name.startswith("claude"):
            return AgentSpec("claude", binary, _claude_argv(binary))
        if name.startswith("opencode"):
            return AgentSpec("opencode", binary, _opencode_argv(binary))
        if name.startswith("codex"):
            return AgentSpec("codex", binary, _codex_argv(binary))
        return AgentSpec("custom", binary, [binary, "-p"])

    for name, builder in (
        ("claude", _claude_argv),
        ("opencode", _opencode_argv),
        ("codex", _codex_argv),
    ):
        found = shutil.which(name)
        if found:
            return AgentSpec(name, found, builder(found))
    return None


def _claude_argv(binary: str) -> list[str]:
    return [binary, "-p", "--dangerously-skip-permissions"]


def _opencode_argv(binary: str) -> list[str]:
    return [binary, "run", "--auto"]


def _codex_argv(binary: str) -> list[str]:
    return [binary, "exec", "--sandbox", "workspace-write"]


def build_agent_prompt(
    user_text: str,
    *,
    chat_id: str = "",
    message_id: str = "",
    last_job: dict | None = None,
) -> str:
    job_blob = (
        json.dumps(last_job, ensure_ascii=False, indent=2)
        if last_job
        else "无（还没有 data/last-job.json）"
    )
    chat_line = f"当前飞书 chat_id：{chat_id}\n" if chat_id else ""
    msg_line = f"当前飞书 message_id：{message_id}\n" if message_id else ""
    reply_block = ""
    if message_id:
        reply_block = (
            "完成后必须调用 reply-preview（成功或失败都要调，这是编排最后一步）：\n"
            f"uv run python skills/reply-preview/scripts/run.py --message-id '{message_id}'\n"
            "失败时加上 --summary '中文原因'。未传 URL 时脚本会读 data/last-job.json。\n"
            "没有 message_id 时不要调用该 Skill。\n\n"
        )
    return (
        "你是本机编码助手。工作目录是飞书内容助手项目根目录。\n"
        "请阅读 AGENTS.md 与 skills/ 下各 SKILL.md，按用户需求执行 "
        "`uv run python skills/<name>/scripts/run.py`。\n"
        "安装环境不是 Skill：在项目根执行 ./install.sh（见 AGENTS.md）。\n"
        "不要自己实现 Agent 循环；不要读取其它目录的生产密钥（例如 .env.prod）；"
        "不要编造飞书/OSS 凭证；不要执行 git reset --hard。\n"
        f"{chat_line}"
        f"{msg_line}"
        f"{reply_block}"
        "上次任务产物 data/last-job.json：\n"
        f"{job_blob}\n"
        "若用户原文含飞书文档链接：必须重新执行 download-feishu-doc"
        "（同一链接也要重新拉云文档并覆盖本地稿），"
        "不要用 last-job 里的旧 processed.md 代替下载。"
        "last-job 只在用户没有给新链接时使用。"
        "没有特别说明时，官网和公众号都要转换；"
        "仅当用户明确只要官网或只要公众号时才省略另一路。"
        "公众号转换读 processed.md，不要读官网 Hugo 稿。\n\n"
        "用户原文：\n"
        f"{user_text.strip()}\n\n"
        "完成后，在最终回复中单独输出以下固定行"
        "（没有对应预览就省略该行；失败则用中文写明原因）：\n"
        "官网预览=<url>\n"
        "公众号预览=<url>\n"
    )


def _flatten_stdout(stdout: str) -> str:
    text = stdout or ""
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return text
        if isinstance(data, dict):
            for key in ("result", "message", "text", "output"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            inner = data.get("data")
            if isinstance(inner, dict):
                for key in ("result", "message", "text"):
                    value = inner.get(key)
                    if isinstance(value, str) and value.strip():
                        return value
        if isinstance(data, list):
            chunks = []
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    chunks.append(item["text"])
            if chunks:
                return "\n".join(chunks)
    return text


def run_agent(
    user_text: str,
    *,
    settings: Settings,
    chat_id: str = "",
    message_id: str = "",
    cwd: Path | None = None,
) -> AgentRunResult:
    spec = which_agent(settings)
    if spec is None:
        return AgentRunResult(status="error", message=NO_AGENT_MESSAGE)

    prompt = build_agent_prompt(
        user_text,
        chat_id=chat_id,
        message_id=message_id,
        last_job=load_last_job(settings),
    )
    argv = [*spec.argv, prompt]
    workdir = str((cwd or BOT_ROOT).resolve())
    timeout = max(int(settings.agent_timeout), 30)
    logger.info("Starting agent %s in %s (timeout=%ss)", spec.name, workdir, timeout)

    try:
        completed = subprocess.run(
            argv,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return AgentRunResult(
            status="error",
            message=NO_AGENT_MESSAGE,
            argv=argv[:-1],
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        return AgentRunResult(
            status="error",
            message=f"Agent 执行超时（>{timeout}s）。飞书无人值守需要预先放开权限/沙箱。",
            stdout=stdout,
            stderr=stderr,
            argv=argv[:-1],
        )

    stdout = _flatten_stdout(completed.stdout or "")
    stderr = completed.stderr or ""
    if completed.returncode != 0:
        detail = (stderr or stdout).strip().splitlines()
        tail = detail[-1][:300] if detail else f"退出码 {completed.returncode}"
        return AgentRunResult(
            status="error",
            message=f"Agent 失败：{tail}",
            stdout=stdout,
            stderr=stderr,
            argv=argv[:-1],
        )
    return AgentRunResult(
        status="ok",
        message="Agent 已完成",
        stdout=stdout,
        stderr=stderr,
        argv=argv[:-1],
    )
