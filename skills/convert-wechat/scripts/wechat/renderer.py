"""Restyle Hugo markdown into WeChat HTML plus a themable copy preview page."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import markdown

from config import Settings
from last_job import abs_from_job, load_last_job, relpath, update_last_job
from urls import wechat_page_url
from wechat.catalog import write_wechat_catalog
from wechat.highlight import highlight_code, parse_fence_info
from wechat.source import fallback_hugo_field, fallback_hugo_title, parse_processed_markdown
from wechat.themes import (
    ARTICLE_PREVIEW_CSS,
    COLORS,
    FONTS,
    SIZES,
    theme_data_json,
)
from wechat.xml_styles import StyleOverlayError, overlay_xml_styles

_FRONT_MATTER = re.compile(r"^\+\+\+\n.*?\n\+\+\+\n*", re.DOTALL)
_FIGURE = re.compile(
    r'\{\{<\s*figure\s+([^>]*)>\}\}',
    re.IGNORECASE,
)
_VIDEO = re.compile(
    r'\{\{<\s*video\s+([^>]*)>\}\}',
    re.IGNORECASE,
)
_GRID_OPEN = re.compile(r"\{\{<\s*grid\s*>\}\}", re.IGNORECASE)
_GRID_CLOSE = re.compile(r"\{\{<\s*/grid\s*>\}\}", re.IGNORECASE)
_COLUMN_OPEN = re.compile(
    r'\{\{<\s*column(?:\s+[^>]*)?>\}\}',
    re.IGNORECASE,
)
_COLUMN_CLOSE = re.compile(r"\{\{<\s*/column\s*>\}\}", re.IGNORECASE)
_ATTR = re.compile(r'(\w+)="([^"]*)"')
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_HTML_SRC = re.compile(r'(src=")(/[^"]+)(")')
_FENCE = re.compile(
    r"^```[ \t]*([^\n`]*)\n(.*?)(?:\n)?^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_CALLOUT = re.compile(
    r"<callout\b([^>]*)>(.*?)</callout>",
    re.IGNORECASE | re.DOTALL,
)
_CALLOUT_SC = re.compile(
    r"\{\{<\s*callout\s+([^>]*)>\}\}(.*?)\{\{<\s*/callout\s*>\}\}",
    re.IGNORECASE | re.DOTALL,
)
_STRIKE = re.compile(r"~~(.+?)~~")
_ATX_H1_LINE = re.compile(r"^#[^#\n](.*)$")
_FRONT_MATTER_TITLE = re.compile(
    r"^title\s*=\s*(['\"])(.*)\1\s*$",
    re.MULTILINE,
)
_VIDEO_COVER = re.compile(
    r'(<section class="wechat-video-card">'
    r"\s*<section class=\"wechat-video-card-hd\">.*?</section>"
    r"\s*<section class=\"wechat-video-card-bd\">.*?</section>"
    r"\s*</section>)\s*"
    r"(?:<p>)?(<figure\b.*?</figure>|<img\b[^>]*>)(?:</p>)?",
    re.IGNORECASE | re.DOTALL,
)
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_SKIP_LIST_WRAP = frozenset({"code", "pre", "script", "style", "svg", "textarea"})
_LIST_TEXT_PARENTS = frozenset({"div", "li", "p", "section"})


class _ListBareTextWrapper(HTMLParser):
    """Wrap bare text in list items so WeChat does not turn it into a block."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.stack: list[str] = []
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._flush()
        raw = self.get_starttag_text()
        self.parts.append(raw if raw is not None else f"<{tag}>")
        if tag not in _VOID_TAGS and not (raw or "").rstrip().endswith("/>"):
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._flush()
        raw = self.get_starttag_text()
        self.parts.append(raw if raw is not None else f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        self._flush()
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.stack.pop()
            if self.stack:
                self.stack.pop()
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self._buf.append(data)

    def handle_entityref(self, name: str) -> None:
        self._buf.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._buf.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._flush()
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._flush()
        self.parts.append(f"<!{decl}>")

    def close(self) -> None:
        self._flush()
        super().close()

    def _should_wrap(self) -> bool:
        if not self.stack or any(tag in _SKIP_LIST_WRAP for tag in self.stack):
            return False
        if "li" not in self.stack:
            return False
        return self.stack[-1] in _LIST_TEXT_PARENTS

    def _flush(self) -> None:
        if not self._buf:
            return
        data = "".join(self._buf)
        self._buf.clear()
        if self._should_wrap() and data.strip():
            self.parts.append(f'<span style="display: inline">{data}</span>')
        else:
            self.parts.append(data)


def wrap_list_bare_text(html_text: str) -> str:
    """Keep list text after leading inline tags (strong/em/code) on the same line.

    WeChat's editor wraps a bare text node that follows an inline child of
    ``<li>`` in a block ``<section>``, so「**感知系统**：视觉…」breaks at the
    colon after paste. A span with a style attribute is kept.
    """
    parser = _ListBareTextWrapper()
    parser.feed(html_text)
    parser.close()
    return "".join(parser.parts)


@dataclass
class WeChatResult:
    status: str
    message: str
    html_path: str = ""
    wechat_preview: str = ""


def _attrs(blob: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _ATTR.finditer(blob)}


def _abs_url(src: str, base: str) -> str:
    src = src.strip()
    if not src:
        return src
    if src.startswith(("http://", "https://", "data:")):
        return src
    return base.rstrip("/") + "/" + src.lstrip("/")


COVER_HINT = (
    "此为封面图。复制到公众号编辑器后，请先设置封面，再手动删除本提示和横线。"
    "复制正文时若不勾选「复制封面图」，这三项都不会带上。"
)


def resolve_cover_url(meta_src: str, job_src: str, site_base_url: str) -> str:
    """Prefer a site path from metadata or last-job, then make it absolute."""
    meta = (meta_src or "").strip()
    job = (job_src or "").strip()
    if meta.startswith(("/", "http://", "https://")):
        raw = meta
    elif job.startswith(("/", "http://", "https://")):
        raw = job
    else:
        raw = meta or job
    return _abs_url(raw, site_base_url) if raw else ""


def _cover_block_html(src: str) -> str:
    if not src:
        return ""
    return (
        f'<div class="wx-cover-block" data-wx-cover="1">'
        f'<img class="wx-cover-img" src="{html.escape(src, quote=True)}" alt="封面图">'
        f'<p class="wx-cover-hint">{html.escape(COVER_HINT)}</p>'
        f'<hr class="wx-cover-rule">'
        f"</div>"
    )


def _hugo_site_title(hugo_root: Path | None) -> str:
    if hugo_root is None:
        return "演示站点"
    path = Path(hugo_root) / "hugo.toml"
    if not path.is_file():
        return "演示站点"
    match = _FRONT_MATTER_TITLE.search(path.read_text(encoding="utf-8"))
    return match.group(2).strip() if match else "演示站点"


def strip_front_matter(markdown_text: str) -> str:
    return _FRONT_MATTER.sub("", markdown_text.lstrip(), count=1)


def _front_matter_title(markdown_text: str) -> str:
    match = _FRONT_MATTER_TITLE.search(markdown_text)
    return match.group(2).strip() if match else ""


def _strip_article_title(markdown_text: str, *, title: str = "") -> str:
    """Drop a leading H1 only when it is the article title (original first line).

    Body H1s such as「# 一、…」must be kept. WeChat already has a title field.
    """
    if not markdown_text:
        return markdown_text
    lines = markdown_text.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines):
        return markdown_text
    match = _ATX_H1_LINE.match(lines[start])
    if not match:
        return markdown_text
    heading = match.group(1).strip()
    if title and heading != title:
        return markdown_text
    if not title:
        return markdown_text
    rest = lines[start + 1 :]
    while rest and not rest[0].strip():
        rest = rest[1:]
    result = "\n".join(rest)
    if markdown_text.endswith("\n") and result:
        result += "\n"
    return result


def _fence_placeholder(index: int) -> str:
    return f"WXCODEPLACEHOLDER{index}END"


def _lift_fenced_code(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Pull fenced blocks out so languages like 'Plain Text' still become <pre>."""
    blocks: list[tuple[str, str]] = []

    def repl(match: re.Match[str]) -> str:
        lang = (match.group(1) or "").strip()
        code = match.group(2).replace("\r\n", "\n").rstrip("\n")
        idx = len(blocks)
        blocks.append((lang, code))
        return f"\n\n{_fence_placeholder(idx)}\n\n"

    return _FENCE.sub(repl, text), blocks


def _lang_class(lang: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_+-]+", "", lang).lower()
    return f' class="language-{html.escape(slug, quote=True)}"' if slug else ""


def _restore_fenced_code(body: str, blocks: list[tuple[str, str]]) -> str:
    for idx, (info, code) in enumerate(blocks):
        token = _fence_placeholder(idx)
        lang, title = parse_fence_info(info)
        highlighted = highlight_code(code, lang)
        pre = (
            f"<pre><code{_lang_class(lang)}>"
            f"{highlighted}</code></pre>"
        )
        if title:
            block = (
                f'<section class="wechat-code">'
                f'<section class="wechat-code-title">'
                f"<span>{html.escape(title)}</span></section>"
                f"{pre}</section>"
            )
        else:
            block = pre
        body = body.replace(f"<p>{token}</p>", block)
        body = body.replace(token, block)
    return body


def _attr_value(attr_blob: str, name: str) -> str:
    match = re.search(
        rf'{name}=["\']([^"\']*)["\']',
        attr_blob or "",
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _wx_card(css: str, heading: str, inner_html: str, extra: str = "") -> str:
    """WeChat's editor keeps background/border on section, not aside/div."""
    return (
        f'\n\n<section class="{css}">'
        f'<section class="{css}-hd"><span>{html.escape(heading)}</span></section>'
        f'<section class="{css}-bd">{inner_html}</section>'
        f"{extra}</section>\n\n"
    )


def _callout_html(attrs: str, inner: str) -> str:
    emoji = _attr_value(attrs, "emoji") or "📌"
    cover = _attr_value(attrs, "cover")
    caption = _attr_value(attrs, "caption")
    inner_html = markdown.markdown(
        inner,
        extensions=["extra", "sane_lists", "nl2br"],
    )
    is_video = (
        emoji in {"🎬", "🎥"}
        or "视频" in inner
        or _attr_value(attrs, "video") == "true"
    )
    css = "wechat-video-card" if is_video else "wechat-callout"
    label = "视频" if is_video else "说明"
    cover_html = ""
    if cover:
        cap = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
        cover_html = (
            f'<figure><img src="{html.escape(cover, quote=True)}" '
            f'alt="{html.escape(caption)}">{cap}</figure>'
        )
    return _wx_card(css, f"{emoji} {label}", inner_html, cover_html)


def _rewrite_callouts(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return _callout_html(match.group(1), match.group(2).strip())

    text = _CALLOUT.sub(repl, text)
    return _CALLOUT_SC.sub(repl, text)


def _merge_video_covers(body: str) -> str:
    def repl(match: re.Match[str]) -> str:
        card, media = match.group(1), match.group(2)
        if "<figure" not in media and media.lower().startswith("<img"):
            media = f"<figure>{media}</figure>"
        return card[: -len("</section>")] + media + "</section>"

    return _VIDEO_COVER.sub(repl, body, count=1)


def restyle_markdown(
    markdown_text: str,
    *,
    site_base_url: str,
    xml_text: str = "",
    article_title: str = "",
) -> str:
    """Turn article markdown into semantic HTML. Styles stay in the preview page."""
    if xml_text:
        markdown_text = overlay_xml_styles(markdown_text, xml_text)
    title = article_title or _front_matter_title(markdown_text)
    text = strip_front_matter(markdown_text)
    text = _strip_article_title(text, title=title)
    text = _rewrite_callouts(text)

    def replace_figure(match: re.Match[str]) -> str:
        attrs = _attrs(match.group(1))
        src = _abs_url(attrs.get("src", ""), site_base_url)
        caption = attrs.get("caption", "")
        alt = attrs.get("alt", "") or caption
        cap_html = (
            f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
        )
        return (
            f'<figure><img src="{html.escape(src, quote=True)}" '
            f'alt="{html.escape(alt, quote=True)}">{cap_html}</figure>'
        )

    def replace_video(match: re.Match[str]) -> str:
        attrs = _attrs(match.group(1))
        src = _abs_url(attrs.get("src", ""), site_base_url)
        caption = attrs.get("caption", "")
        label = caption or src
        return _wx_card(
            "wechat-video-card",
            "🎬 视频",
            f"<p>视频不在公众号内嵌播放，请到官网查看：{html.escape(label)}</p>",
        ).strip()

    text = _FIGURE.sub(replace_figure, text)
    text = _VIDEO.sub(replace_video, text)
    text = _GRID_OPEN.sub("", text)
    text = _GRID_CLOSE.sub("", text)
    text = _COLUMN_OPEN.sub("", text)
    text = _COLUMN_CLOSE.sub("", text)

    def replace_md_image(match: re.Match[str]) -> str:
        alt, src = match.group(1), _abs_url(match.group(2), site_base_url)
        img = (
            f'<img src="{html.escape(src, quote=True)}" '
            f'alt="{html.escape(alt)}">'
        )
        if alt.strip():
            return (
                f"<figure>{img}"
                f"<figcaption>{html.escape(alt)}</figcaption></figure>"
            )
        return img

    text = _MD_IMAGE.sub(replace_md_image, text)
    text = _HTML_SRC.sub(
        lambda m: m.group(1) + _abs_url(m.group(2), site_base_url) + m.group(3),
        text,
    )

    text, code_blocks = _lift_fenced_code(text)
    text = _STRIKE.sub(r"<del>\1</del>", text)
    body = markdown.markdown(
        text,
        extensions=["extra", "sane_lists", "nl2br"],
    )
    body = _restore_fenced_code(body, code_blocks)
    body = _merge_video_covers(body)
    body = wrap_list_bare_text(body)
    return f'<div class="wechat-article">{body}</div>'


def _extract_article_div(article_html: str) -> str:
    match = re.search(
        r'(<div class="wechat-article"[^>]*>.*</div>)\s*</body>',
        article_html,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return article_html


def _seg_buttons(opt: str, items: list[tuple[str, str]]) -> str:
    bits: list[str] = []
    for value, label in items:
        bits.append(
            f'<button type="button" data-opt="{html.escape(opt)}" '
            f'data-value="{html.escape(value)}">{html.escape(label)}</button>'
        )
    return f'<div class="wx-seg">{"".join(bits)}</div>'


def _color_buttons() -> str:
    bits: list[str] = []
    for _key, label, value in COLORS:
        bits.append(
            f'<button type="button" class="wx-color" data-opt="accent" '
            f'data-value="{html.escape(value)}" title="{html.escape(label)}">'
            f'<span class="wx-color-dot" style="background:{html.escape(value)}"></span>'
            f"{html.escape(label)}</button>"
        )
    return f'<div class="wx-colors">{"".join(bits)}</div>'


_COPY_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>'
    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'
    "</svg>"
)


def _meta_item(label: str, value: str) -> str:
    raw = (value or "").strip()
    display = html.escape(raw) if raw else "（空）"
    empty = "" if raw else " is-empty"
    return (
        f'<div class="wx-meta-item">'
        f'<div class="wx-meta-head">'
        f"<h2>{html.escape(label)}</h2>"
        f'<button type="button" class="wx-meta-copy" data-copy="{html.escape(raw, quote=True)}" '
        f'aria-label="复制{html.escape(label)}" title="复制">{_COPY_ICON}</button>'
        f"</div>"
        f'<p class="wx-meta-value{empty}">{display}</p>'
        f"</div>"
    )


def _panel_html(*, title: str = "", author: str = "", summary: str = "") -> str:
    font_items = [(key, label) for key, label, _stack in FONTS]
    size_items = [(str(size), f"{size}px") for size in SIZES]
    return f"""
<aside class="wx-panel" id="style-panel">
  <section class="wx-meta">
    {_meta_item("标题", title)}
    {_meta_item("作者", author)}
    {_meta_item("摘要", summary)}
  </section>
  <section class="wx-style-start">
    <h2>字体</h2>
    {_seg_buttons("font", font_items)}
  </section>
  <section>
    <h2>字号</h2>
    {_seg_buttons("size", size_items)}
  </section>
  <section>
    <h2>主题色</h2>
    {_color_buttons()}
  </section>
</aside>
"""


def _chrome_css() -> str:
    return """
    * { box-sizing: border-box; }
    html, body { margin: 0; height: 100%; }
    body {
      background: #f3f4f6;
      color: #111827;
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
    }
    .wx-app { display: flex; flex-direction: column; height: 100%; }
    .wx-stage {
      flex: 1;
      min-width: 0;
      min-height: 0;
      display: flex;
      flex-direction: column;
    }
    .wx-toolbar {
      flex: none;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 6px 12px;
      background: #fff;
      border-bottom: 1px solid #e5e7eb;
    }
    .wx-toolbar__left {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }
    .wx-home {
      color: #111827;
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-decoration: none;
      white-space: nowrap;
    }
    .wx-home:hover { color: #111827; }
    .wx-seg { display: flex; flex-wrap: wrap; gap: 8px; }
    .wx-seg button, .wx-copy {
      border: 1px solid #e5e7eb;
      background: #fff;
      color: #111827;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
    }
    .wx-copy {
      background: #2563EB;
      border-color: #2563EB;
      color: #fff;
      font-size: 13px;
      padding: 4px 10px;
    }
    .wx-copy:disabled { opacity: 0.65; cursor: wait; }
    .wx-toolbar__right {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: none;
    }
    .wx-copy-cover {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      color: #374151;
      cursor: pointer;
      white-space: nowrap;
      user-select: none;
    }
    .wx-copy-cover input { margin: 0; }
    .wx-seg button[aria-pressed="true"] {
      border-color: #111827;
      font-weight: 600;
    }
    .wx-body { display: flex; flex-direction: row; flex: 1; min-height: 0; }
    .wx-preview {
      flex: 1;
      min-width: 0;
      min-height: 0;
      overflow-x: auto;
      overflow-y: hidden;
      display: flex;
      justify-content: center;
      align-items: stretch;
      padding: 16px;
    }
    #wx-device {
      background: #fff;
      overflow-x: hidden;
      overflow-y: auto;
      min-height: 0;
      height: 100%;
    }
    #wx-device[data-device="phone"] {
      width: 375px;
      max-width: 100%;
      border: 1px solid #e5e7eb;
      border-radius: 24px;
      padding: 20px 18px 32px;
    }
    #wx-device[data-device="desktop"] {
      width: min(720px, 100%);
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 28px 24px;
    }
    #article-html .wx-cover-block { margin: 0 0 1.25em; }
    #article-html .wx-cover-img {
      display: block;
      width: 100%;
      height: auto;
      aspect-ratio: 2.35 / 1;
      object-fit: cover;
      object-position: center;
      margin: 0;
      cursor: zoom-in;
    }
    .wx-cover-zoom {
      position: fixed;
      z-index: 80;
      display: none;
      pointer-events: none;
      padding: 8px;
      background: #fff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      box-shadow: 0 12px 40px rgba(15, 23, 42, 0.18);
    }
    .wx-cover-zoom.is-open { display: block; }
    .wx-cover-zoom img {
      display: block;
      width: auto;
      height: auto;
      max-width: min(86vw, 680px);
      max-height: min(76vh, 600px);
      object-fit: contain;
    }
    #article-html .wx-cover-hint {
      margin: 8px 0 0;
      font-size: 12px;
      line-height: 1.55;
      color: #6b7280;
    }
    #article-html .wx-cover-rule {
      margin: 12px 0 0;
      border: none;
      border-top: 1px solid #e5e7eb;
    }
    .wx-panel {
      width: 300px;
      flex: none;
      flex-shrink: 0;
      overflow: auto;
      background: #fff;
      border-left: 1px solid #e5e7eb;
      padding: 16px 16px 32px;
    }
    .wx-panel h2 {
      margin: 0 0 10px;
      font-size: 13px;
      font-weight: 600;
    }
    .wx-panel section { margin-bottom: 20px; }
    .wx-meta { display: flex; flex-direction: column; gap: 14px; }
    .wx-meta-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .wx-meta-head h2 { margin: 0; }
    .wx-meta-copy {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      padding: 0;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      background: #fff;
      color: #6b7280;
      cursor: pointer;
    }
    .wx-meta-copy:hover { color: #111827; border-color: #d1d5db; }
    .wx-meta-copy.is-copied { color: #059669; border-color: #059669; }
    .wx-meta-value {
      margin: 6px 0 0;
      font-size: 13px;
      line-height: 1.5;
      color: #374151;
      word-break: break-word;
      white-space: pre-wrap;
    }
    .wx-meta-value.is-empty { color: #9ca3af; }
    .wx-style-start {
      border-top: 1px solid #e5e7eb;
      padding-top: 20px;
    }
    .wx-colors { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .wx-color {
      display: flex;
      align-items: center;
      gap: 8px;
      border: 1px solid #e5e7eb;
      background: #fff;
      border-radius: 6px;
      padding: 6px 8px;
      cursor: pointer;
      font-size: 12px;
      text-align: left;
    }
    .wx-color[aria-pressed="true"] { border-color: #111827; font-weight: 600; }
    .wx-color-dot {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      flex: none;
      border: 1px solid rgba(0,0,0,.08);
    }
"""


def _preview_script() -> str:
    """Preview + copy JS. Plain string so braces are not eaten by the page f-string."""
    return r"""
    (function () {
      const data = JSON.parse(document.getElementById("wx-theme-data").textContent);
      const host = document.getElementById("article-html");
      const deviceEl = document.getElementById("wx-device");
      const btn = document.getElementById("copy-btn");
      const LABEL = "复制正文";
      const storageKey = "wx-preview-style-v1:" + (document.body.getAttribute("data-slug") || "default");
      const STYLE_PROPS = [
        "color", "background-color",
        "font-family", "font-size", "font-weight", "font-style", "line-height",
        "text-align", "text-decoration", "list-style-type", "list-style-position",
        "border-collapse", "vertical-align",
        "margin-top", "margin-right", "margin-bottom", "margin-left",
        "padding-top", "padding-right", "padding-bottom", "padding-left",
        "border-top-width", "border-top-style", "border-top-color",
        "border-right-width", "border-right-style", "border-right-color",
        "border-bottom-width", "border-bottom-style", "border-bottom-color",
        "border-left-width", "border-left-style", "border-left-color",
        "border-radius", "word-break", "display", "white-space",
        "overflow", "overflow-x", "overflow-y", "box-sizing"
      ];
      const INLINE_TAGS = {
        a: 1, b: 1, code: 1, del: 1, em: 1, i: 1, mark: 1, small: 1, span: 1, strong: 1, u: 1
      };

      function loadState() {
        const defaults = Object.assign({ device: "phone" }, data.defaults || {});
        try {
          const raw = localStorage.getItem(storageKey);
          if (!raw) return defaults;
          return Object.assign({}, defaults, JSON.parse(raw));
        } catch (err) {
          return defaults;
        }
      }

      const state = loadState();

      function keep(prop, value) {
        if (!value) return false;
        if (value === "normal" && prop === "font-style") return false;
        if (prop === "background-color" && (value === "rgba(0, 0, 0, 0)" || value === "transparent")) {
          return false;
        }
        if (prop.indexOf("border-") === 0 && prop.indexOf("-width") !== -1 && (value === "0px" || value === "0")) {
          return false;
        }
        if (prop.indexOf("overflow") === 0 && (value === "visible" || value === "auto")) {
          return false;
        }
        if (prop === "box-sizing" && value === "content-box") return false;
        return true;
      }

      function syncButtons() {
        document.querySelectorAll("[data-opt]").forEach((el) => {
          const opt = el.getAttribute("data-opt");
          const value = el.getAttribute("data-value");
          let current = String(state[opt]);
          if (opt === "accent") current = String(state.accent).toLowerCase();
          const selected = opt === "accent"
            ? value.toLowerCase() === current
            : value === current;
          el.setAttribute("aria-pressed", selected ? "true" : "false");
        });
      }

      function apply() {
        host.style.setProperty("--wx-accent", state.accent);
        host.style.setProperty("--wx-size", state.size + "px");
        const font = (data.fonts || {})[state.font] || (data.fonts || {}).sans;
        if (font && font.stack) host.style.setProperty("--wx-font", font.stack);
        deviceEl.dataset.device = state.device;
        syncButtons();
        try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch (err) {}
      }

      function snapshotInline(liveRoot) {
        const clone = liveRoot.cloneNode(true);
        const liveNodes = [liveRoot].concat(Array.from(liveRoot.querySelectorAll("*")));
        const cloneNodes = [clone].concat(Array.from(clone.querySelectorAll("*")));
        for (let i = 0; i < liveNodes.length; i++) {
          const live = liveNodes[i];
          const node = cloneNodes[i];
          if (!node || live.nodeType !== 1) continue;
          const cs = window.getComputedStyle(live);
          const tag = live.tagName.toLowerCase();
          const parts = [];
          for (let p = 0; p < STYLE_PROPS.length; p++) {
            const prop = STYLE_PROPS[p];
            let val = cs.getPropertyValue(prop);
            if (!keep(prop, val)) continue;
            if (prop === "display" && INLINE_TAGS[tag]) continue;
            if (prop === "font-weight" && Number(val) >= 600) val = "bold";
            if (prop.indexOf("border-") === 0 && prop.indexOf("-color") !== -1) {
              const side = prop.replace("-color", "-width");
              const width = cs.getPropertyValue(side);
              if (width === "0px" || width === "0") continue;
            }
            if (prop.indexOf("border-") === 0 && prop.indexOf("-style") !== -1) {
              const side = prop.replace("-style", "-width");
              const width = cs.getPropertyValue(side);
              if (width === "0px" || width === "0") continue;
            }
            parts.push(prop + ": " + val);
          }
          if (parts.length) node.setAttribute("style", parts.join("; "));
          node.removeAttribute("class");
          node.removeAttribute("id");
        }
        return clone;
      }

      function sizeCopiedImages(liveRoot, clone) {
        const liveImgs = liveRoot.querySelectorAll("img");
        const cloneImgs = clone.querySelectorAll("img");
        const n = Math.min(liveImgs.length, cloneImgs.length);
        for (let i = 0; i < n; i++) {
          const live = liveImgs[i];
          const node = cloneImgs[i];
          const nw = live.naturalWidth || 0;
          const nh = live.naturalHeight || 0;
          const extra = nw && nh
            ? "width: " + nw + "px; height: " + nh + "px; max-width: none"
            : "width: auto; height: auto; max-width: none";
          const prev = node.getAttribute("style") || "";
          node.setAttribute("style", prev ? prev.replace(/;?\s*$/, "") + "; " + extra : extra);
          if (nw && nh) {
            node.setAttribute("width", String(nw));
            node.setAttribute("height", String(nh));
          }
        }
      }

      function replaceWithSection(el) {
        if (!el || el.nodeType !== 1) return el;
        const tag = el.tagName.toLowerCase();
        if (tag !== "aside" && tag !== "div") return el;
        const section = document.createElement("section");
        for (let i = 0; i < el.attributes.length; i++) {
          section.setAttribute(el.attributes[i].name, el.attributes[i].value);
        }
        while (el.firstChild) section.appendChild(el.firstChild);
        if (el.parentNode) el.replaceWith(section);
        return section;
      }

      function rewriteWeChatBlocks(root) {
        const nodes = Array.from(root.querySelectorAll("aside, div"));
        for (let i = nodes.length - 1; i >= 0; i--) {
          replaceWithSection(nodes[i]);
        }
        return replaceWithSection(root);
      }

      function flattenListEmphasis(root) {
        root.querySelectorAll("li strong, li b, li em, li i").forEach((el) => {
          const span = document.createElement("span");
          const prev = el.getAttribute("style") || "";
          const tag = el.tagName.toLowerCase();
          const extra = (tag === "strong" || tag === "b") ? "font-weight: 700" : "font-style: italic";
          span.setAttribute("style", prev ? prev.replace(/;?\s*$/, "") + "; " + extra : extra);
          while (el.firstChild) span.appendChild(el.firstChild);
          el.replaceWith(span);
        });
      }

      function wrapListBareText(root) {
        function wrap(el) {
          if (el.closest("pre, code, script, style")) return;
          Array.from(el.childNodes).forEach((node) => {
            if (node.nodeType !== Node.TEXT_NODE) return;
            if (!node.nodeValue || !/[^\s]/.test(node.nodeValue)) return;
            const span = document.createElement("span");
            span.setAttribute("style", "display: inline");
            span.textContent = node.nodeValue;
            el.replaceChild(span, node);
          });
        }
        root.querySelectorAll("li").forEach((li) => {
          wrap(li);
          li.querySelectorAll("p, section, div").forEach(wrap);
        });
      }

      function preserveCodeSpaces(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        const nodes = [];
        let current;
        while ((current = walker.nextNode())) {
          if (current.parentElement && current.parentElement.closest("pre")) {
            nodes.push(current);
          }
        }
        const nbsp = "\u00a0";
        for (const node of nodes) {
          node.nodeValue = node.nodeValue
            .replace(/\t/g, nbsp + nbsp + nbsp + nbsp)
            .replace(/ /g, nbsp);
        }
      }

      function blobToDataUrl(blob) {
        return new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(reader.error || new Error("读取图片失败"));
          reader.readAsDataURL(blob);
        });
      }

      async function inlineImages(root) {
        const imgs = Array.from(root.querySelectorAll("img"));
        for (const img of imgs) {
          const src = img.getAttribute("src") || "";
          if (!src || src.indexOf("data:") === 0) continue;
          if (src.split("?")[0].toLowerCase().endsWith(".svg")) {
            throw new Error("公众号不支持 SVG 图片，请先换成 PNG 或 JPG");
          }
          const res = await fetch(src);
          if (!res.ok) throw new Error("预览图打不开，请确认本机预览还在运行");
          const blob = await res.blob();
          const type = (blob.type || "").toLowerCase();
          if (type.indexOf("svg") !== -1) {
            throw new Error("公众号不支持 SVG 图片，请先换成 PNG 或 JPG");
          }
          img.setAttribute("src", await blobToDataUrl(blob));
        }
      }

      async function writeClipboard(html, text) {
        if (navigator.clipboard && window.ClipboardItem) {
          await navigator.clipboard.write([
            new ClipboardItem({
              "text/html": new Blob([html], { type: "text/html" }),
              "text/plain": new Blob([text], { type: "text/plain" })
            })
          ]);
          return;
        }
        const holder = document.createElement("div");
        holder.contentEditable = "true";
        holder.style.cssText = "position:fixed;left:-9999px;top:0;";
        holder.innerHTML = html;
        document.body.appendChild(holder);
        const range = document.createRange();
        range.selectNodeContents(holder);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        const ok = document.execCommand("copy");
        sel.removeAllRanges();
        holder.remove();
        if (!ok) throw new Error("当前浏览器不允许写入剪贴板");
      }

      function copyRoot() {
        const coverBox = document.getElementById("copy-cover");
        if (coverBox && coverBox.checked) return host;
        return host.querySelector(".wechat-article") || host;
      }

      async function copyArticle() {
        btn.disabled = true;
        btn.textContent = "正在复制…";
        btn.removeAttribute("title");
        try {
          const live = copyRoot();
          const clone = rewriteWeChatBlocks(snapshotInline(live));
          sizeCopiedImages(live, clone);
          flattenListEmphasis(clone);
          wrapListBareText(clone);
          preserveCodeSpaces(clone);
          await inlineImages(clone);
          await writeClipboard(clone.outerHTML, live.innerText);
          btn.textContent = "已复制";
          setTimeout(() => {
            if (btn.textContent === "已复制") btn.textContent = LABEL;
          }, 1600);
        } catch (err) {
          const msg = err && err.message ? err.message : "请检查预览图是否还能打开";
          btn.textContent = "复制失败";
          btn.title = msg;
        } finally {
          btn.disabled = false;
        }
      }

      document.addEventListener("click", (ev) => {
        const metaBtn = ev.target.closest(".wx-meta-copy");
        if (metaBtn) {
          const text = metaBtn.getAttribute("data-copy") || "";
          const mark = () => {
            metaBtn.classList.add("is-copied");
            metaBtn.title = "已复制";
            setTimeout(() => {
              metaBtn.classList.remove("is-copied");
              metaBtn.title = "复制";
            }, 1200);
          };
          const fail = (err) => {
            const msg = err && err.message ? err.message : "复制失败";
            metaBtn.title = msg;
          };
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(mark).catch(fail);
          } else {
            writeClipboard(text, text).then(mark).catch(fail);
          }
          return;
        }
        const target = ev.target.closest("[data-opt]");
        if (!target) return;
        const opt = target.getAttribute("data-opt");
        const value = target.getAttribute("data-value");
        if (opt === "size") state.size = Number(value);
        else if (opt === "device" || opt === "font" || opt === "accent") {
          state[opt] = value;
        }
        apply();
      });
      function bindCoverZoom() {
        const img = host.querySelector(".wx-cover-img");
        if (!img) return;
        const pop = document.createElement("div");
        pop.className = "wx-cover-zoom";
        pop.setAttribute("aria-hidden", "true");
        const full = document.createElement("img");
        full.alt = "封面图完整预览";
        pop.appendChild(full);
        document.body.appendChild(pop);

        let lastEv = null;

        function hide() {
          pop.classList.remove("is-open");
        }

        function place(ev) {
          lastEv = ev;
          const pad = 16;
          const rect = pop.getBoundingClientRect();
          let x = ev.clientX + 18;
          let y = ev.clientY + 18;
          const w = rect.width || 240;
          const h = rect.height || 160;
          if (x + w > window.innerWidth - pad) x = ev.clientX - w - 12;
          if (y + h > window.innerHeight - pad) y = window.innerHeight - h - pad;
          if (x < pad) x = pad;
          if (y < pad) y = pad;
          pop.style.left = x + "px";
          pop.style.top = y + "px";
        }

        full.addEventListener("load", () => {
          if (pop.classList.contains("is-open") && lastEv) place(lastEv);
        });

        img.addEventListener("mouseenter", (ev) => {
          full.src = img.currentSrc || img.getAttribute("src") || "";
          pop.classList.add("is-open");
          place(ev);
        });
        img.addEventListener("mousemove", place);
        img.addEventListener("mouseleave", hide);
        deviceEl.addEventListener("scroll", hide, { passive: true });
        window.addEventListener("blur", hide);
      }

      bindCoverZoom();
      btn.addEventListener("click", copyArticle);
      apply();
    })();
"""


def build_preview_page(
    article_html: str,
    *,
    title: str = "公众号预览",
    slug: str = "",
    author: str = "",
    summary: str = "",
    home_label: str = "演示站点",
    cover_image: str = "",
) -> str:
    """Wrap article with device preview, style panel, and copy toolbar."""
    safe_title = html.escape(title)
    safe_slug = html.escape(slug)
    safe_home = html.escape(home_label or "演示站点")
    copy_script = _preview_script()
    chrome_css = _chrome_css()
    panel = _panel_html(title=title, author=author, summary=summary)
    payload = theme_data_json()
    device_seg = _seg_buttons("device", [("phone", "手机"), ("desktop", "电脑")])
    cover_html = _cover_block_html(cover_image)
    cover_toggle = ""
    if cover_image:
        cover_toggle = (
            '<label class="wx-copy-cover" for="copy-cover">'
            '<input type="checkbox" id="copy-cover" checked> 复制封面图</label>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
{chrome_css}
{ARTICLE_PREVIEW_CSS}
  </style>
</head>
<body data-slug="{safe_slug}">
  <div class="wx-app">
    <div class="wx-body">
      <div class="wx-stage">
        <header class="wx-toolbar">
          <div class="wx-toolbar__left">
            <a class="wx-home" href="/">{safe_home}</a>
            {device_seg}
          </div>
          <div class="wx-toolbar__right">
            {cover_toggle}
            <button type="button" class="wx-copy" id="copy-btn">复制正文</button>
          </div>
        </header>
        <main class="wx-preview">
          <div id="wx-device" data-device="phone">
            <div id="article-html">{cover_html}{article_html}</div>
          </div>
        </main>
      </div>
      {panel}
    </div>
  </div>
  <script type="application/json" id="wx-theme-data">{payload}</script>
  <script>
{copy_script}
  </script>
</body>
</html>
"""


def convert_wechat(
    settings: Settings,
    *,
    markdown_path: Path | None = None,
) -> WeChatResult:
    job = load_last_job(settings) or {}
    source = markdown_path or abs_from_job(
        settings,
        job.get("processed_markdown_path") or job.get("content_path"),
    )
    if source is None or not source.is_file():
        return WeChatResult(
            status="error",
            message="没有可转换的 processed.md。请先 download-feishu-doc（通常还要 deploy-local 以便图片有可访问 URL）。",
        )

    text = source.read_text(encoding="utf-8")
    parsed = parse_processed_markdown(text)
    if parsed is not None:
        body = parsed.body
        slug = parsed.slug or str(job.get("slug") or source.stem)
        lang = parsed.lang or str(job.get("lang") or "zh-cn")
        article_title = parsed.title or fallback_hugo_title(text) or slug
        author = parsed.author
        summary = parsed.summary
    else:
        body = text
        slug = str(job.get("slug") or source.stem)
        lang = str(job.get("lang") or "zh-cn")
        article_title = fallback_hugo_title(text) or _front_matter_title(text) or slug
        author = fallback_hugo_field(text, "author")
        summary = fallback_hugo_field(text, "summary")

    xml_text = ""
    xml_path = abs_from_job(settings, job.get("xml_path"))
    if xml_path is not None and xml_path.is_file():
        xml_text = xml_path.read_text(encoding="utf-8")
    cover_image = resolve_cover_url(
        parsed.featured_image if parsed is not None else "",
        str(job.get("featured_image") or ""),
        settings.site_base_url,
    )
    try:
        article = _extract_article_div(
            restyle_markdown(
                body,
                site_base_url=settings.site_base_url,
                xml_text=xml_text,
                article_title=article_title,
            )
        )
    except StyleOverlayError as exc:
        return WeChatResult(status="error", message=f"❌ {exc}")
    page = build_preview_page(
        article,
        title=article_title,
        slug=slug,
        author=author,
        summary=summary,
        home_label=_hugo_site_title(settings.hugo_root),
        cover_image=cover_image,
    )

    out_dir = settings.preview_dir / "_wechat" / lang / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(page, encoding="utf-8")
    write_wechat_catalog(settings.preview_dir, settings.hugo_root)

    preview = wechat_page_url(settings.site_base_url, lang, slug)
    rel = relpath(out_path)
    update_last_job(settings, wechat_preview=preview)
    return WeChatResult(
        status="ok",
        message=f"公众号预览已生成 {rel}",
        html_path=rel,
        wechat_preview=preview,
    )
