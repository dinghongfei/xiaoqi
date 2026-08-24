"""Tests for the WeChat CSS inliner."""

from wechat.inline_css import inline_css


def test_inline_css_applies_descendant_rules():
    css = """
    .wechat-article { font-size: 16px; background: #ffffff; }
    .wechat-article h2 { color: #2563EB; }
    """
    html = "<div class='wechat-article'><h2>标题</h2><p>正文</p></div>"
    out = inline_css(html, css)
    assert 'class="wechat-article"' in out or "wechat-article" in out
    assert "font-size: 16px" in out
    assert "#2563EB" in out
    assert "<style" not in out.lower()


def test_inline_style_escapes_quotes_so_attributes_stay_valid():
    css = '.wechat-article { font-family: "PingFang SC", sans-serif; }'
    html = "<div class='wechat-article'><p>正文</p></div>"
    out = inline_css(html, css)
    assert '"PingFang SC"' not in out
    assert "font-family:" in out
    assert "&quot;PingFang SC&quot;" in out or "'PingFang SC'" in out
