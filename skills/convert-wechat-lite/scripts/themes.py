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
    "style": "classic",
    "font": "sans",
    "size": 16,
    "accent": "#2563EB",
    "device": "phone",
}

# id, name, description, default accent, default font
STYLE_THEMES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "classic",
        "简约通用",
        "白底线饰、左侧细条，适合大多数公众号内容。",
        "#2563EB",
        "sans",
    ),
    (
        "tech",
        "科技前沿",
        "冷色细线、字距略开，适合 AI、硬件与产品发布。",
        "#0EA5E9",
        "sans",
    ),
    (
        "science",
        "科普轻读",
        "青绿点线、层级清晰，适合知识讲解与入门科普。",
        "#059669",
        "sans",
    ),
    (
        "lifestyle",
        "生活分享",
        "暖色居中标题、底部分隔，适合日常随笔与种草。",
        "#EA580C",
        "sans",
    ),
    (
        "editorial",
        "人文叙事",
        "衬线留白、细线斜引，适合评论、故事与深度长文。",
        "#6D28D9",
        "serif",
    ),
)

STYLE_THEME_CSS = """
/* 公众号友好：白底深字，只用强调色与线条区分主题，避免大面积色块 */

#article-html[data-style] .wechat-article {
  background: #ffffff;
  color: #1f2937;
}
#article-html[data-style] .wechat-article blockquote {
  background: transparent;
  border-radius: 0;
}
#article-html[data-style] .wechat-article .wechat-callout,
#article-html[data-style] .wechat-article .wechat-video-card {
  background: transparent;
  border-radius: 0;
  border: none;
  border-left: 3px solid var(--wx-accent);
  overflow: visible;
}
#article-html[data-style] .wechat-article .wechat-callout-hd,
#article-html[data-style] .wechat-article .wechat-video-card-hd {
  background: transparent;
  color: var(--wx-accent);
  padding: 0 0 6px 0;
}
#article-html[data-style] .wechat-article .wechat-callout-bd,
#article-html[data-style] .wechat-article .wechat-video-card-bd {
  padding: 0 0 0 2px;
}
#article-html[data-style] .wechat-article h2 {
  background: transparent;
}

/* 简约通用：克制底边 + 左侧细条 */
#article-html[data-style="classic"] .wechat-article h1 {
  color: var(--wx-accent);
  border: none;
  border-bottom: 2px solid var(--wx-accent);
  padding: 0 0 8px;
}
#article-html[data-style="classic"] .wechat-article h2 {
  color: #111827;
  border: none;
  border-left: 3px solid var(--wx-accent);
  padding: 0 0 0 10px;
}
#article-html[data-style="classic"] .wechat-article blockquote {
  border-left: 3px solid var(--wx-accent);
  padding: 0.25rem 0 0.25rem 0.9rem;
  color: #374151;
}

/* 科技前沿：字距略开、细线硬边，无底色 */
#article-html[data-style="tech"] .wechat-article h1 {
  color: var(--wx-accent);
  border: none;
  border-bottom: 1px solid var(--wx-accent);
  padding: 0 0 10px;
  letter-spacing: 0.06em;
}
#article-html[data-style="tech"] .wechat-article h2 {
  color: #0f172a;
  border: none;
  border-left: 2px solid var(--wx-accent);
  padding: 0 0 0 12px;
  letter-spacing: 0.03em;
}
#article-html[data-style="tech"] .wechat-article h3 {
  color: #334155;
}
#article-html[data-style="tech"] .wechat-article blockquote {
  border-left: 2px solid var(--wx-accent);
  padding: 0.2rem 0 0.2rem 0.85rem;
  color: #475569;
}
#article-html[data-style="tech"] .wechat-article .wechat-callout,
#article-html[data-style="tech"] .wechat-article .wechat-video-card {
  border-left-width: 2px;
}

/* 科普轻读：点状底边，亲和清晰 */
#article-html[data-style="science"] .wechat-article h1 {
  color: var(--wx-accent);
  border: none;
  border-bottom: 2px dotted var(--wx-accent);
  padding: 0 0 8px;
}
#article-html[data-style="science"] .wechat-article h2 {
  color: #14532d;
  border: none;
  border-left: 3px solid var(--wx-accent);
  padding: 0 0 0 10px;
}
#article-html[data-style="science"] .wechat-article blockquote {
  border-left: 3px solid var(--wx-accent);
  padding: 0.25rem 0 0.25rem 0.9rem;
  color: #166534;
}

/* 生活分享：居中主标题，柔和底部分隔线 */
#article-html[data-style="lifestyle"] .wechat-article h1 {
  color: var(--wx-accent);
  border: none;
  text-align: center;
  padding: 0 0 4px;
}
#article-html[data-style="lifestyle"] .wechat-article h2 {
  color: #9a3412;
  border: none;
  border-bottom: 1px solid var(--wx-accent);
  padding: 0 0 6px;
}
#article-html[data-style="lifestyle"] .wechat-article blockquote {
  border-left: 3px solid var(--wx-accent);
  padding: 0.25rem 0 0.25rem 0.9rem;
  color: #9a3412;
}
#article-html[data-style="lifestyle"] .wechat-article .wechat-callout,
#article-html[data-style="lifestyle"] .wechat-article .wechat-video-card {
  border-left-width: 3px;
}

/* 人文叙事：细线、字距与斜体引用，偏编辑感 */
#article-html[data-style="editorial"] .wechat-article {
  line-height: 1.9;
}
#article-html[data-style="editorial"] .wechat-article h1 {
  color: #1c1917;
  border: none;
  border-bottom: 1px solid #d6d3d1;
  padding: 0 0 10px;
  letter-spacing: 0.08em;
  font-weight: 650;
}
#article-html[data-style="editorial"] .wechat-article h2 {
  color: var(--wx-accent);
  border: none;
  padding: 0;
  font-weight: 650;
  letter-spacing: 0.04em;
}
#article-html[data-style="editorial"] .wechat-article blockquote {
  border-left: 2px solid #a8a29e;
  padding: 0.2rem 0 0.2rem 0.85rem;
  color: #57534e;
  font-style: italic;
}
#article-html[data-style="editorial"] .wechat-article .wechat-callout,
#article-html[data-style="editorial"] .wechat-article .wechat-video-card {
  border-left-color: #a8a29e;
}
#article-html[data-style="editorial"] .wechat-article .wechat-callout-hd,
#article-html[data-style="editorial"] .wechat-article .wechat-video-card-hd {
  color: #57534e;
}
"""


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
  background: transparent;
  font-weight: 600;
}
#article-html .wechat-article blockquote {
  margin: 0 0 1.25rem;
  padding: 0.25rem 0 0.25rem 0.9rem;
  border-left: 3px solid var(--wx-accent);
  background: transparent;
  border-radius: 0;
  color: #374151;
}
#article-html .wechat-article pre {
  margin: 1em 0;
  padding: 12px 0;
  background: transparent;
  border-top: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
  border-radius: 0;
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
  background: transparent;
  padding: 0;
  border-bottom: 1px solid #d1d5db;
  border-radius: 0;
  color: #111827;
}
#article-html .wechat-article .wechat-code {
  margin: 1em 0;
  border: none;
  border-top: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
  border-radius: 0;
  overflow: visible;
}
#article-html .wechat-article .wechat-code-title {
  background: transparent;
  color: var(--wx-accent);
  font-size: 0.75em;
  font-weight: 600;
  padding: 6px 0;
  border-bottom: 1px solid #e5e7eb;
}
#article-html .wechat-article .wechat-code-title span {
  color: inherit;
  font-weight: inherit;
  font-size: inherit;
}
#article-html .wechat-article .wechat-code pre {
  margin: 0;
  border: none;
  border-radius: 0;
}
#article-html .wechat-article .wechat-video-card,
#article-html .wechat-article .wechat-callout {
  margin: 1em 0;
  border: none;
  border-left: 3px solid var(--wx-accent);
  background: transparent;
  border-radius: 0;
  overflow: visible;
}
#article-html .wechat-article .wechat-video-card-hd,
#article-html .wechat-article .wechat-callout-hd {
  background: transparent;
  color: var(--wx-accent);
  font-weight: 600;
  padding: 0 0 6px 0;
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
  padding: 0 0 0 2px;
}
#article-html .wechat-article .wechat-video-card figure {
  margin: 0;
}
#article-html .wechat-article .wechat-video-card img {
  margin: 0;
}
#article-html .wechat-article .wechat-video-fallback {
  color: #4b5563;
  background: transparent;
  padding: 0;
  border-radius: 0;
}
""" + STYLE_THEME_CSS


def theme_payload() -> dict:
    return {
        "styles": {
            key: {
                "label": label,
                "desc": desc,
                "accent": accent,
                "font": font,
            }
            for key, label, desc, accent, font in STYLE_THEMES
        },
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
