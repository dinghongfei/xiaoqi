"""Preview theme tokens. Copy resolves these to computed px/hex in the browser."""

from __future__ import annotations

import json

FONTS: tuple[tuple[str, str, str], ...] = (
    (
        "sans",
        "无衬线",
        "-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', "
        "'Noto Sans SC', 'Microsoft YaHei', sans-serif",
    ),
    (
        "serif",
        "衬线",
        "'Songti SC', 'STSong', 'SimSun', 'Noto Serif SC', serif",
    ),
    (
        "mono",
        "等宽",
        "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Microsoft YaHei', monospace",
    ),
)

SIZES: tuple[int, ...] = (12, 14, 16, 18)

COLORS: tuple[tuple[str, str, str], ...] = (
    ("blue", "经典蓝", "#2563EB"),
    ("green", "翡翠绿", "#059669"),
    ("wechat", "微信绿", "#07C160"),
    ("pink", "樱花粉", "#E85D8C"),
    ("orange", "暖橙", "#EB6106"),
    ("red", "朱红", "#DC2626"),
    ("violet", "靛紫", "#7C3AED"),
    ("teal", "青灰", "#0F766E"),
    ("sky", "天蓝", "#0284C7"),
    ("amber", "琥珀", "#D97706"),
    ("rose", "玫红", "#E11D48"),
    ("ink", "石墨", "#374151"),
)

DEFAULTS: dict[str, str | int] = {
    "font": "sans",
    "size": 16,
    "accent": "#2563EB",
    "device": "phone",
}

ARTICLE_PREVIEW_CSS = """
#article-html {
  --wx-accent: #2563EB;
  --wx-size: 16px;
  --wx-font: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB',
    'Noto Sans SC', 'Microsoft YaHei', sans-serif;
}
#article-html .wechat-article {
  font-size: var(--wx-size);
  line-height: 1.75;
  color: #1f2937;
  background: #ffffff;
  font-family: var(--wx-font);
  word-break: break-word;
}
#article-html .wechat-article h1,
#article-html .wechat-article h2,
#article-html .wechat-article h3,
#article-html .wechat-article h4 {
  font-weight: 700;
  line-height: 1.4;
  margin: 1.4em 0 0.7em;
}
#article-html .wechat-article h1 {
  display: block;
  font-size: 1.25em;
  color: var(--wx-accent);
  background: transparent;
  padding: 0 0 8px;
  border: none;
  border-bottom: 2px solid var(--wx-accent);
}
#article-html .wechat-article h2 {
  display: block;
  font-size: 1.125em;
  color: #111827;
  background: transparent;
  border: none;
  border-left: 4px solid var(--wx-accent);
  padding: 0 0 0 10px;
}
#article-html .wechat-article h3 {
  font-size: 1em;
  color: #111827;
}
#article-html .wechat-article h4 {
  font-size: 1em;
  color: #374151;
  font-weight: 650;
}
#article-html .wechat-article .wechat-cover {
  margin: 0 0 0.4em;
}
#article-html .wechat-article .wechat-cover figure {
  margin: 0 0 8px;
}
#article-html .wechat-article .wechat-cover img {
  margin: 0 auto;
  max-width: 100%;
  height: auto;
  display: block;
}
#article-html .wechat-article .wechat-cover-hint {
  color: #6b7280;
  font-size: 0.8125em;
  line-height: 1.65;
  margin: 0;
}
#article-html .wechat-article .wechat-cover hr {
  border: none;
  border-top: 1px solid #e5e7eb;
  margin: 16px 0 8px;
}
#article-html .wechat-article .wechat-cover + h1 {
  margin-top: 0.6em;
}
#article-html .wechat-article p { margin: 0.85em 0; }
#article-html .wechat-article a { color: var(--wx-accent); text-decoration: none; }
#article-html .wechat-article strong { font-weight: 700; }
#article-html .wechat-article em { font-style: italic; }
#article-html .wechat-article u { text-decoration: underline; }
#article-html .wechat-article del {
  text-decoration: line-through;
  color: #6b7280;
}
#article-html .wechat-article img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 12px auto;
}
#article-html .wechat-article figure { margin: 16px 0; }
#article-html .wechat-article figcaption {
  color: #6b7280;
  font-size: 0.8125em;
  text-align: center;
  margin-top: 6px;
  line-height: 1.5;
}
#article-html .wechat-article ul,
#article-html .wechat-article ol {
  padding-left: 1.6em;
  margin: 0.7em 0;
}
#article-html .wechat-article li { margin: 0.35em 0; }
#article-html .wechat-article table {
  border-collapse: collapse;
  width: 100%;
  margin: 1em 0;
  font-size: 0.92em;
}
#article-html .wechat-article th,
#article-html .wechat-article td {
  border: 1px solid #e5e7eb;
  padding: 8px 10px;
  vertical-align: top;
}
#article-html .wechat-article th {
  background: #f3f4f6;
  font-weight: 600;
}
#article-html .wechat-article blockquote {
  margin: 0 0 1.25rem;
  padding: 0.875rem 1rem;
  border-left: 4px solid var(--wx-accent);
  background: #f9fafb;
  border-radius: 4px;
  color: #374151;
}
#article-html .wechat-article pre {
  margin: 1em 0;
  padding: 12px 14px;
  background: #f6f8fa;
  border-radius: 6px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8125em;
  line-height: 1.55;
  color: #1f2937;
}
#article-html .wechat-article pre code {
  font-family: inherit;
  font-size: inherit;
  background: transparent;
  padding: 0;
  white-space: inherit;
}
#article-html .wechat-article :not(pre) > code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.875em;
  background: #f3f4f6;
  padding: 0.1em 0.35em;
  border-radius: 4px;
}
#article-html .wechat-article .wechat-code {
  margin: 1em 0;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
#article-html .wechat-article .wechat-code-title {
  background: #111827;
  color: #f9fafb;
  font-size: 0.75em;
  padding: 6px 12px;
}
#article-html .wechat-article .wechat-code-title span {
  color: inherit;
  font-weight: inherit;
  font-size: inherit;
}
#article-html .wechat-article .wechat-code pre {
  margin: 0;
  border-radius: 0;
}
#article-html .wechat-article .wechat-video-card,
#article-html .wechat-article .wechat-callout {
  margin: 1em 0;
  border: 1px solid #dbeafe;
  background: #f8fafc;
  border-radius: 10px;
  overflow: hidden;
}
#article-html .wechat-article .wechat-video-card-hd,
#article-html .wechat-article .wechat-callout-hd {
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 600;
  padding: 8px 12px;
}
#article-html .wechat-article .wechat-video-card-hd span,
#article-html .wechat-article .wechat-callout-hd span,
#article-html .wechat-article .wechat-video-card-hd p,
#article-html .wechat-article .wechat-callout-hd p {
  margin: 0;
  color: inherit;
  font-weight: inherit;
  font-size: inherit;
}
#article-html .wechat-article .wechat-video-card-bd,
#article-html .wechat-article .wechat-callout-bd {
  padding: 10px 12px;
}
#article-html .wechat-article .wechat-video-card figure {
  margin: 0;
}
#article-html .wechat-article .wechat-video-card img {
  margin: 0;
}
#article-html .wechat-article .wechat-video-fallback {
  color: #4b5563;
  background: #f3f4f6;
  padding: 10px 12px;
  border-radius: 6px;
}
"""


def theme_payload() -> dict:
    return {
        "fonts": {
            key: {"label": label, "stack": stack} for key, label, stack in FONTS
        },
        "sizes": list(SIZES),
        "colors": [
            {"id": key, "label": label, "value": value}
            for key, label, value in COLORS
        ],
        "defaults": dict(DEFAULTS),
    }


def theme_data_json() -> str:
    return json.dumps(theme_payload(), ensure_ascii=False, separators=(",", ":"))
