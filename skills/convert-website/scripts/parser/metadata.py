"""Parse metadata block from Feishu doc."""

import re

from parser.feishu_text import normalize_metadata_fields, unescape_feishu_text

VALID_LANGS = frozenset({"zh-cn", "en"})
USER_LANG_INPUT = frozenset({"zh", "en"})
VALID_SECTIONS = frozenset({"blog"})
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

REQUIRED_METADATA_FIELDS = (
    "slug",
    "lang",
    "title",
    "date",
    "author",
    "categories",
    "summary",
)

DEFAULT_FIELD_HINTS: dict[str, str] = {
    "slug": "文件名，中英文文章要一致，不允许中文、空格，多个单词使用-链接",
    "lang": "中文写zh, 英文写en",
    "title": "标题",
    "date": "时间，格式2026-02-14 要<=今天",
    "author": "作者",
    "categories": "分类",
    "summary": "摘要，100字以内",
}


class MetadataError(ValueError):
    pass


def format_field_label(field: str, hints: dict[str, str] | None = None) -> str:
    field_hints = hints or {}
    hint = field_hints.get(field) or DEFAULT_FIELD_HINTS.get(field, field)
    return f"{field}（{hint}）"


def format_metadata_errors(errors: list[str]) -> str:
    if not errors:
        return ""
    if len(errors) == 1:
        error = errors[0]
        if _is_field_label_only(error):
            return f"元数据还差几笔～请补上 {error} ✏️"
        return error
    return "元数据还差几笔才完整呢～请补上 ✏️\n" + "\n".join(errors)


def _is_field_label_only(error: str) -> bool:
    return error.startswith(("slug（", "lang（", "title（", "date（", "author（", "categories（", "summary（"))


def collect_metadata_errors(
    data: dict,
    hints: dict[str, str] | None = None,
) -> list[str]:
    field_hints = hints or {}
    errors: list[str] = []

    for field in REQUIRED_METADATA_FIELDS:
        value = data.get(field)
        text = unescape_feishu_text(str(value)).strip() if value is not None else ""
        if not text:
            errors.append(format_field_label(field, field_hints))
            continue

        if field == "slug":
            slug = normalize_slug(text)
            if not SLUG_PATTERN.match(slug):
                label = format_field_label("slug", field_hints)
                errors.append(
                    f"slug 这个名字不太对劲～{label} 得用英文 kebab-case 哦 🔤"
                )
        elif field == "lang":
            raw = text.lower()
            if raw not in USER_LANG_INPUT:
                label = format_field_label("lang", field_hints)
                errors.append(
                    f"语言填错啦！{label} 只能填 zh 或 en，你写成了 {value!r} 🤷"
                )

    return errors


def normalize_slug(slug: str) -> str:
    return unescape_feishu_text(slug).lower()


def normalize_user_lang(lang: str) -> str:
    raw = unescape_feishu_text(lang).lower().strip()
    return "zh-cn" if raw == "zh" else "en"


def validate_metadata_fields(
    data: dict,
    hints: dict[str, str] | None = None,
) -> dict:
    """Validate and normalize core metadata fields."""
    errors = collect_metadata_errors(data, hints)
    if errors:
        raise MetadataError(format_metadata_errors(errors))

    data["slug"] = normalize_slug(str(data["slug"]))
    data["lang"] = normalize_user_lang(str(data["lang"]))

    if "draft" not in data or data["draft"] in (None, ""):
        data["draft"] = False

    return normalize_metadata_fields(data)


def validate_section(section: str) -> str:
    if section not in VALID_SECTIONS:
        raise MetadataError(
            f"section「{section}」我还不太认识呢，目前只懂："
            f"{', '.join(sorted(VALID_SECTIONS))} 🗂️"
        )
    return section
