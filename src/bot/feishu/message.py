"""Extract plain text from a Feishu IM event payload."""

from __future__ import annotations

import json
import re


def parse_message_content(content: str) -> str:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content

    if isinstance(data, str):
        return data

    text = data.get("text", "")
    return re.sub(r"@_\w+_\d+\s*", "", text).strip()
