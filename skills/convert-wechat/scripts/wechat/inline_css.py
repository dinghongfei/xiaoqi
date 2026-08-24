"""Tiny CSS inliner for WeChat HTML (style tags are stripped by editors)."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_RULE_RE = re.compile(
    r"([^{]+)\{([^}]+)\}",
    re.DOTALL,
)


def _parse_rules(css: str) -> list[tuple[list[str], str]]:
    rules: list[tuple[list[str], str]] = []
    for match in _RULE_RE.finditer(css):
        selectors = [part.strip() for part in match.group(1).split(",") if part.strip()]
        decls = " ".join(match.group(2).split())
        if selectors and decls:
            rules.append((selectors, decls.rstrip(";")))
    return rules


def _escape_attr(value: str) -> str:
    """Escape attribute values without turning CSS single quotes into entities."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    raw = ""
    for key, value in attrs:
        if key.lower() == "class" and value:
            raw = value
            break
    return set(raw.split())


def _match(selector: str, tag: str, classes: set[str], in_article: bool) -> bool:
    selector = re.sub(r"\s+", " ", selector).strip()
    if selector == ".wechat-article":
        return tag == "div" and "wechat-article" in classes
    if selector.startswith(".wechat-article "):
        if not in_article:
            return False
        rest = selector[len(".wechat-article ") :].strip()
        if rest.startswith("."):
            return rest[1:] in classes
        if "." in rest:
            name, cls = rest.split(".", 1)
            return tag == name and cls in classes
        return tag == rest
    if selector.startswith("."):
        return selector[1:] in classes
    return tag == selector


class _Inliner(HTMLParser):
    def __init__(self, rules: list[tuple[list[str], str]]):
        super().__init__(convert_charrefs=False)
        self.rules = rules
        self.parts: list[str] = []
        self._article_depth = 0
        self._div_marks: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(self._open(tag, attrs, self_closing=False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(self._open(tag, attrs, self_closing=True))

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._div_marks:
            if self._div_marks.pop():
                self._article_depth = max(0, self._article_depth - 1)
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.parts.append(f"<!{decl}>")

    def _open(self, tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool) -> str:
        classes = _classes(attrs)
        in_article = self._article_depth > 0 or "wechat-article" in classes
        styles: list[str] = []
        existing = ""
        kept: list[tuple[str, str]] = []
        for key, value in attrs:
            if key.lower() == "style" and value:
                existing = value.strip().rstrip(";")
                continue
            kept.append((key, value or ""))
        for selectors, decls in self.rules:
            if any(_match(sel, tag, classes, in_article) for sel in selectors):
                styles.append(decls)
        if existing:
            styles.insert(0, existing)
        if styles:
            kept.append(("style", "; ".join(styles) + ";"))
        if tag == "div":
            is_article = "wechat-article" in classes
            self._div_marks.append(is_article)
            if is_article:
                self._article_depth += 1
        attr_str = "".join(
            f' {k}="{_escape_attr(v)}"' for k, v in kept
        )
        if self_closing or tag in {"img", "br", "hr", "source", "meta", "link"}:
            return f"<{tag}{attr_str}>"
        return f"<{tag}{attr_str}>"


def inline_css(html: str, css: str) -> str:
    """Apply simple class/descendant CSS as inline style attributes."""
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", html, flags=re.I | re.S)
    parser = _Inliner(_parse_rules(css))
    parser.feed(body)
    parser.close()
    return "".join(parser.parts)
