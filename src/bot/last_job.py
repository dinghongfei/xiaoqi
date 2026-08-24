"""Read last-job.json so the IM adapter can include it in the Agent prompt."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bot.config import Settings


def load_last_job(settings: Settings) -> dict[str, Any] | None:
    path = Path(settings.last_job_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
