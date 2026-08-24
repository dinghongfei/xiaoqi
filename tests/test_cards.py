"""Tests for Feishu preview card (reply-preview Skill)."""

from feishu.card import build_preview_card, card_as_text


def test_build_preview_card_two_buttons():
    card = build_preview_card(
        site_preview="http://127.0.0.1:1314/blog/hello-preview/",
        wechat_preview="http://127.0.0.1:1314/_wechat/zh-cn/hello-preview/",
        summary="转换完成",
    )
    actions = card["elements"][1]["actions"]
    labels = [item["text"]["content"] for item in actions]
    assert labels == ["官网预览", "公众号预览"]
    assert actions[0]["url"].endswith("/blog/hello-preview/")
    assert actions[1]["url"].endswith("/_wechat/zh-cn/hello-preview/")
    assert card["header"]["title"]["content"] == "预览已就绪"


def test_card_as_text_fallback():
    text = card_as_text(
        site_preview="http://127.0.0.1:1314/blog/a/",
        wechat_preview="http://127.0.0.1:1314/_wechat/zh-cn/a/",
    )
    assert "官网预览" in text
    assert "公众号预览" in text
