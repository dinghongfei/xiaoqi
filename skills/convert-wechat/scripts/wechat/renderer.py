"""Restyle Hugo markdown into WeChat HTML plus a themable copy preview page."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

import markdown

from config import Settings
from last_job import abs_from_job, load_last_job, relpath, update_last_job
from urls import wechat_page_url
from wechat.catalog import write_wechat_catalog
from wechat.highlight import highlight_code, parse_fence_info
from wechat.themes import (
    ARTICLE_PREVIEW_CSS,
    COLORS,
    FONTS,
    SIZES,
    THEMES,
    theme_data_json,
)
from wechat.xml_styles import overlay_xml_styles

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
    r'(<aside class="wechat-video-card">.*?</aside>)\s*'
    r"(?:<p>)?(<figure\b.*?</figure>|<img\b[^>]*>)(?:</p>)?",
    re.IGNORECASE | re.DOTALL,
)


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
                f'<div class="wechat-code">'
                f'<div class="wechat-code-title">{html.escape(title)}</div>'
                f"{pre}</div>"
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
    return (
        f'\n\n<aside class="{css}">'
        f'<div class="{css}-hd">{html.escape(f"{emoji} {label}")}</div>'
        f'<div class="{css}-bd">{inner_html}</div>'
        f"{cover_html}</aside>\n\n"
    )


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
        return card[: -len("</aside>")] + media + "</aside>"

    return _VIDEO_COVER.sub(repl, body, count=1)


def restyle_markdown(
    markdown_text: str,
    *,
    site_base_url: str,
    xml_text: str = "",
) -> str:
    """Turn Hugo markdown into semantic article HTML. Styles stay in the preview page."""
    if xml_text:
        markdown_text = overlay_xml_styles(markdown_text, xml_text)
    title = _front_matter_title(markdown_text)
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
        return (
            f'<aside class="wechat-video-card">'
            f'<div class="wechat-video-card-hd">🎬 视频</div>'
            f'<div class="wechat-video-card-bd">'
            f"<p>视频不在公众号内嵌播放，请到官网查看：{html.escape(label)}</p>"
            f"</div></aside>"
        )

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


def _panel_html() -> str:
    theme_items = [(key, label) for key, label in THEMES]
    font_items = [(key, label) for key, label, _stack in FONTS]
    size_items = [(str(size), f"{size}px") for size in SIZES]
    return f"""
<aside class="wx-panel" id="style-panel">
  <section>
    <h2>主题</h2>
    {_seg_buttons("theme", theme_items)}
  </section>
  <section>
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
  <section>
    <h2>自定义色</h2>
    <label class="wx-custom">
      <input type="color" id="wx-custom-color" value="#2563EB">
      <span>自选</span>
    </label>
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
    .wx-toolbar {
      flex: none;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 16px;
      background: #fff;
      border-bottom: 1px solid #e5e7eb;
    }
    .wx-seg { display: flex; flex-wrap: wrap; gap: 8px; }
    .wx-seg button, .wx-copy {
      border: 1px solid #e5e7eb;
      background: #fff;
      color: #111827;
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
    }
    .wx-copy {
      background: #2563EB;
      border-color: #2563EB;
      color: #fff;
      font-size: 14px;
      padding: 8px 14px;
    }
    .wx-copy:disabled { opacity: 0.65; cursor: wait; }
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
    .wx-custom {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
    }
    .wx-custom input[type="color"] {
      width: 32px;
      height: 32px;
      padding: 0;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      background: #fff;
      cursor: pointer;
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
      const custom = document.getElementById("wx-custom-color");
      const LABEL = "一键复制";
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
        "border-radius", "word-break", "display", "white-space"
      ];
      const IMG_PROPS = ["max-width", "height", "display"];

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
        const preset = (data.colors || []).some(
          (c) => String(c.value).toLowerCase() === String(state.accent).toLowerCase()
        );
        if (custom) {
          custom.value = state.accent;
          const wrap = custom.closest(".wx-custom");
          if (wrap) wrap.classList.toggle("is-custom", !preset);
        }
      }

      function apply() {
        host.dataset.theme = state.theme;
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
          const props = tag === "img" ? STYLE_PROPS.concat(IMG_PROPS) : STYLE_PROPS;
          const parts = [];
          for (let p = 0; p < props.length; p++) {
            const prop = props[p];
            const val = cs.getPropertyValue(prop);
            if (!keep(prop, val)) continue;
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

      async function copyArticle() {
        btn.disabled = true;
        btn.textContent = "正在复制…";
        btn.removeAttribute("title");
        try {
          const live = host.querySelector(".wechat-article") || host;
          const clone = snapshotInline(live);
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
        const target = ev.target.closest("[data-opt]");
        if (!target) return;
        const opt = target.getAttribute("data-opt");
        const value = target.getAttribute("data-value");
        if (opt === "size") state.size = Number(value);
        else if (opt === "device" || opt === "theme" || opt === "font" || opt === "accent") {
          state[opt] = value;
        }
        apply();
      });
      if (custom) {
        custom.addEventListener("input", () => {
          state.accent = custom.value;
          apply();
        });
      }
      btn.addEventListener("click", copyArticle);
      apply();
    })();
"""


def build_preview_page(
    article_html: str,
    *,
    title: str = "公众号预览",
    slug: str = "",
) -> str:
    """Wrap article with device preview, style panel, and copy toolbar."""
    safe_title = html.escape(title)
    safe_slug = html.escape(slug)
    copy_script = _preview_script()
    chrome_css = _chrome_css()
    panel = _panel_html()
    payload = theme_data_json()
    device_seg = _seg_buttons("device", [("phone", "手机"), ("desktop", "电脑")])
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
    <header class="wx-toolbar">
      {device_seg}
      <button type="button" class="wx-copy" id="copy-btn">一键复制</button>
    </header>
    <div class="wx-body">
      <main class="wx-preview">
        <div id="wx-device" data-device="phone">
          <div id="article-html">{article_html}</div>
        </div>
      </main>
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
    source = markdown_path or abs_from_job(settings, job.get("content_path"))
    if source is None or not source.is_file():
        return WeChatResult(
            status="error",
            message="没有官网 Markdown。请先 convert-website（通常还要先 deploy-local 以便图片有可访问 URL）。",
        )

    slug = str(job.get("slug") or source.stem)
    lang = str(job.get("lang") or "zh-cn")
    text = source.read_text(encoding="utf-8")
    xml_text = ""
    xml_path = abs_from_job(settings, job.get("xml_path"))
    if xml_path is not None and xml_path.is_file():
        xml_text = xml_path.read_text(encoding="utf-8")
    article = _extract_article_div(
        restyle_markdown(
            text,
            site_base_url=settings.site_base_url,
            xml_text=xml_text,
        )
    )
    article_title = _front_matter_title(text) or slug
    page = build_preview_page(
        article,
        title=article_title,
        slug=slug,
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
