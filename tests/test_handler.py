"""Thin Feishu handler: no convert/publish state machine."""

from unittest.mock import MagicMock

from bot.feishu.handler import MessageHandler
from bot.feishu.worker import MessageJob


def _text_event(text: str, *, group: bool = False):
    message = MagicMock()
    message.message_id = "om_1"
    message.chat_id = "oc_1"
    message.message_type = "text"
    message.chat_type = "group" if group else "p2p"
    message.content = '{"text": "%s"}' % text
    message.mentions = [MagicMock()] if group else []
    if group:
        message.mentions[0].id = None
    event = MagicMock()
    event.message = message
    data = MagicMock()
    data.event = event
    return data


def test_handler_enqueues_raw_user_text(monkeypatch):
    worker = MagicMock()
    handler = MessageHandler(settings=MagicMock(), worker=worker)
    monkeypatch.setattr("bot.feishu.handler.send_received_ack", lambda *a, **k: None)
    handler.handle(_text_event("帮我看看这篇 https://x.feishu.cn/docx/TOKEN"))
    worker.enqueue.assert_called_once()
    job: MessageJob = worker.enqueue.call_args[0][0]
    assert "https://x.feishu.cn/docx/TOKEN" in job.text
    assert job.chat_id == "oc_1"
    assert job.message_id == "om_1"
    assert not hasattr(job, "mode") or not hasattr(MessageJob, "mode")
