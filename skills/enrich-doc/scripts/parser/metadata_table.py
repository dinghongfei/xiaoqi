"""Parse metadata table from Feishu doc markdown export."""

import re

from parser.feishu_text import unescape_feishu_text
from parser.metadata import MetadataError, validate_metadata_fields


def parse_table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    inner = stripped.strip("|")
    return [cell.strip() for cell in inner.split("|")]


def is_table_separator_row(cells: list[str]) -> bool:
    non_empty = [cell for cell in cells if cell.strip()]
    if not non_empty:
        return True
    return all(re.fullmatch(r"-+", cell.strip()) for cell in non_empty)


def parse_metadata_table(text: str) -> dict:
    """Parse a three-column metadata table: field | hint | value."""
    data: dict[str, str] = {}
    hints: dict[str, str] = {}

    for line in text.splitlines():
        cells = parse_table_cells(line)
        if not cells or is_table_separator_row(cells) or len(cells) < 3:
            continue

        key = unescape_feishu_text(cells[0]).strip().lower()
        hint = unescape_feishu_text(cells[1]).strip()
        value = unescape_feishu_text(cells[2]).strip()
        if key:
            data[key] = value
            if hint:
                hints[key] = hint

    if not data:
        raise MetadataError(
            "咦，元数据怎么不是表格？请用三列表格填写（属性名 | 说明 | 属性值）📋"
        )

    return validate_metadata_fields(data, hints)
