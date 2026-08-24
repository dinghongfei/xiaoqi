"""Tests for convert-website Skill (no live Feishu)."""

from pathlib import Path

from config import Settings
from last_job import dump_last_job
from pipeline.convert_website import convert_website

PROCESSED = """
| slug | 文件名 | hello-preview |
| lang | 中文写zh, 英文写en | zh |
| title | 标题 | 你好预览 |
| date | 时间 | 2026-03-01 |
| author | 作者 | 内容编辑 |
| categories | 分类 | 演示 |
| summary | 摘要 | 摘要文字 |
---

# 正文标题

## 小节

正文段落

![cover](/image/demo-cover.svg)
"""


def test_convert_website_writes_hugo_markdown(tmp_path: Path):
    hugo_root = tmp_path / "site"
    hugo_root.mkdir()
    (hugo_root / "hugo.toml").write_text("title='demo'\n", encoding="utf-8")
    processed = tmp_path / "processed.md"
    processed.write_text(PROCESSED, encoding="utf-8")
    settings = Settings(
        hugo_root=hugo_root,
        hugo_deploy_dir=tmp_path / "preview",
        last_job_path=tmp_path / "last-job.json",
        site_base_url="http://127.0.0.1:1314",
    )
    dump_last_job(
        settings,
        {"processed_markdown_path": str(processed), "section": "blog"},
    )
    result = convert_website(settings)
    assert result.status == "ok"
    assert result.slug == "hello-preview"
    assert result.lang == "zh-cn"
    path = hugo_root / "content" / "zh-cn" / "blog" / "hello-preview.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "translationKey = 'hello-preview'" in text
    assert "# 正文标题" not in text
    assert "## 小节" in text
    assert "正文段落" in text
    assert result.site_preview == "http://127.0.0.1:1314/blog/hello-preview/"


def test_prepare_hugo_body_keeps_content_h1_after_intro():
    from parser.body_format import prepare_hugo_body

    md = """开篇段落。

# 一、什么是具身智能

正文
"""
    body = prepare_hugo_body(md)
    assert "# 一、什么是具身智能" in body
    assert "开篇段落。" in body


def test_prepare_hugo_body_drops_only_first_line_title_h1():
    from parser.body_format import prepare_hugo_body

    md = """# 测试飞书云文档转换为公众号文章

# 一、什么是具身智能

正文
"""
    body = prepare_hugo_body(md)
    assert "# 测试飞书云文档转换为公众号文章" not in body
    assert "# 一、什么是具身智能" in body


def test_convert_website_requires_download(tmp_path: Path):
    settings = Settings(
        hugo_root=tmp_path / "site",
        last_job_path=tmp_path / "missing.json",
    )
    result = convert_website(settings)
    assert result.status == "error"
    assert "download-feishu-doc" in result.message


def test_prepare_hugo_body_restores_xml_styles_and_drops_title():
    from parser.body_format import prepare_hugo_body

    md = """
# 测试飞书云文档转换为公众号文章

与传统的纯软件AI不同。

大模型让AI"能思考"。

```python
print(1)
```

<callout emoji="🎬">
**视频内容**：工厂分拣
</callout>

![](/image/g1.jpg)
"""
    xml = """
    <p>与传统的<u>纯软件AI</u>不同。</p>
    <p><span text-color="rgb(216,57,49)">大模型让AI"能思考"</span></p>
    <pre caption="VLA模型推理示例" lang="python"><code>print(1)</code></pre>
    <callout emoji="🎬"><p>视频</p></callout>
    <img caption="图：宇树 G1"/>
    """
    body = prepare_hugo_body(md, xml)
    assert "# 测试飞书云文档转换为公众号文章" not in body
    assert "<u>纯软件AI</u>" in body
    assert "color: rgb(216,57,49)" in body or "color: rgb(216, 57, 49)" in body
    assert '{title="VLA模型推理示例"}' in body
    assert "{{< callout" in body
    assert 'cover="/image/g1.jpg"' in body
    assert "{{< figure" in body or "caption=" in body

