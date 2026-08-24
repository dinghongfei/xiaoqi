"""Preserve ordered-list numbering when Feishu inserts media between items."""

from __future__ import annotations

import re

ORDERED_LIST_ITEM_RE = re.compile(r"^(\d+)\.\s")
FIGURE_CAPTION_RE = re.compile(r"^(?:\*|\s*)?(?:Figure|Fig\.)\b", re.IGNORECASE)
SHORTCODE_RE = re.compile(r"^\{\{<")
MARKDOWN_IMAGE_RE = re.compile(r"^!\[")


def _is_list_interrupter(line: str) -> bool:
    """Lines that may appear between ordered-list items without starting a new list."""
    if not line.strip():
        return True
    if ORDERED_LIST_ITEM_RE.match(line):
        return False
    if line.lstrip().startswith("#"):
        return False
    if MARKDOWN_IMAGE_RE.match(line.strip()):
        return True
    if SHORTCODE_RE.match(line.strip()):
        return True
    if "{{< figure" in line:
        return True
    if FIGURE_CAPTION_RE.match(line.strip()):
        return True
    lower = line.lower()
    if "<grid" in lower or "</grid>" in lower or "<column" in lower:
        return True
    return False


def fix_ordered_list_numbering(body: str) -> str:
    """Renumber list items that Feishu restarts at 1 after media blocks."""
    lines = body.split("\n")
    output: list[str] = []
    in_list = False
    next_num = 1

    for line in lines:
        match = ORDERED_LIST_ITEM_RE.match(line)
        if match:
            num = int(match.group(1))
            if in_list and num == 1 and next_num > 1:
                num = next_num
                line = ORDERED_LIST_ITEM_RE.sub(f"{num}. ", line, count=1)
            elif not in_list:
                in_list = True
                next_num = num + 1
            elif num == next_num:
                next_num = num + 1
            else:
                in_list = True
                next_num = num + 1
            output.append(line)
            continue

        if _is_list_interrupter(line):
            output.append(line)
            continue

        in_list = False
        next_num = 1
        output.append(line)

    return "\n".join(output)
