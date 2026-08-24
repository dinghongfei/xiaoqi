"""Restore Feishu XML inline styles that markdown export drops."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_FRONT_MATTER = re.compile(r"^\+\+\+\n.*?\n\+\+\+\n*", re.DOTALL)
_FENCE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_OPEN_FENCE = re.compile(r"^```(?!`)([^\n]*)", re.MULTILINE)
_BARE_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_FIGURE_SHORTCODE = re.compile(
    r"\{\{<\s*figure\s+([^>]*)>\}\}",
    re.IGNORECASE,
)
_QUOTE_CHARS = "\"\"\"''"


def _clean_caption(text: str) -> str:
    text = html.unescape(text or "")
    return re.sub(r"[\s\xa0]+", " ", text).strip(" \t\r\n")


def _quote_pattern(text: str) -> str:
    escaped = re.escape(text)
    return escaped.replace(r"\"", f"[{re.escape(_QUOTE_CHARS)}]").replace(
        r"\'", f"[{re.escape(_QUOTE_CHARS)}]"
    )


class _FeishuStyleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[dict[str, str]] = []
        self.spans: list[tuple[str, dict[str, str]]] = []
        self.image_captions: list[str] = []
        self.code_titles: list[tuple[str, str]] = []
        self._in_pre = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        current = dict(self._stack[-1]) if self._stack else {}
        if tag in {"span", "font", "mark"}:
            color = attr.get("text-color") or attr.get("color")
            background = attr.get("background-color") or attr.get("bgcolor")
            if color:
                current["color"] = color
            if background:
                current["background"] = background
        if tag == "u":
            current["underline"] = "1"
        if tag in {"del", "s"}:
            current["strike"] = "1"
        if tag in {"callout", "pre", "table", "tr", "td", "th"}:
            current = {}
        self._stack.append(current)
        if tag == "pre":
            self._in_pre = True
            lang = (attr.get("lang") or "").strip()
            title = _clean_caption(attr.get("caption") or "")
            self.code_titles.append((lang, title))
        if tag in {"img", "image"}:
            caption = _clean_caption(attr.get("caption") or "")
            if caption:
                self.image_captions.append(caption)

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre":
            self._in_pre = False
        if self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_pre:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text or len(text) < 2:
            return
        style = self._stack[-1] if self._stack else {}
        useful = {
            key: value
            for key, value in style.items()
            if key in {"color", "background", "underline"} and value
        }
        if useful:
            self.spans.append((text, useful))


def parse_feishu_xml_styles(xml_text: str) -> _FeishuStyleParser:
    parser = _FeishuStyleParser()
    parser.feed(f"<doc>{xml_text}</doc>")
    parser.close()
    return parser


def _inside_code_fence(text: str, index: int) -> bool:
    for match in _FENCE_BLOCK.finditer(text):
        if match.start() < index < match.end():
            return True
    return False


def _already_marked(body: str, start: int, end: int) -> bool:
    prefix = body[max(0, start - 48) : start]
    return bool(re.search(r"<(?:u|span|del|mark)\b[^>]*>\s*$", prefix, re.I))


def _wrap_span(body: str, text: str, style: dict[str, str]) -> str:
    css: list[str] = []
    if style.get("color"):
        css.append(f"color: {style['color']}")
    if style.get("background"):
        css.append(f"background-color: {style['background']}")
    if style.get("underline") and not css:
        open_tag, close_tag = "<u>", "</u>"
    elif style.get("underline"):
        css.append("text-decoration: underline")
        open_tag = f'<span style="{html.escape("; ".join(css), quote=True)}">'
        close_tag = "</span>"
    else:
        open_tag = f'<span style="{html.escape("; ".join(css), quote=True)}">'
        close_tag = "</span>"

    pattern = re.compile(_quote_pattern(text))
    for match in pattern.finditer(body):
        if _inside_code_fence(body, match.start()):
            continue
        if _already_marked(body, match.start(), match.end()):
            continue
        return (
            body[: match.start()]
            + open_tag
            + match.group(0)
            + close_tag
            + body[match.end() :]
        )
    return body


def _apply_code_titles(body: str, titles: list[tuple[str, str]]) -> str:
    pending = [(lang, title) for lang, title in titles if title]
    if not pending:
        return body

    def repl(match: re.Match[str]) -> str:
        info = match.group(1).strip()
        if not info or "title=" in info:
            return match.group(0)
        if not pending:
            return match.group(0)
        _lang, title = pending.pop(0)
        escaped = title.replace('"', '\\"')
        return f'```{info} title="{escaped}"'

    return _OPEN_FENCE.sub(repl, body)


def _escape_shortcode(value: str) -> str:
    return value.replace('"', '\\"')


def _apply_image_captions(body: str, captions: list[str]) -> str:
    unused = list(captions)
    if not unused:
        return body

    def repl_md(match: re.Match[str]) -> str:
        alt, src = match.group(1).strip(), match.group(2).strip()
        if alt:
            return match.group(0)
        if not unused:
            return match.group(0)
        caption = unused.pop(0)
        return (
            f'{{{{< figure src="{src}" '
            f'caption="{_escape_shortcode(caption)}" >}}}}'
        )

    body = _BARE_IMAGE.sub(repl_md, body)

    def repl_figure(match: re.Match[str]) -> str:
        attrs = match.group(1)
        if re.search(r'\bcaption="[^"]+"', attrs):
            return match.group(0)
        if not unused:
            return match.group(0)
        caption = unused.pop(0)
        return (
            f'{{{{< figure {attrs.strip()} '
            f'caption="{_escape_shortcode(caption)}" >}}}}'
        )

    return _FIGURE_SHORTCODE.sub(repl_figure, body)


def overlay_xml_styles(markdown_text: str, xml_text: str) -> str:
    """Put back underline, colors, highlights, code titles and image captions."""
    if not xml_text.strip():
        return markdown_text
    parsed = parse_feishu_xml_styles(xml_text)
    front = ""
    body = markdown_text
    match = _FRONT_MATTER.match(markdown_text)
    if match:
        front = match.group(0)
        body = markdown_text[match.end() :]

    spans = sorted(parsed.spans, key=lambda item: len(item[0]), reverse=True)
    for text, style in spans:
        body = _wrap_span(body, text, style)
    body = _apply_code_titles(body, parsed.code_titles)
    body = _apply_image_captions(body, parsed.image_captions)
    return front + body
