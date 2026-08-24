"""Host only sends a result card when the Agent never ran."""

from bot.agent_runner import NO_AGENT_MESSAGE, AgentRunResult
from bot.feishu.worker import _host_must_reply


def test_host_fallback_when_agent_missing():
    assert _host_must_reply(AgentRunResult(status="error", message=NO_AGENT_MESSAGE))


def test_host_fallback_when_agent_times_out():
    assert _host_must_reply(
        AgentRunResult(status="error", message="Agent 执行超时（>600s）。飞书无人值守需要预先放开权限/沙箱。")
    )


def test_host_does_not_send_card_when_agent_finished():
    assert not _host_must_reply(AgentRunResult(status="ok", message="Agent 已完成"))
    assert not _host_must_reply(AgentRunResult(status="error", message="Agent 失败：boom"))
