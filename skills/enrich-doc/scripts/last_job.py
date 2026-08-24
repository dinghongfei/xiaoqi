"""Session artifacts for the latest bot job (not Agent memory)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BOT_ROOT, Settings


def last_job_path(settings: Settings) -> Path:
    return Path(settings.last_job_path)


def load_last_job(settings: Settings) -> dict[str, Any] | None:
    path = last_job_path(settings)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def dump_last_job(settings: Settings, data: dict[str, Any]) -> Path:
    path = last_job_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def update_last_job(settings: Settings, **fields: Any) -> dict[str, Any]:
    current = load_last_job(settings) or {}
    current.update({k: v for k, v in fields.items() if v is not None})
    dump_last_job(settings, current)
    return current


def relpath(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(BOT_ROOT.resolve()))
    except ValueError:
        return str(resolved)


def job_dir(settings: Settings, token: str) -> Path:
    safe = "".join(ch for ch in token if ch.isalnum() or ch in ("-", "_"))
    if not safe:
        safe = "unknown"
    path = Path(settings.jobs_dir) / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def abs_from_job(settings: Settings, stored: str | None) -> Path | None:
    if not stored:
        return None
    path = Path(stored)
    if not path.is_absolute():
        path = BOT_ROOT / path
    return path
