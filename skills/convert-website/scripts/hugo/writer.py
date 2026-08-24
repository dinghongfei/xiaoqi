"""Write Hugo markdown files with TOML front matter."""

from pathlib import Path

from hugo.paths import content_file_path


def _toml_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _format_toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _toml_quote(value)
    if isinstance(value, list):
        items = ", ".join(_toml_quote(str(v)) for v in value)
        return f"[{items}]"
    return _toml_quote(str(value))


def build_front_matter(metadata: dict, slug: str) -> str:
    """Build TOML front matter from metadata dict."""
    field_order = [
        "date",
        "draft",
        "title",
        "translationKey",
        "categories",
        "author",
        "summary",
        "featured_image",
    ]

    lines = ["+++"]
    fm = dict(metadata)
    fm["translationKey"] = slug

    for key in field_order:
        if key in fm and fm[key] is not None and fm[key] != "":
            lines.append(f"{key} = {_format_toml_value(fm[key])}")

    lines.append("+++")
    return "\n".join(lines)


def build_markdown(metadata: dict, slug: str, body: str) -> str:
    front = build_front_matter(metadata, slug)
    return f"{front}\n\n{body.strip()}\n"


def write_content_file(
    hugo_root: Path,
    section: str,
    lang: str,
    slug: str,
    metadata: dict,
    body: str,
) -> Path:
    path = content_file_path(hugo_root, section, lang, slug)
    path.parent.mkdir(parents=True, exist_ok=True)

    content = build_markdown(metadata, slug, body)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return path
