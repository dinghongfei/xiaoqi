"""Feishu long-connection entry (thin adapter, no Skill orchestration)."""

from __future__ import annotations

import logging
import sys

import lark_oapi as lark

from bot.config import (
    SettingsError,
    get_settings,
    require_feishu_settings,
    resolve_env_file,
)
from bot.feishu.handler import create_event_handler
from bot.feishu.worker import AgentWorker

logger = logging.getLogger(__name__)


def _create_runtime(settings):
    require_feishu_settings(settings)
    worker = AgentWorker(settings=settings)
    return create_event_handler(settings, worker)


def _build_event_handler(settings, event_handler):
    def _ignore_message_read(_data) -> None:
        pass

    return (
        lark.EventDispatcherHandler.builder(
            settings.feishu_encrypt_key,
            settings.feishu_verification_token,
            lark.LogLevel.INFO,
        )
        .register_p2_im_message_receive_v1(event_handler)
        .register_p2_im_message_message_read_v1(_ignore_message_read)
        .build()
    )


def run_serve(env_file: str | None = None) -> None:
    path = resolve_env_file(env_file)
    settings = get_settings(path)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        require_feishu_settings(settings)
    except SettingsError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    event_handler = _create_runtime(settings)
    handler = _build_event_handler(settings, event_handler)
    ws_client = lark.ws.Client(
        settings.feishu_app_id,
        settings.feishu_app_secret,
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
    )
    logger.info("Starting bot (WebSocket)…")
    logger.info("Preview dir: %s", settings.preview_dir)
    ws_client.start()


if __name__ == "__main__":
    run_serve()
