"""Tests for reply-preview Skill (no live Feishu)."""

from pathlib import Path
from unittest.mock import patch

from config import Settings
from pipeline.reply_preview import reply_preview


def test_reply_preview_requires_message_id():
    result = reply_preview(Settings(feishu_app_id="id", feishu_app_secret="sec"), "")
    assert not result.ok
    assert "message-id" in result.message


def test_reply_preview_requires_credentials():
    result = reply_preview(Settings(feishu_app_id="", feishu_app_secret=""), "om_1")
    assert not result.ok
    assert "FEISHU_APP_ID" in result.message


def test_reply_preview_reads_last_job_urls(tmp_path: Path):
    last_job = tmp_path / "last-job.json"
    last_job.write_text(
        '{"site_preview": "http://127.0.0.1:1314/blog/a/", '
        '"wechat_preview": "http://127.0.0.1:1314/_wechat/zh-cn/a/"}',
        encoding="utf-8",
    )
    settings = Settings(
        feishu_app_id="id",
        feishu_app_secret="sec",
        last_job_path=last_job,
    )
    with patch("pipeline.reply_preview.get_tenant_access_token", return_value="tok"):
        with patch("pipeline.reply_preview.reply_interactive") as interactive:
            result = reply_preview(settings, "om_1")
    assert result.ok
    card = interactive.call_args[0][1]
    labels = [item["text"]["content"] for item in card["elements"][1]["actions"]]
    assert labels == ["官网预览", "公众号预览"]


def test_reply_preview_falls_back_to_text(tmp_path: Path):
    from feishu.openapi import OpenAPIError

    settings = Settings(
        feishu_app_id="id",
        feishu_app_secret="sec",
        last_job_path=tmp_path / "missing.json",
    )
    with patch("pipeline.reply_preview.get_tenant_access_token", return_value="tok"):
        with patch(
            "pipeline.reply_preview.reply_interactive",
            side_effect=OpenAPIError("card failed"),
        ):
            with patch("pipeline.reply_preview.reply_text") as text_reply:
                result = reply_preview(settings, "om_1", summary="失败了")
    assert result.ok
    assert "文本" in result.message
    assert "失败了" in text_reply.call_args[0][1]
