"""Tests for WeChat restyle and themable preview copy page."""

from pathlib import Path
import re

from config import Settings
from last_job import dump_last_job
from wechat.highlight import highlight_code
from wechat.renderer import convert_wechat, restyle_markdown, build_preview_page
from wechat.themes import theme_payload


SAMPLE_MD = """+++
title = '你好'
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
    video_html = html[html.find("wechat-video-card") : html.find("</aside>") + 8]
    assert "iron.png" in video_html


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
    assert [item["id"] for item in data["themes"]] == ["classic", "elegant", "simple"]
    assert set(data["fonts"]) == {"sans", "serif", "mono"}
    assert data["sizes"] == [14, 15, 16, 17, 18]
    assert any(c["value"] == "#2563EB" for c in data["colors"])
    assert data["defaults"]["accent"] == "#2563EB"


def test_preview_page_has_copy_device_and_style_panel():
    page = build_preview_page("<div class='wechat-article'><p>正文</p></div>", slug="demo")
    assert "一键复制" in page
    assert "copy-btn" in page
    assert "article-html" in page
    assert "style-panel" in page
    assert "readAsDataURL" in page
    assert "preserveCodeSpaces" in page
    assert 'querySelectorAll("img")' in page
    assert "getComputedStyle" in page
    assert "--wx-accent" in page
    assert 'data-opt="device"' in page
    assert "手机" in page
    assert "电脑" in page
    assert "经典" in page
    assert "优雅" in page
    assert "简洁" in page
    assert "无衬线" in page
    assert "主题色" in page
    assert "copy-status" not in page
    assert "不要单独复制图片" not in page
    assert "发布" not in page
    assert "探索更多主题" not in page
    assert "mdnice" not in page.lower()
    assert ".wx-body { flex-direction: column; }" not in page
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
    assert "一键复制" in page
    assert "wechat-article" in page
    assert "style-panel" in page
    assert "wx-theme-data" in page
