"""Normalize text exported from Feishu docs/markdown."""

import re
from datetime import date, datetime

TITLE_TAG_PATTERN = re.compile(r"<title>[^<]*</title>\s*", re.IGNORECASE)
DATE_ONLY_PATTERN = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
CATEGORY_SPLIT_PATTERN = re.compile(r"[,，;；/|]+")
DEFAULT_TZ_SUFFIX = "T00:00:00+08:00"

HEADING_LINE_PATTERN = re.compile(r"^(#{1,6}\s+)(.*)$")
INLINE_STYLE_PATTERNS = (
    re.compile(r"\*\*\*(.+?)\*\*\*"),
    re.compile(r"___(.+?)___"),
    re.compile(r"\*\*(.+?)\*\*"),
    re.compile(r"__(.+?)__"),
    re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)"),
    re.compile(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)"),
    re.compile(r"~~(.+?)~~"),
    re.compile(r"`(.+?)`"),
)
HTML_EMPHASIS_PATTERN = re.compile(
    r"</?(?:strong|em|b|i|u|s|del|mark)(?:\s[^>]*)?>",
    re.IGNORECASE,
)


def strip_feishu_title_tag(text: str) -> str:
    """Remove leading <title> block inserted by lark-cli docs +fetch markdown export."""
    return TITLE_TAG_PATTERN.sub("", text, count=1)


def prepare_feishu_markdown(raw: str) -> str:
    """Normalize Feishu/lark-cli markdown export before metadata parsing."""
    text = strip_feishu_title_tag(raw).strip()
    return text


def unescape_feishu_text(text: str) -> str:
    """Remove backslash escapes inserted by Feishu markdown/YAML export."""
    return re.sub(r"\\(.)", r"\1", text.strip())


def strip_inline_styles(text: str) -> str:
    """Remove bold/italic/code/strike markers and simple emphasis HTML tags."""
    result = text
    previous = None
    while previous != result:
        previous = result
        for pattern in INLINE_STYLE_PATTERNS:
            result = pattern.sub(r"\1", result)
        result = HTML_EMPHASIS_PATTERN.sub("", result)
    return result.strip()


def strip_heading_inline_styles(markdown: str) -> str:
    """Strip inline styles from ATX heading lines only; leave body text alone."""
    lines: list[str] = []
    for line in markdown.splitlines():
        match = HEADING_LINE_PATTERN.match(line)
        if match:
            prefix, content = match.group(1), match.group(2)
            lines.append(f"{prefix}{strip_inline_styles(content)}")
        else:
            lines.append(line)
    result = "\n".join(lines)
    if markdown.endswith("\n"):
        result += "\n"
    return result


def _clean_category_item(item: str) -> str:
    s = unescape_feishu_text(item).strip()
    if s.startswith("- "):
        return s[2:].strip()
    if s.startswith("-"):
        return s[1:].strip()
    return s


def normalize_categories(value) -> list[str]:
    if isinstance(value, list):
        items = [_clean_category_item(str(v)) for v in value]
        return [item for item in items if item]

    if isinstance(value, str):
        cleaned = unescape_feishu_text(value).strip()
        if not cleaned:
            return []
        parts = [part.strip() for part in CATEGORY_SPLIT_PATTERN.split(cleaned)]
        items = [_clean_category_item(part) for part in parts if part.strip()]
        return [item for item in items if item]

    if value is None:
        return []

    item = unescape_feishu_text(str(value)).strip()
    return [item] if item else []


def normalize_date(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return f"{value.isoformat()}{DEFAULT_TZ_SUFFIX}"

    text = unescape_feishu_text(str(value)).strip()
    match = DATE_ONLY_PATTERN.match(text)
    if match:
        year, month, day = (int(match.group(i)) for i in range(1, 4))
        return f"{date(year, month, day).isoformat()}{DEFAULT_TZ_SUFFIX}"

    return text


def normalize_metadata_fields(data: dict) -> dict:
    """Clean Feishu export artifacts from Hugo front matter fields."""
    for key in ("title", "author", "summary"):
        if key in data and isinstance(data[key], str):
            data[key] = unescape_feishu_text(data[key])

    if "date" in data and data["date"] is not None:
        data["date"] = normalize_date(data["date"])

    if "categories" in data and data["categories"] is not None:
        data["categories"] = normalize_categories(data["categories"])

    return data
