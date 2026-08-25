"""Tests for Agent CLI adapters."""

import json
from unittest.mock import MagicMock, patch

from bot.agent_runner import (
    AgentSpec,
    build_agent_prompt,
    run_agent,
    which_agent,
)
from bot.config import Settings


def test_build_agent_prompt_mentions_skills_and_last_job():
    prompt = build_agent_prompt(
        "帮我看看这篇官网效果 https://example.feishu.cn/docx/ABC",
        chat_id="oc_1",
        message_id="om_1",
        last_job={"slug": "hello-preview"},
    )
    assert "AGENTS.md" in prompt
    assert "skills/" in prompt
    assert "scripts/run.py" in prompt
    assert "uv run python" in prompt
    assert "./install.sh" in prompt
    assert "uv run bot" not in prompt
    assert "reply-preview" in prompt
    assert "om_1" in prompt
    assert "官网预览=" in prompt
    assert "公众号预览=" in prompt
    assert "hello-preview" in prompt
    assert "oc_1" in prompt
    assert ".env.prod" in prompt
    assert "不要编造" in prompt


def test_build_agent_prompt_skips_reply_preview_without_message_id():
    prompt = build_agent_prompt("看看官网", chat_id="oc_1")
    assert "reply-preview" not in prompt
    assert "message_id" not in prompt


def test_which_agent_prefers_claude(monkeypatch):
    def fake_which(name):
        return {"claude": "/usr/bin/claude", "opencode": None, "codex": None}.get(name)

    monkeypatch.setattr("bot.agent_runner.shutil.which", fake_which)
    monkeypatch.delenv("AGENT_BIN", raising=False)
    spec = which_agent(Settings(agent_bin=""))
    assert spec is not None
    assert spec.name == "claude"
    assert spec.argv[:2] == ["/usr/bin/claude", "-p"]
    assert "--dangerously-skip-permissions" in spec.argv


def test_which_agent_opencode_auto(monkeypatch):
    monkeypatch.setattr("bot.agent_runner.shutil.which", lambda name: "/bin/opencode" if name == "opencode" else None)
    monkeypatch.delenv("AGENT_BIN", raising=False)
    spec = which_agent(Settings(agent_bin=""))
    assert spec.argv == ["/bin/opencode", "run", "--auto"]


def test_which_agent_codex_workspace_write(monkeypatch):
    monkeypatch.setattr("bot.agent_runner.shutil.which", lambda name: "/bin/codex" if name == "codex" else None)
    monkeypatch.delenv("AGENT_BIN", raising=False)
    spec = which_agent(Settings(agent_bin=""))
    assert spec.argv == ["/bin/codex", "exec", "--sandbox", "workspace-write"]


def test_run_agent_no_binary(monkeypatch, tmp_path):
    monkeypatch.setattr("bot.agent_runner.which_agent", lambda _s: None)
    result = run_agent("预览", settings=Settings(last_job_path=tmp_path / "x.json"))
    assert result.status == "error"
    assert "Claude Code" in result.message


def test_run_agent_parses_stdout(monkeypatch, tmp_path):
    spec = AgentSpec("claude", "claude", ["claude", "-p", "--dangerously-skip-permissions"])
    monkeypatch.setattr("bot.agent_runner.which_agent", lambda _s: spec)
    completed = MagicMock(
        returncode=0,
        stdout="ok\n官网预览=http://127.0.0.1:1314/blog/a/\n",
        stderr="",
    )
    with patch("bot.agent_runner.subprocess.run", return_value=completed) as run:
        result = run_agent(
            "看看官网",
            settings=Settings(agent_timeout=30, last_job_path=tmp_path / "missing.json"),
            cwd=tmp_path,
        )
    assert result.status == "ok"
    argv = run.call_args[0][0]
    assert argv[0] == "claude"
    assert argv[-1].startswith("你是本机编码助手")


def test_run_agent_flattens_json_result(monkeypatch, tmp_path):
    spec = AgentSpec("claude", "claude", ["claude", "-p"])
    monkeypatch.setattr("bot.agent_runner.which_agent", lambda _s: spec)
    payload = json.dumps({"result": "官网预览=http://127.0.0.1:1314/blog/x/\n"})
    completed = MagicMock(returncode=0, stdout=payload, stderr="")
    with patch("bot.agent_runner.subprocess.run", return_value=completed):
        result = run_agent("x", settings=Settings(agent_timeout=30))
    assert result.status == "ok"
