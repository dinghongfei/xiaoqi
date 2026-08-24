"""Tests for metadata parsing."""

import pytest

from parser.doc_content import split_doc_content
from parser.metadata import MetadataError
from parser.metadata_table import parse_metadata_table


SAMPLE_METADATA_TABLE = """
| slug | 文件名 | vla-robot-brain |
| lang | 中文写zh, 英文写en | zh |
| title | 标题 | VLA 架构：机器人领域的「GPT 时刻」 |
| date | 时间，格式2026-02-14 | 2026-02-14 |
| author | 作者 | 内容编辑 |
| categories | 分类 | 具身智能，现实AI |
| summary | 摘要，100字以内 | Vision-Language-Action 模型正在成为... |
"""


def test_parse_metadata_table_valid():
    data = parse_metadata_table(SAMPLE_METADATA_TABLE)
    assert data["slug"] == "vla-robot-brain"
    assert data["lang"] == "zh-cn"
    assert data["title"] == "VLA 架构：机器人领域的「GPT 时刻」"
    assert data["date"] == "2026-02-14T00:00:00+08:00"
    assert data["categories"] == ["具身智能", "现实AI"]


def test_parse_metadata_table_missing_values():
    table = """
| slug | 文件名 | test-slug |
| lang | 语言 | en |
| title | 标题 | Test |
| date | 时间 |  |
| author | 作者 |  |
| categories | 分类 | Research |
| summary | 摘要 | Summary |
"""
    with pytest.raises(MetadataError) as exc:
        parse_metadata_table(table)
    message = str(exc.value)
    assert "元数据还差几笔才完整呢～请补上 ✏️" in message
    assert "date（时间）" in message
    assert "author（作者）" in message
    assert message.index("date（时间）") < message.index("author（作者）")
    assert "\n" in message


def test_parse_metadata_table_multiple_validation_errors():
    table = """
| slug | 文件名 | 中文标题 |
| lang | 中文写 zh，英文写 en | zh-cn |
| title | 标题 | Test |
| date | 时间 |  |
| author | 作者 | Author |
| categories | 分类 | Research |
| summary | 摘要 | Summary |
"""
    with pytest.raises(MetadataError) as exc:
        parse_metadata_table(table)
    message = str(exc.value)
    assert message.count("\n") >= 3
    assert "date（时间）" in message
    assert "slug 这个名字不太对劲" in message
    assert "语言填错啦" in message


def test_parse_metadata_table_rejects_yaml():
    with pytest.raises(MetadataError, match="三列表格"):
        parse_metadata_table("slug: test\nlang: en\ntitle: Test")


def test_parse_metadata_table_with_separator_row():
    table = """
| slug | 文件名 | test-slug |
| --- | --- | --- |
| lang | 语言 | en |
| title | 标题 | Test |
| date | 时间 | 2026-02-14 |
| author | 作者 | Author |
| categories | 分类 | A, B |
| summary | 摘要 | Summary |
"""
    data = parse_metadata_table(table)
    assert data["slug"] == "test-slug"
    assert data["categories"] == ["A", "B"]


def test_parse_metadata_table_rejects_invalid_lang():
    table = """
| slug | 文件名 | test-slug |
| lang | 中文写 zh，英文写 en | zh-cn |
| title | 标题 | Test |
| date | 时间 | 2026-02-14 |
| author | 作者 | Author |
| categories | 分类 | Research |
| summary | 摘要 | Summary |
"""
    with pytest.raises(MetadataError, match="语言填错啦.*lang（中文写 zh，英文写 en）"):
        parse_metadata_table(table)


def test_split_doc_content():
    raw = SAMPLE_METADATA_TABLE.strip() + "\n---\n\n## 正文标题\n\n段落内容。"
    doc = split_doc_content(raw)
    assert doc.metadata["slug"] == "vla-robot-brain"
    assert "## 正文标题" in doc.body
    assert "段落内容" in doc.body


def test_split_doc_content_missing_separator():
    with pytest.raises(MetadataError, match="分界线"):
        split_doc_content("| slug | x | y |\nno separator")


FEISHU_V2_EXPORT = """<title>测试飞书发布到官网 英文</title>

| slug | 文件名 | vla-robot-brain |
| lang | 语言 | en |
| title | 标题 | VLA 架构：机器人领域的「GPT 时刻」 |
| date | 时间 | 2026-02-14 |
| author | 作者 | 内容编辑 |
| categories | 分类 | Research |
| summary | 摘要 | Vision-Language-Action 模型正在成为... |

---

# 拓扑图

正文内容
"""


def test_split_doc_content_feishu_v2_export_with_title_tag():
    doc = split_doc_content(FEISHU_V2_EXPORT)
    assert doc.metadata["slug"] == "vla-robot-brain"
    assert doc.metadata["lang"] == "en"
    assert doc.metadata["categories"] == ["Research"]
    assert "# 拓扑图" in doc.body
    assert "vla-robot-brain" in doc.metadata_region


def test_split_doc_content_metadata_region_includes_embedded_image():
    raw = (
        "| slug | 文件名 | test-slug |\n"
        "| lang | 语言 | en |\n"
        "| title | 标题 | Test |\n"
        "| date | 时间 | 2026-02-14 |\n"
        "| author | 作者 | Author |\n"
        "| categories | 分类 | Research |\n"
        "| summary | 摘要 | Summary |\n"
        '<img src="CoverToken"/>\n'
        "---\n\n"
        "Body text"
    )
    doc = split_doc_content(raw)
    assert 'src="CoverToken"' in doc.metadata_region
    assert "CoverToken" not in doc.body
