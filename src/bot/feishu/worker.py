"""Serial queue: ack already sent; run local Agent CLI. Result card is a Skill."""

from __future__ import annotations

import logging
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass

from bot.agent_runner import NO_AGENT_MESSAGE, run_agent
from bot.config import BOT_ROOT, Settings

logger = logging.getLogger(__name__)

REPLY_PREVIEW_SCRIPT = BOT_ROOT / "skills" / "reply-preview" / "scripts" / "run.py"


@dataclass(frozen=True)
class MessageJob:
    text: str
    chat_id: str
    message_id: str


def _host_must_reply(result) -> bool:
    """Agent never finished orchestration, so the host sends a fallback card."""
    if result.status != "error":
        return False
    return result.message == NO_AGENT_MESSAGE or str(result.message).startswith(
        "Agent 执行超时"
    )


def send_fallback_card(message_id: str, summary: str) -> None:
    if not message_id or not REPLY_PREVIEW_SCRIPT.is_file():
        logger.warning("Cannot send fallback card (missing message_id or skill)")
        return
    cmd = [
        sys.executable,
        str(REPLY_PREVIEW_SCRIPT),
        "--message-id",
        message_id,
        "--summary",
        summary,
        "--root",
        str(BOT_ROOT),
    ]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(BOT_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception:
        logger.exception("Fallback reply-preview skill failed for %s", message_id)
        return
    if completed.returncode != 0:
        logger.warning(
            "Fallback reply-preview exited %s: %s",
            completed.returncode,
            (completed.stderr or completed.stdout or "").strip()[:300],
        )


class AgentWorker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._queue: queue.Queue[MessageJob | None] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run,
            name="bot-agent-worker",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, job: MessageJob) -> None:
        self._queue.put(job)
        logger.info(
            "Queued agent job %s (queue size ~%d)",
            job.message_id,
            self._queue.qsize(),
        )

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is None:
                    return
                try:
                    self._process(job)
                except Exception:
                    logger.exception("Worker error on job %s", job.message_id)
                    try:
                        send_fallback_card(
                            job.message_id,
                            "处理时出了点意外，请稍后再试。",
                        )
                    except Exception:
                        logger.warning("Failed to send crash reply for %s", job.message_id)
            finally:
                self._queue.task_done()

    def _process(self, job: MessageJob) -> None:
        result = run_agent(
            job.text,
            settings=self.settings,
            chat_id=job.chat_id,
            message_id=job.message_id,
        )
        if _host_must_reply(result):
            send_fallback_card(job.message_id, result.message)
