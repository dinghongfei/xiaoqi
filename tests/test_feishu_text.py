"""Tests for Feishu text unescaping."""

from parser.feishu_text import (
    normalize_categories,
    normalize_date,
    strip_heading_inline_styles,
    unescape_feishu_text,
)


def test_unescape_feishu_text():
    assert unescape_feishu_text(r"192\.168\.5\.1") == "192.168.5.1"
    assert unescape_feishu_text(r"2026\-02\-14T10:00:00\+08:00") == "2026-02-14T10:00:00+08:00"


def test_normalize_categories_from_string():
    assert normalize_categories(r"\- Research") == ["Research"]


def test_normalize_categories_from_chinese_comma():
    assert normalize_categories("具身智能，现实AI") == ["具身智能", "现实AI"]


def test_normalize_categories_from_multiple_separators():
    assert normalize_categories("A, B; C/ D| E") == ["A", "B", "C", "D", "E"]


def test_normalize_categories_from_list():
    assert normalize_categories([r"\- Research", "VLA"]) == ["Research", "VLA"]


def test_normalize_date():
    assert normalize_date(r"2026\-02\-14T10:00:00\+08:00") == "2026-02-14T10:00:00+08:00"


def test_normalize_date_from_date_only():
    assert normalize_date("2026-02-14") == "2026-02-14T00:00:00+08:00"


def test_strip_heading_inline_styles_removes_bold_italic():
    body = (
        "# **全球首个双手全掌触觉数据集**\n"
        "\n"
        "正文里保留 **加粗** 和 *斜体*。\n"
        "\n"
        "## _次级标题_\n"
        "\n"
        "### ***混合***标题\n"
        "\n"
        "#### <strong>HTML</strong>标题\n"
    )
    result = strip_heading_inline_styles(body)
    assert "# 全球首个双手全掌触觉数据集" in result
    assert "## 次级标题" in result
    assert "### 混合标题" in result
    assert "#### HTML标题" in result
    assert "正文里保留 **加粗** 和 *斜体*。" in result


def test_strip_heading_inline_styles_keeps_non_heading_lines():
    body = "不是标题 **加粗**\n# 已是干净标题\n"
    assert strip_heading_inline_styles(body) == body
