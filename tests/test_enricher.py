"""Tests for enrich pipeline helpers and Enricher."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config import Settings
from feishu.client import build_enrichment_xml, value_for_metadata_table
from last_job import dump_last_job, load_last_job
from parser.doc_content import split_doc_content
from parser.message import DocRef
from parser.metadata import MetadataError
from pipeline.enricher import (
    Enricher,
    build_enrichment_markdown,
    doc_already_has_metadata,
    doc_has_image_heading,
    doc_has_images,
    extract_article_text,
    extract_feishu_doc_title,
    image_section_has_media,
    parse_metadata_json,
    prepend_enrichment_markdown,
)

SAMPLE_TABLE = """
| slug | 文件名 | demo-slug |
| lang | 语言 | zh |
| title | 标题 | 示例标题 |
| date | 时间 | 2026-07-16 |
| author | 作者 | 内容编辑 |
| categories | 分类 | 具身智能 |
| summary | 摘要 | 这是摘要 |
"""

VALID_METADATA = {
    "slug": "demo-article",
    "lang": "zh",
    "title": "演示文章",
    "date": "2026-07-16",
    "author": "内容编辑",
    "categories": "具身智能",
    "summary": "这是一段摘要",
}


def test_doc_has_images_markdown():
    assert doc_has_images("hello ![alt](token123) world")
    assert doc_has_images('<image token="tok"/>')
    assert not doc_has_images("纯文字没有图片")


def test_doc_already_has_metadata():
    raw = f"{SAMPLE_TABLE}\n---\n正文"
    assert doc_already_has_metadata(raw)
    assert not doc_already_has_metadata("只有正文没有元数据")


def test_extract_article_text_strips_media_and_tags():
    raw = "# 标题\n\n一段话 ![图](tok)\n\n<image token='x'/>\n\n[链接](https://a.com)"
    text = extract_article_text(raw)
    assert "标题" in text
    assert "一段话" in text
    assert "链接" in text
    assert "tok" not in text
    assert "<image" not in text


def test_extract_feishu_doc_title():
    assert (
        extract_feishu_doc_title("<title>世界奖励模型（WRM）</title>\n\n正文")
        == "世界奖励模型（WRM）"
    )
    assert extract_feishu_doc_title("# 只有正文") == ""


def test_parse_metadata_json_with_fence():
    data = parse_metadata_json('```json\n{"slug":"a"}\n```')
    assert data["slug"] == "a"


def test_parse_metadata_json_invalid():
    with pytest.raises(MetadataError):
        parse_metadata_json("not json")


def test_value_for_metadata_table_formats():
    assert value_for_metadata_table("lang", "zh-cn") == "zh"
    assert value_for_metadata_table("date", "2026-07-16T00:00:00+08:00") == "2026-07-16"
    assert value_for_metadata_table("categories", ["具身智能", "现实AI"]) == "具身智能，现实AI"


def test_doc_has_image_heading():
    assert doc_has_image_heading("# 图片\n\n提示词")
    assert doc_has_image_heading("<h1>图片</h1>\n<p>x</p>")
    assert not doc_has_image_heading("# 属性\n\n正文")


def test_image_section_has_media():
    assert image_section_has_media("# 图片\n\n![x](tok)\n\n# 正文")
    assert not image_section_has_media("# 图片\n\n仅有文字提示词\n\n# 正文")
    assert not image_section_has_media("正文\n\n![body](tok)\n无图片区")


def test_build_enrichment_xml_includes_table_hr_and_prompt():
    xml = build_enrichment_xml(
        {
            "slug": "demo-slug",
            "lang": "zh-cn",
            "title": "标题 A & B",
            "date": "2026-07-16T00:00:00+08:00",
            "author": "内容编辑",
            "categories": ["具身智能"],
            "summary": "摘要",
        },
        cover_prompt="蓝白科技封面，机器人剪影",
        include_image_heading=True,
    )
    assert xml.startswith("<h1>属性</h1>")
    assert "<table>" in xml
    assert "<td><p>slug</p></td>" in xml
    assert "不允许中文、空格" in xml
    assert "<td><p>zh</p></td>" in xml
    assert "A &amp; B" in xml
    assert "<h1>图片</h1>" in xml
    assert "蓝白科技封面" in xml
    assert xml.endswith("<hr/>")


def test_build_enrichment_xml_skips_image_heading_when_requested():
    xml = build_enrichment_xml(
        {
            "slug": "demo-slug",
            "lang": "zh",
            "title": "标题",
            "date": "2026-07-16",
            "author": "内容编辑",
            "categories": ["技术报告"],
            "summary": "摘要",
        },
        cover_prompt="提示词",
        include_image_heading=False,
    )
    assert "<h1>属性</h1>" in xml
    assert "<h1>图片</h1>" not in xml
    assert "<p>提示词</p>" in xml
    assert xml.endswith("<hr/>")


def test_build_enrichment_xml_no_prompt_when_images_exist():
    xml = build_enrichment_xml(
        {
            "slug": "demo-slug",
            "lang": "zh",
            "title": "标题",
            "date": "2026-07-16",
            "author": "内容编辑",
            "categories": ["技术报告"],
            "summary": "摘要",
        },
        cover_prompt=None,
    )
    assert "<h1>属性</h1>" in xml
    assert "<h1>图片</h1>" not in xml
    # 已有封面图时只写属性表，表格下方不写横线
    assert "<hr/>" not in xml


def test_inspect_ready_without_cover_image():
    client = MagicMock()
    client.fetch_doc_markdown.return_value = (
        "<title>飞书原标题</title>\n\n正文：关于机器人的文章",
        "doxcn123",
    )
    result = Enricher(client=client).inspect_doc(
        DocRef(
            kind="docx",
            token="TokenOne",
            url="https://example.feishu.cn/docx/TokenOne",
        )
    )

    assert result.status == "ready"
    assert result.doc_title == "飞书原标题"
    assert "机器人" in result.article_text
    assert result.need_cover_prompt is True
    assert result.has_image_heading is False
    blob = result.to_dict()
    assert blob["required_fields"][0] == "slug"
    assert "article_text" in blob
    assert "can_edit" in blob


def test_inspect_skips_cover_when_image_section_has_media():
    client = MagicMock()
    client.fetch_doc_markdown.return_value = (
        "# 图片\n\n![cover](img_token)\n\n正文关于机器人",
        "doxcn123",
    )
    result = Enricher(client=client).inspect_doc(DocRef(kind="docx", token="TokenOne"))

    assert result.status == "ready"
    assert result.need_cover_prompt is False
    assert result.has_image_heading is True


def test_inspect_rejects_existing_metadata():
    client = MagicMock()
    client.fetch_doc_markdown.return_value = (
        f"{SAMPLE_TABLE}\n---\n正文",
        "doxcn123",
    )
    result = Enricher(client=client).inspect_doc(DocRef(kind="docx", token="TokenOne"))

    assert result.status == "error"
    assert "已有属性信息" in result.message


def test_apply_success_without_images_writes_cover_prompt():
    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("正文：关于机器人的文章", "doxcn123")
    enricher = Enricher(client=client)

    result = enricher.apply_metadata(
        DocRef(
            kind="docx",
            token="TokenOne",
            url="https://example.feishu.cn/docx/TokenOne",
        ),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )

    assert result.status == "enriched"
    assert result.slug == "demo-article"
    assert result.doc_url == "https://example.feishu.cn/docx/TokenOne"
    assert result.cover_prompt == "封面提示词"
    client.prepend_doc_enrichment.assert_called_once()
    kwargs = client.prepend_doc_enrichment.call_args.kwargs
    assert kwargs["cover_prompt"] == "封面提示词"
    assert kwargs["document_id"] == "doxcn123"


def test_apply_surfaces_write_back_permission_error():
    from feishu.client import FeishuAPIError

    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("正文：关于机器人的文章", "doxcn123")
    client.has_doc_edit_permission.return_value = True
    client.prepend_doc_enrichment.side_effect = FeishuAPIError(
        "机器人没有该文档的编辑权限。请在飞书文档/知识库把应用机器人加为「可编辑」协作者"
    )
    result = Enricher(client=client).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )

    assert result.status == "error"
    assert "编辑权限" in result.message
    assert "已下载" in result.message
    assert result.wrote_cloud is False


def test_apply_still_writes_cover_prompt_when_body_has_images():
    client = MagicMock()
    client.fetch_doc_markdown.return_value = (
        "正文\n\n![diagram](img_token)\n更多文字",
        "doxcn123",
    )
    result = Enricher(client=client).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )

    assert result.status == "enriched"
    assert result.cover_prompt == "封面提示词"
    kwargs = client.prepend_doc_enrichment.call_args.kwargs
    assert kwargs["cover_prompt"] == "封面提示词"
    assert kwargs["include_image_heading"] is True


def test_apply_skips_cover_prompt_when_image_section_has_media():
    client = MagicMock()
    client.fetch_doc_markdown.return_value = (
        "# 图片\n\n![cover](img_token)\n\n正文关于机器人",
        "doxcn123",
    )
    result = Enricher(client=client).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        dict(VALID_METADATA),
    )

    assert result.status == "enriched"
    assert result.cover_prompt == ""
    kwargs = client.prepend_doc_enrichment.call_args.kwargs
    assert kwargs["cover_prompt"] is None
    assert kwargs["include_image_heading"] is False


def test_apply_skips_image_heading_when_already_present():
    client = MagicMock()
    client.fetch_doc_markdown.return_value = (
        "# 图片\n\n旧提示\n\n正文关于机器人",
        "doxcn123",
    )
    result = Enricher(client=client).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )

    assert result.status == "enriched"
    kwargs = client.prepend_doc_enrichment.call_args.kwargs
    assert kwargs["cover_prompt"] == "封面提示词"
    assert kwargs["include_image_heading"] is False


def test_apply_rejects_existing_metadata():
    client = MagicMock()
    client.fetch_doc_markdown.return_value = (
        f"{SAMPLE_TABLE}\n---\n正文",
        "doxcn123",
    )
    result = Enricher(client=client).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )

    assert result.status == "error"
    assert "已有属性信息" in result.message
    client.prepend_doc_enrichment.assert_not_called()


def test_apply_requires_cover_prompt_when_needed():
    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("足够长的正文内容用于补全", "doxcn123")
    result = Enricher(client=client).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        dict(VALID_METADATA),
    )

    assert result.status == "error"
    assert "cover_prompt" in result.message
    client.prepend_doc_enrichment.assert_not_called()


def test_apply_rejects_invalid_metadata():
    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("足够长的正文内容用于补全", "doxcn123")
    result = Enricher(client=client).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {"slug": "Bad Slug", "cover_prompt": "封面"},
    )

    assert result.status == "error"
    assert "元数据" in result.message or "slug" in result.message
    client.prepend_doc_enrichment.assert_not_called()


def test_build_enrichment_markdown_is_parseable():
    prefix = build_enrichment_markdown(
        dict(VALID_METADATA),
        cover_prompt="蓝白科技封面",
        include_image_heading=True,
    )
    doc = split_doc_content(prefix + "\n正文关于机器人")
    assert doc.metadata["slug"] == "demo-article"
    assert doc.metadata["lang"] == "zh-cn"
    assert "正文关于机器人" in doc.body
    assert "蓝白科技封面" in doc.metadata_region
    assert "# 属性" in prefix
    assert prefix.rstrip().endswith("---")


def test_prepend_enrichment_markdown_keeps_title():
    existing = "<title>原标题</title>\n\n正文内容足够长"
    prefix = build_enrichment_markdown(dict(VALID_METADATA))
    out = prepend_enrichment_markdown(existing, prefix)
    assert out.startswith("# 原标题\n")
    assert "<title>" not in out
    assert "| slug |" in out
    assert "正文内容足够长" in out
    assert doc_already_has_metadata(out)


def test_prepend_enrichment_markdown_keeps_first_line_h1():
    existing = "# 测试飞书云文档转换为公众号文章\n\n# 一、什么是具身智能\n\n正文\n"
    prefix = build_enrichment_markdown(dict(VALID_METADATA))
    out = prepend_enrichment_markdown(existing, prefix)
    assert out.startswith("# 测试飞书云文档转换为公众号文章\n")
    assert out.index("# 测试飞书云文档转换为公众号文章") < out.index("# 属性")
    assert out.index("# 属性") < out.index("# 一、什么是具身智能")
    doc = split_doc_content(out)
    assert "# 测试飞书云文档转换为公众号文章" in doc.metadata_region
    assert "# 一、什么是具身智能" in doc.body
    assert "# 测试飞书云文档转换为公众号文章" not in doc.body


def test_prepend_uses_raw_title_when_body_starts_with_section_h1():
    existing = "# 一、什么是具身智能\n\n正文\n"
    prefix = build_enrichment_markdown(dict(VALID_METADATA))
    out = prepend_enrichment_markdown(
        existing, prefix, doc_title="测试飞书云文档转换为公众号文章1"
    )
    assert out.startswith("# 测试飞书云文档转换为公众号文章1\n")
    assert out.index("# 测试飞书云文档转换为公众号文章1") < out.index("# 属性")
    assert out.index("# 属性") < out.index("# 一、什么是具身智能")
    doc = split_doc_content(out)
    assert "# 一、什么是具身智能" in doc.body


def _tmp_settings(tmp_path: Path) -> Settings:
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    return Settings(
        last_job_path=tmp_path / "last-job.json",
        jobs_dir=jobs,
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=tmp_path / "preview",
        state_db_path=tmp_path / "state.db",
    )


def test_apply_writes_local_only_without_edit_permission(tmp_path: Path):
    settings = _tmp_settings(tmp_path)
    work = Path(settings.jobs_dir) / "TokenOne"
    work.mkdir()
    processed = work / "processed.md"
    raw = work / "raw.md"
    processed.write_text(
        "# 一、什么是具身智能\n\n正文：关于机器人的文章\n",
        encoding="utf-8",
    )
    original_raw = "<title>测试飞书云文档转换为公众号文章1</title>\n\n# 一、什么是具身智能\n\n正文：关于机器人的文章\n"
    raw.write_text(original_raw, encoding="utf-8")
    dump_last_job(
        settings,
        {
            "token": "TokenOne",
            "document_id": "doxcn123",
            "processed_markdown_path": str(processed),
            "raw_markdown_path": str(raw),
            "metadata_warning": "元数据尚未完整",
        },
    )

    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("正文：关于机器人的文章", "doxcn123")
    client.has_doc_edit_permission.return_value = False

    result = Enricher(client=client, settings=settings).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )

    assert result.status == "enriched"
    assert result.wrote_cloud is False
    client.prepend_doc_enrichment.assert_not_called()
    assert "本地已下载文档" in result.message
    processed_text = processed.read_text(encoding="utf-8")
    raw_text = raw.read_text(encoding="utf-8")
    assert doc_already_has_metadata(processed_text)
    processed_doc = split_doc_content(processed_text)
    assert processed_doc.metadata["slug"] == "demo-article"
    assert processed_text.startswith("# 测试飞书云文档转换为公众号文章1\n")
    assert processed_text.index("# 测试飞书云文档转换为公众号文章1") < processed_text.index(
        "# 属性"
    )
    assert processed_text.index("# 属性") < processed_text.index("# 一、什么是具身智能")
    assert "# 一、什么是具身智能" in processed_doc.body
    assert raw_text == original_raw
    assert "# 属性" not in raw_text
    job = load_last_job(settings)
    assert job["slug"] == "demo-article"
    assert job["metadata_warning"] == ""


def test_apply_skips_cloud_probe_false_even_if_prepend_would_succeed(tmp_path: Path):
    settings = _tmp_settings(tmp_path)
    work = Path(settings.jobs_dir) / "TokenOne"
    work.mkdir()
    (work / "processed.md").write_text("正文：关于机器人的文章\n", encoding="utf-8")

    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("正文：关于机器人的文章", "doxcn123")
    client.has_doc_edit_permission.return_value = False

    result = Enricher(client=client, settings=settings).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )

    assert result.status == "enriched"
    client.prepend_doc_enrichment.assert_not_called()


def test_apply_permission_error_falls_back_to_local(tmp_path: Path):
    from feishu.client import FeishuAPIError

    settings = _tmp_settings(tmp_path)
    work = Path(settings.jobs_dir) / "TokenOne"
    work.mkdir()
    processed = work / "processed.md"
    processed.write_text("正文：关于机器人的文章\n", encoding="utf-8")

    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("正文：关于机器人的文章", "doxcn123")
    client.has_doc_edit_permission.return_value = True
    client.prepend_doc_enrichment.side_effect = FeishuAPIError(
        "机器人没有该文档的编辑权限。请在飞书文档/知识库把应用机器人加为「可编辑」协作者"
    )

    result = Enricher(client=client, settings=settings).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )

    assert result.status == "enriched"
    assert result.wrote_cloud is False
    assert doc_already_has_metadata(processed.read_text(encoding="utf-8"))


def test_apply_inconclusive_edit_probe_falls_back_to_local(tmp_path: Path):
    from feishu.client import FeishuAPIError

    settings = _tmp_settings(tmp_path)
    work = Path(settings.jobs_dir) / "TokenOne"
    work.mkdir()
    processed = work / "processed.md"
    processed.write_text("正文：关于机器人的文章\n", encoding="utf-8")

    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("正文：关于机器人的文章", "doxcn123")
    client.has_doc_edit_permission.return_value = None
    client.prepend_doc_enrichment.side_effect = FeishuAPIError("lark-cli 请求失败")

    result = Enricher(client=client, settings=settings).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )

    assert result.status == "enriched"
    assert result.wrote_cloud is False
    assert doc_already_has_metadata(processed.read_text(encoding="utf-8"))


def test_apply_with_permission_also_updates_local(tmp_path: Path):
    settings = _tmp_settings(tmp_path)
    work = Path(settings.jobs_dir) / "TokenOne"
    work.mkdir()
    processed = work / "processed.md"
    processed.write_text("正文：关于机器人的文章\n", encoding="utf-8")

    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("正文：关于机器人的文章", "doxcn123")
    client.has_doc_edit_permission.return_value = True

    result = Enricher(client=client, settings=settings).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )

    assert result.status == "enriched"
    assert result.wrote_cloud is True
    client.prepend_doc_enrichment.assert_called_once()
    assert doc_already_has_metadata(processed.read_text(encoding="utf-8"))


def test_inspect_rejects_local_existing_metadata(tmp_path: Path):
    settings = _tmp_settings(tmp_path)
    work = Path(settings.jobs_dir) / "TokenOne"
    work.mkdir()
    prefix = build_enrichment_markdown(dict(VALID_METADATA))
    (work / "processed.md").write_text(prefix + "\n正文关于机器人\n", encoding="utf-8")

    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("正文：关于机器人的文章", "doxcn123")

    result = Enricher(client=client, settings=settings).inspect_doc(
        DocRef(kind="docx", token="TokenOne")
    )
    assert result.status == "error"
    assert "本地已下载文档" in result.message


def test_apply_rejects_local_existing_metadata(tmp_path: Path):
    settings = _tmp_settings(tmp_path)
    work = Path(settings.jobs_dir) / "TokenOne"
    work.mkdir()
    prefix = build_enrichment_markdown(dict(VALID_METADATA))
    (work / "processed.md").write_text(prefix + "\n正文关于机器人\n", encoding="utf-8")

    client = MagicMock()
    client.fetch_doc_markdown.return_value = ("正文：关于机器人的文章", "doxcn123")

    result = Enricher(client=client, settings=settings).apply_metadata(
        DocRef(kind="docx", token="TokenOne"),
        {**VALID_METADATA, "cover_prompt": "封面提示词"},
    )
    assert result.status == "error"
    assert "本地已下载文档" in result.message
    client.prepend_doc_enrichment.assert_not_called()
