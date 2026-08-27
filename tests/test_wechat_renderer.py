"""Tests for WeChat restyle and themable preview copy page."""

from pathlib import Path
import json
import re

from config import Settings
from last_job import dump_last_job
from wechat.highlight import highlight_code
from wechat.renderer import (
    COVER_HINT,
    convert_wechat,
    restyle_markdown,
    build_preview_page,
    wrap_list_bare_text,
)
from wechat.source import parse_processed_markdown
from wechat.themes import theme_payload


SAMPLE_MD = """+++
title = '你好'
author = '内容编辑'
summary = 'Hugo摘要'
translationKey = 'hello-preview'
+++

# 标题

{{< figure src="/image/demo-cover.svg" caption="示意图说明" >}}

{{< grid >}}
{{< column width-ratio="0.5" >}}
左栏
{{< /column >}}
{{< column width-ratio="0.5" >}}
{{< video src="/video/demo.mp4" caption="实验录像" >}}
{{< /column >}}
{{< /grid >}}

正文保持原意。
"""

SAMPLE_PROCESSED = """# 飞书文档标题

# 属性
| slug | 文件名 | hello-preview |
| lang | 中文写zh, 英文写en | zh |
| title | 标题 | 你好 |
| date | 时间 | 2026-03-01 |
| author | 作者 | 内容编辑 |
| categories | 分类 | 演示 |
| summary | 摘要 | 摘要文字 |

# 图片

封面提示词不要出现在正文

---

# 一、什么是具身智能

{{< figure src="/image/demo-cover.svg" caption="示意图说明" >}}

正文保持原意。
"""

SAMPLE_PROCESSED_COVER = SAMPLE_PROCESSED.replace(
    "封面提示词不要出现在正文",
    "![](/image/article-cover.png)",
)


def test_restyle_keeps_semantic_html_and_absolute_images():
    html = restyle_markdown(SAMPLE_MD, site_base_url="http://127.0.0.1:1314")
    assert "http://127.0.0.1:1314/image/demo-cover.svg" in html
    assert 'class="wechat-article"' in html
    assert "示意图说明" in html
    assert "视频不在公众号内嵌播放" in html
    assert "{{< grid" not in html
    assert "{{< figure" not in html
    assert "mdnice" not in html.lower()
    assert "style=" not in html
    assert "<h1" in html
    assert "标题" in html
    assert "正文保持原意" in html


def test_restyle_keeps_content_h1_when_not_front_matter_title():
    md = """+++
title = '具身智能：机器人的下一个时代'
+++

开篇段落。

# 一、什么是具身智能

正文
"""
    html = restyle_markdown(md, site_base_url="http://127.0.0.1:1314")
    assert "<h1" in html
    assert "一、什么是具身智能" in html


def test_restyle_drops_leading_h1_matching_front_matter_title():
    md = """+++
title = '测试飞书云文档转换为公众号文章'
+++

# 测试飞书云文档转换为公众号文章

# 一、什么是具身智能

正文
"""
    html = restyle_markdown(md, site_base_url="http://127.0.0.1:1314")
    assert html.count("<h1") == 1
    assert "一、什么是具身智能" in html
    assert "测试飞书云文档转换为公众号文章" not in html


def test_restyle_keeps_rich_article_formats():
    md = """+++
title = '格式'
translationKey = 'rich-preview'
+++

**具身智能**强调*身体与环境交互*，不是<u>纯软件 AI</u>，也不是~~虚拟数字人~~。

<span style="color: rgb(216, 57, 49)">大模型让 AI 能思考</span>，<span style="background-color: rgba(255, 246, 122, 0.8)">具身智能让 AI 能行动</span>。

- **感知系统**：视觉与力觉
- **运动控制**：步态规划

1. 采集环境
2. 生成规划

| 产品 | 公司 |
| --- | --- |
| Optimus | Tesla |

> 身体是认知的基础。

```python title="VLA模型推理示例"
import torch
print("ok")
```

![宇树 G1 产品图](/image/g1.jpg)

<callout emoji="🎬">
**视频内容**：工厂分拣演示
**视频时长**：2分35秒 | **分辨率**：1080P
</callout>

![小鹏 Iron 视频封面](/image/iron.png)
"""
    html = restyle_markdown(md, site_base_url="http://127.0.0.1:1314")
    assert "<strong>具身智能</strong>" in html
    assert "<em>身体与环境交互</em>" in html
    assert "<u>纯软件 AI</u>" in html
    assert "<del>虚拟数字人</del>" in html
    assert "color: rgb(216, 57, 49)" in html
    assert "background-color: rgba(255, 246, 122, 0.8)" in html
    assert "<ul>" in html and "<ol>" in html
    assert "<table>" in html and "Optimus" in html
    assert "<blockquote>" in html
    assert "wechat-code-title" in html
    assert "VLA模型推理示例" in html
    assert "style=" in html
    assert "<figcaption>宇树 G1 产品图</figcaption>" in html
    assert "wechat-video-card" in html
    assert "工厂分拣演示" in html
    assert "小鹏 Iron 视频封面" in html
    assert "<aside" not in html
    video_html = re.search(
        r'<section class="wechat-video-card">.*?</section>\s*'
        r'<section class="wechat-video-card-bd">.*?</section>.*?</section>',
        html,
        re.S,
    )
    assert video_html is not None
    assert "iron.png" in video_html.group(0)
    assert '<section class="wechat-video-card-hd">' in video_html.group(0)
    assert '<section class="wechat-code">' in html
    assert '<section class="wechat-code-title">' in html
    assert '<span style="display: inline">：视觉与力觉</span>' in html
    assert '<span style="display: inline">：步态规划</span>' in html
    assert "<p><strong>具身智能</strong>强调" in html


def test_callout_uses_section_not_aside_or_div():
    md = """+++
title = '格式'
+++

<callout emoji="✔️">
然后呢，要如何解决
</callout>
"""
    html = restyle_markdown(md, site_base_url="http://127.0.0.1:1314")
    assert "<aside" not in html
    assert '<div class="wechat-callout' not in html
    assert '<section class="wechat-callout">' in html
    assert '<section class="wechat-callout-hd"><span>' in html
    assert "然后呢，要如何解决" in html
    assert "✔️ 说明" in html


def test_wrap_list_bare_text_keeps_colon_after_bold_on_same_item():
    html = wrap_list_bare_text(
        "<ul><li><strong>感知系统</strong>：视觉、力觉、触觉、听觉</li>"
        "<li>纯文本项</li></ul>"
        "<ol><li><p><strong>采集</strong>：摄像头</p></li></ol>"
        "<p><strong>具身智能</strong>强调身体</p>"
    )
    assert "<strong>感知系统</strong>" in html
    assert '<span style="display: inline">：视觉、力觉、触觉、听觉</span>' in html
    assert '<span style="display: inline">纯文本项</span>' in html
    assert '<span style="display: inline">：摄像头</span>' in html
    assert "<p><strong>具身智能</strong>强调身体</p>" in html


def test_restyle_wraps_ordered_and_unordered_list_tails():
    md = """+++
title = '列表'
+++

- **感知系统**：视觉、力觉、触觉、听觉等多模态传感器融合
- **运动控制**：步态规划

1. **采集**：摄像头和传感器
2. 纯文本项
"""
    html = restyle_markdown(md, site_base_url="http://127.0.0.1:1314")
    assert "<strong>感知系统</strong>" in html
    assert (
        '<span style="display: inline">'
        "：视觉、力觉、触觉、听觉等多模态传感器融合</span>"
    ) in html
    assert "<strong>采集</strong>" in html
    assert '<span style="display: inline">：摄像头和传感器</span>' in html
    assert "纯文本项" in html


def test_xml_overlay_restores_color_underline_caption_and_code_title():
    md = """+++
title = '样例'
+++

与传统的纯软件AI不同，载体是真实机器人。

大模型让AI"能思考"，而具身智能让AI"能行动"。

```python
print(1)
```

![](/image/g1.jpg)
"""
    xml = """
    <p>与传统的<u>纯软件AI</u>不同，载体是真实机器人。</p>
    <p><span text-color="rgb(216,57,49)">大模型让AI"能思考"</span>，而<span background-color="rgba(255,246,122,0.8)">具身智能让AI"能行动"</span>。</p>
    <pre caption="VLA模型推理示例" lang="python"><code>print(1)</code></pre>
    <img caption="图：宇树 G1 具身智能人形机器人"/>
    """
    html = restyle_markdown(
        md,
        site_base_url="http://127.0.0.1:1314",
        xml_text=xml,
    )
    assert "<u>纯软件AI</u>" in html
    assert "color: rgb(216,57,49)" in html or "color: rgb(216, 57, 49)" in html
    assert "background-color: rgba(255,246,122,0.8)" in html or "background-color: rgba(255, 246, 122, 0.8)" in html
    assert "VLA模型推理示例" in html
    assert "宇树 G1" in html
    assert "<figcaption>" in html


def test_xml_overlay_does_not_split_rgba_with_nested_span():
    from wechat.xml_styles import converted_style_errors, overlay_xml_styles

    md = """+++
title = '样例'
+++

这里有一段高亮文字。

正文里的 206。
"""
    xml = """
    <p><span background-color="rgba(186,206,253,.7)">这里有一段高亮文字</span></p>
    <p><span text-color="rgb(36,91,219)">206</span></p>
    """
    html = restyle_markdown(
        md,
        site_base_url="http://127.0.0.1:1314",
        xml_text=xml,
    )
    assert "background-color: rgba(186,206,253,.7)" in html
    assert "rgba(186,<span" not in html
    assert converted_style_errors(overlay_xml_styles(md, xml)) == []
    assert "color: rgb(36,91,219)" in html


def test_restyle_keeps_plain_text_fence_as_pre():
    md = """+++
title = '引用'
+++

```Plain Text
@article{demo,
  year = {2026}
}
```
"""
    html = restyle_markdown(md, site_base_url="http://127.0.0.1:1314")
    assert "<pre>" in html
    assert "<code" in html
    assert "@article{demo," in html
    assert "year&nbsp;=&nbsp;{2026}" in html
    assert "Plain Text @article" not in html
    assert "</pre>" in html


def test_highlight_keeps_spaces_between_python_tokens():
    html = highlight_code("import torch\n", "python")
    plain = re.sub(r"<[^>]+>", "", html)
    assert "import&nbsp;torch" in plain


def test_theme_payload_has_first_wave_presets():
    data = theme_payload()
    assert "themes" not in data
    assert set(data["fonts"]) == {"sans", "serif", "mono"}
    assert data["sizes"] == [12, 14, 16, 18]
    assert any(c["value"] == "#2563EB" for c in data["colors"])
    assert any(c["id"] == "wechat" and c["value"] == "#07C160" for c in data["colors"])
    assert data["defaults"]["accent"] == "#2563EB"


def test_preview_page_has_copy_device_and_style_panel():
    page = build_preview_page("<div class='wechat-article'><p>正文</p></div>", slug="demo")
    assert "复制正文" in page
    assert "copy-btn" in page
    assert "article-html" in page
    assert "style-panel" in page
    assert "readAsDataURL" in page
    assert "preserveCodeSpaces" in page
    assert "flattenListEmphasis" in page
    assert "wrapListBareText" in page
    assert "rewriteWeChatBlocks" in page
    assert "replaceWithSection" in page
    assert "INLINE_TAGS" in page
    assert 'querySelectorAll("img")' in page
    assert "getComputedStyle" in page
    assert "let val = cs.getPropertyValue(prop)" in page
    assert "styleCopiedImage" in page
    assert "IMG_COPY_STYLE" in page
    assert "max-width: 100%; height: auto; display: block;" in page
    assert 'removeAttribute("width")' in page
    assert 'removeAttribute("height")' in page
    assert "IMG_PROPS" not in page
    assert "--wx-accent" in page
    assert 'data-opt="device"' in page
    assert "手机" in page
    assert "电脑" in page
    assert 'class="wx-home"' in page
    assert 'href="/"' in page
    assert "演示站点" in page
    assert "<h2>主题</h2>" not in page
    assert "优雅" not in page
    assert "简洁" not in page
    assert "自定义色" not in page
    assert "wx-custom-color" not in page
    assert "无衬线" in page
    assert "主题色" in page
    assert 'aria-label="复制标题"' in page
    assert 'aria-label="复制作者"' in page
    assert 'aria-label="复制摘要"' in page
    assert "wx-meta-copy" in page
    assert "wx-style-start" in page
    assert "复制封面图" in page
    assert 'id="copy-cover" checked' in page
    assert "wx-copy-cover" in page
    assert "wx-toolbar__right" in page
    assert 'querySelector("[data-wx-cover]")' in page
    assert "copyCoverEl.checked" in page
    assert "state.copyCover" in page
    filled = build_preview_page(
        "<div class='wechat-article'><p>正文</p></div>",
        title="示例标题",
        author="内容编辑",
        summary='摘要"测试"',
    )
    assert 'data-copy="示例标题"' in filled
    assert 'data-copy="内容编辑"' in filled
    assert "摘要&quot;测试&quot;" in filled
    assert "copy-status" not in page
    assert "不要单独复制图片" not in page
    assert "发布" not in page
    assert "探索更多主题" not in page
    assert "mdnice" not in page.lower()
    assert ".wx-body { flex-direction: column; }" not in page
    assert "wx-main" in page
    assert "overflow-y: hidden" in page
    assert "border-bottom: 2px solid var(--wx-accent)" in page
    assert "border-left: 4px solid var(--wx-accent)" in page


def test_convert_wechat_writes_preview_tree(tmp_path: Path):
    content = tmp_path / "hello-preview.md"
    content.write_text(SAMPLE_MD, encoding="utf-8")
    preview = tmp_path / "preview"
    settings = Settings(
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=preview,
        last_job_path=tmp_path / "last-job.json",
        site_base_url="http://127.0.0.1:1314",
    )
    dump_last_job(
        settings,
        {
            "slug": "hello-preview",
            "lang": "zh-cn",
            "content_path": str(content),
        },
    )
    result = convert_wechat(settings)
    assert result.status == "ok"
    assert result.wechat_preview == "http://127.0.0.1:1314/_wechat/zh-cn/hello-preview/"
    page = (preview / "_wechat" / "zh-cn" / "hello-preview" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "复制正文" in page
    assert "wechat-article" in page
    assert "style-panel" in page
    assert "wx-theme-data" in page
    catalog = preview / "_wechat" / "index.json"
    assert catalog.is_file()
    data = json.loads(catalog.read_text(encoding="utf-8"))
    article = data["articles"][0]
    assert article["title"] == "你好"
    assert article["lang"] == "zh-cn"
    assert article["slug"] == "hello-preview"
    assert article["url"] == "/_wechat/zh-cn/hello-preview/"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", article["date"])
    assert "<title>你好</title>" in page
    assert 'data-copy="你好"' in page
    assert 'data-copy="内容编辑"' in page
    assert 'data-copy="Hugo摘要"' in page


def test_convert_wechat_reads_processed_markdown(tmp_path: Path):
    processed = tmp_path / "processed.md"
    processed.write_text(SAMPLE_PROCESSED, encoding="utf-8")
    preview = tmp_path / "preview"
    settings = Settings(
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=preview,
        last_job_path=tmp_path / "last-job.json",
        site_base_url="http://127.0.0.1:1314",
    )
    dump_last_job(
        settings,
        {
            "processed_markdown_path": str(processed),
            "slug": "stale-slug",
            "lang": "en",
        },
    )
    result = convert_wechat(settings)
    assert result.status == "ok"
    assert result.wechat_preview == "http://127.0.0.1:1314/_wechat/zh-cn/hello-preview/"
    page = (preview / "_wechat" / "zh-cn" / "hello-preview" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "<title>你好</title>" in page
    assert "一、什么是具身智能" in page
    assert 'data-copy="你好"' in page
    assert 'data-copy="内容编辑"' in page
    assert 'data-copy="摘要文字"' in page
    assert "封面提示词不要出现在正文" not in page
    assert "飞书文档标题" not in page
    assert "| slug |" not in page
    assert "示意图说明" in page
    assert "正文保持原意" in page
    assert 'class="wechat-cover"' not in page
    assert COVER_HINT not in page
    assert "复制封面图" in page


def test_parse_processed_cover_from_image_section():
    parsed = parse_processed_markdown(SAMPLE_PROCESSED)
    assert parsed is not None
    assert parsed.cover_image == ""
    covered = parse_processed_markdown(SAMPLE_PROCESSED_COVER)
    assert covered is not None
    assert covered.cover_image == "/image/article-cover.png"
    figure_src = SAMPLE_PROCESSED.replace(
        "封面提示词不要出现在正文",
        '{{< figure src="/image/from-figure.png" caption="封面" >}}',
    )
    assert parse_processed_markdown(figure_src).cover_image == "/image/from-figure.png"


def test_restyle_prepends_cover_block_before_body():
    html = restyle_markdown(
        SAMPLE_MD,
        site_base_url="http://127.0.0.1:1314",
        cover_image="/image/article-cover.png",
    )
    cover_at = html.index('class="wechat-cover"')
    body_at = html.index("正文保持原意")
    assert html.index('class="wechat-article"') < cover_at < body_at
    assert "http://127.0.0.1:1314/image/article-cover.png" in html
    assert COVER_HINT in html
    assert "<hr>" in html[cover_at:body_at]
    plain = restyle_markdown(SAMPLE_MD, site_base_url="http://127.0.0.1:1314")
    assert 'class="wechat-cover"' not in plain
    assert COVER_HINT not in plain


def test_convert_wechat_includes_cover_from_processed(tmp_path: Path):
    processed = tmp_path / "processed.md"
    processed.write_text(SAMPLE_PROCESSED_COVER, encoding="utf-8")
    preview = tmp_path / "preview"
    settings = Settings(
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=preview,
        last_job_path=tmp_path / "last-job.json",
        site_base_url="http://127.0.0.1:1314",
    )
    dump_last_job(
        settings,
        {
            "processed_markdown_path": str(processed),
            "featured_image": "/image/stale-cover.png",
        },
    )
    result = convert_wechat(settings)
    assert result.status == "ok"
    page = (preview / "_wechat" / "zh-cn" / "hello-preview" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "http://127.0.0.1:1314/image/article-cover.png" in page
    assert "stale-cover.png" not in page
    assert 'class="wechat-cover"' in page
    assert COVER_HINT in page
    assert "复制封面图" in page


def test_convert_wechat_uses_job_featured_image_when_prompt_only(tmp_path: Path):
    processed = tmp_path / "processed.md"
    processed.write_text(SAMPLE_PROCESSED, encoding="utf-8")
    preview = tmp_path / "preview"
    settings = Settings(
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=preview,
        last_job_path=tmp_path / "last-job.json",
        site_base_url="http://127.0.0.1:1314",
    )
    dump_last_job(
        settings,
        {
            "processed_markdown_path": str(processed),
            "featured_image": "/image/job-cover.png",
        },
    )
    result = convert_wechat(settings)
    assert result.status == "ok"
    page = (preview / "_wechat" / "zh-cn" / "hello-preview" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "http://127.0.0.1:1314/image/job-cover.png" in page
    assert 'class="wechat-cover"' in page
    assert "封面提示词不要出现在正文" not in page


def test_convert_wechat_catalog_overwrites_same_slug(tmp_path: Path):
    preview = tmp_path / "preview"
    settings = Settings(
        hugo_root=tmp_path / "site",
        hugo_deploy_dir=preview,
        last_job_path=tmp_path / "last-job.json",
        site_base_url="http://127.0.0.1:1314",
    )
    first = tmp_path / "first.md"
    first.write_text(SAMPLE_MD, encoding="utf-8")
    dump_last_job(
        settings,
        {
            "slug": "hello-preview",
            "lang": "zh-cn",
            "content_path": str(first),
        },
    )
    assert convert_wechat(settings).status == "ok"
    second = tmp_path / "second.md"
    second.write_text(
        SAMPLE_MD.replace("title = '你好'", "title = '更新标题'"),
        encoding="utf-8",
    )
    dump_last_job(
        settings,
        {
            "slug": "hello-preview",
            "lang": "zh-cn",
            "content_path": str(second),
        },
    )
    assert convert_wechat(settings).status == "ok"
    data = json.loads(
        (preview / "_wechat" / "index.json").read_text(encoding="utf-8")
    )
    assert len(data["articles"]) == 1
    assert data["articles"][0]["title"] == "更新标题"
    assert data["articles"][0]["slug"] == "hello-preview"


def test_write_wechat_catalog_scans_existing_pages(tmp_path: Path):
    from wechat.catalog import write_wechat_catalog

    preview = tmp_path / "preview"
    chinese = preview / "_wechat" / "zh-cn" / "alpha"
    english = preview / "_wechat" / "en" / "beta"
    chinese.mkdir(parents=True)
    english.mkdir(parents=True)
    (chinese / "index.html").write_text("<title>中文稿</title>", encoding="utf-8")
    (english / "index.html").write_text("<title>English</title>", encoding="utf-8")
    write_wechat_catalog(preview)
    data = json.loads((preview / "_wechat" / "index.json").read_text(encoding="utf-8"))
    slugs = {item["slug"]: item for item in data["articles"]}
    assert slugs["alpha"]["title"] == "中文稿"
    assert slugs["alpha"]["url"] == "/_wechat/zh-cn/alpha/"
    assert slugs["beta"]["lang"] == "en"
    assert slugs["beta"]["title"] == "English"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", slugs["alpha"]["date"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", slugs["beta"]["date"])


def test_write_wechat_catalog_uses_hugo_title_not_placeholder(tmp_path: Path):
    from wechat.catalog import write_wechat_catalog

    hugo_root = tmp_path / "site"
    article = hugo_root / "content" / "zh-cn" / "blog"
    article.mkdir(parents=True)
    (article / "intelligent-robot-tech-and-products.md").write_text(
        "+++\ntitle = '智能机器人核心技术与人形产品对比'\n"
        "date = '2026-08-25T00:00:00+08:00'\n"
        "translationKey = 'intelligent-robot-tech-and-products'\n+++\n\n正文\n",
        encoding="utf-8",
    )
    preview = tmp_path / "preview"
    page_dir = preview / "_wechat" / "zh-cn" / "intelligent-robot-tech-and-products"
    page_dir.mkdir(parents=True)
    (page_dir / "index.html").write_text(
        "<title>公众号预览 · intelligent-robot-tech-and-products</title>",
        encoding="utf-8",
    )
    write_wechat_catalog(preview, hugo_root)
    data = json.loads((preview / "_wechat" / "index.json").read_text(encoding="utf-8"))
    assert len(data["articles"]) == 1
    assert data["articles"][0]["title"] == "智能机器人核心技术与人形产品对比"
    assert data["articles"][0]["date"] == "2026-08-25"
    assert "公众号预览" not in data["articles"][0]["title"]
