"""Handle im.message.receive_v1: ack immediately, then fork local Agent CLI."""

from __future__ import annotations

import logging

from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from bot.config import Settings
from bot.feishu.message import parse_message_content
from bot.feishu.reply import send_received_ack
from bot.feishu.worker import AgentWorker, MessageJob

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, settings: Settings, worker: AgentWorker):
        self.settings = settings
        self.worker = worker
        self._seen_message_ids: set[str] = set()

    def handle(self, data: P2ImMessageReceiveV1) -> None:
        event = data.event
        if not event or not event.message:
            return

        message = event.message
        message_id = message.message_id
        chat_id = message.chat_id

        if message_id and message_id in self._seen_message_ids:
            logger.info("Skip duplicate message event: %s", message_id)
            return
        if message_id:
            self._seen_message_ids.add(message_id)

        if message.message_type != "text":
            return

        text = parse_message_content(message.content or "{}")
        if message.chat_type == "group" and not (message.mentions or []):
            return
        if not text.strip():
            return

        try:
            send_received_ack(self.settings, message_id)
        except Exception:
            logger.warning("Failed to send received ack for %s", message_id)

        self.worker.enqueue(
            MessageJob(text=text, chat_id=chat_id or "", message_id=message_id or "")
        )


def create_event_handler(settings: Settings, worker: AgentWorker):
    handler = MessageHandler(settings=settings, worker=worker)

    def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
        try:
            handler.handle(data)
        except Exception:
            logger.exception("Failed to handle message event")

    return do_p2_im_message_receive_v1
