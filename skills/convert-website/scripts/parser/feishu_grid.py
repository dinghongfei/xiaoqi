"""Convert Feishu grid/column markup to Hugo shortcodes."""

from __future__ import annotations

import re

GRID_PATTERN = re.compile(r"<grid\b[^>]*>(.*?)</grid>", re.IGNORECASE | re.DOTALL)
COLUMN_PATTERN = re.compile(
    r"<column\b([^>]*)>(.*?)</column>",
    re.IGNORECASE | re.DOTALL,
)
EMPTY_P_TAG_PATTERN = re.compile(r"<p>\s*</p>", re.IGNORECASE)
WIDTH_RATIO_PATTERN = re.compile(r'width-ratio="([^"]+)"', re.IGNORECASE)


def _column_shortcode(attrs: str, content: str) -> str:
    content = EMPTY_P_TAG_PATTERN.sub("", content).strip()
    width_match = WIDTH_RATIO_PATTERN.search(attrs)
    width_attr = f' width-ratio="{width_match.group(1)}"' if width_match else ""
    open_tag = "{{< column" + width_attr + " >}}"
    return open_tag + "\n" + content + "\n" + "{{< /column >}}"


def convert_feishu_grid_to_shortcode(body: str) -> str:
    """Replace Feishu <grid>/<column> blocks with Hugo grid shortcodes."""

    def replace_grid(match: re.Match[str]) -> str:
        columns = [
            _column_shortcode(col_match.group(1), col_match.group(2))
            for col_match in COLUMN_PATTERN.finditer(match.group(1))
        ]
        if not columns:
            return match.group(0)
        return "{{< grid >}}\n" + "\n".join(columns) + "\n{{< /grid >}}"

    return GRID_PATTERN.sub(replace_grid, body)
