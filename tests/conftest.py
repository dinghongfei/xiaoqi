"""Put each Skill's scripts/ on sys.path so tests import portable packages."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SKILL_NAMES = (
    "clean-generated",
    "reply-preview",
    "compress-media",
    "deploy-local",
    "deploy-cloud",
    "convert-website",
    "convert-wechat",
    "download-feishu-doc",
    "enrich-doc",
)


def pytest_configure() -> None:
    for name in SKILL_NAMES:
        path = str(REPO_ROOT / "skills" / name / "scripts")
        if path not in sys.path:
            sys.path.insert(0, path)
