"""Hugo content path helpers."""

from pathlib import Path

from parser.metadata import VALID_SECTIONS

LANG_DIRS = {
    "zh-cn": "zh-cn",
    "en": "en",
}


def content_file_path(hugo_root: Path, section: str, lang: str, slug: str) -> Path:
    lang_dir = LANG_DIRS.get(lang)
    if not lang_dir:
        raise ValueError(f"Unknown lang: {lang}")
    return hugo_root / "content" / lang_dir / section / f"{slug}.md"


def find_existing_section(hugo_root: Path, slug: str) -> str | None:
    """Return section if slug already exists in any language directory."""
    for section in VALID_SECTIONS:
        for lang in LANG_DIRS:
            if content_file_path(hugo_root, section, lang, slug).exists():
                return section
    return None


def static_media_path(static_dir: Path, media_type: str, filename: str) -> Path:
    subdir = "image" if media_type == "image" else "video"
    return static_dir / subdir / filename
