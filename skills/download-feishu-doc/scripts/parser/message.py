"""Parse @bot commands from group chat messages."""

import json
import re
from dataclasses import dataclass
from typing import Literal

from parser.metadata import VALID_SECTIONS

# Path-based, not host-based: doubao.com / feishu.cn / larksuite.com all work.
DOCX_URL_PATTERN = re.compile(
    r"https?://[^\s/]+/docx/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
WIKI_URL_PATTERN = re.compile(
    r"https?://[^\s/]+/wiki/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
PUBLISH_VERBS = frozenset({"发布", "deploy"})
ENRICH_VERBS = frozenset({"补全", "enrich"})
RESET_VERBS = frozenset(
    {
        "清理工作区",
        "清理",
        "还原",
        "重置",
        "clear",
        "reset",
        "clean",
        "restore",
    }
)

CommandMode = Literal["convert", "publish", "reset", "enrich"]


@dataclass(frozen=True)
class DocRef:
    """Reference to a Feishu document from a chat message URL."""

    kind: str  # docx | wiki
    token: str
    url: str = ""  # 消息里收到的原始链接

    @property
    def label(self) -> str:
        return f"{self.kind}/{self.token}"


@dataclass
class ParsedCommand:
    section: str
    doc_refs: list[DocRef]
    mode: CommandMode = "convert"
    secret_key: str = ""


class MessageParseError(ValueError):
    pass


def extract_doc_refs(text: str) -> list[DocRef]:
    refs: list[DocRef] = []
    seen: set[tuple[str, str]] = set()

    for pattern, kind in ((DOCX_URL_PATTERN, "docx"), (WIKI_URL_PATTERN, "wiki")):
        for match in pattern.finditer(text):
            token = match.group(1)
            key = (kind, token)
            if key not in seen:
                seen.add(key)
                refs.append(DocRef(kind=kind, token=token, url=match.group(0)))

    return refs


DEFAULT_SECTION = "blog"


def _strip_mentions(text: str) -> str:
    text = re.sub(r"@_\w+_\d+\s*", "", text)
    return re.sub(r"@\S+\s*", "", text).strip()


def _is_reset_command(cleaned: str) -> bool:
    if not cleaned:
        return False
    normalized = cleaned.strip().lower()
    if normalized in RESET_VERBS:
        return True
    first = normalized.split()[0]
    return first in RESET_VERBS


def _parse_publish_command(cleaned: str, doc_refs: list[DocRef]) -> ParsedCommand:
    tokens = cleaned.split()
    if len(tokens) < 2:
        raise MessageParseError(
            "发布/deploy 指令格式不对～应为：发布 sk 文档链接 🔗"
        )

    secret_key = tokens[1]
    if secret_key.startswith("http"):
        raise MessageParseError(
            "发布/deploy 指令格式不对～sk 要紧跟在「发布」或 deploy 后面 🔐"
        )

    section = DEFAULT_SECTION
    if len(tokens) >= 3 and tokens[2].lower() in VALID_SECTIONS:
        section = tokens[2].lower()

    if not doc_refs:
        raise MessageParseError(
            "发布也得有文档才行呀～请附上 docx 或 wiki 链接 🔗"
        )

    return ParsedCommand(
        section=section,
        doc_refs=doc_refs,
        mode="publish",
        secret_key=secret_key,
    )


def _parse_enrich_command(doc_refs: list[DocRef]) -> ParsedCommand:
    if not doc_refs:
        raise MessageParseError(
            "补全也得有文档才行呀～请附上 docx 或 wiki 链接 🔗"
        )
    return ParsedCommand(
        section=DEFAULT_SECTION,
        doc_refs=doc_refs,
        mode="enrich",
    )


def parse_command(text: str) -> ParsedCommand:
    """Parse convert, publish/deploy, enrich, or reset commands from Feishu message text."""
    cleaned = _strip_mentions(text)
    doc_refs = extract_doc_refs(text)

    if cleaned:
        if _is_reset_command(cleaned):
            return ParsedCommand(section=DEFAULT_SECTION, doc_refs=[], mode="reset")

        first = cleaned.split()[0].lower()
        if first in PUBLISH_VERBS:
            return _parse_publish_command(cleaned, doc_refs)

        if first in ENRICH_VERBS:
            return _parse_enrich_command(doc_refs)

    if not doc_refs:
        raise MessageParseError(
            "我只会「飞书文档 → Hugo」转换这一件事，查资料、闲聊啥的暂时真不会～，请附上文档链接再 @ 我 🔗"
        )

    if not cleaned:
        return ParsedCommand(section=DEFAULT_SECTION, doc_refs=doc_refs)

    first = cleaned.split()[0].lower()
    section = first if first in VALID_SECTIONS else DEFAULT_SECTION

    return ParsedCommand(section=section, doc_refs=doc_refs, mode="convert")


def parse_message_content(content: str) -> str:
    """Extract plain text from Feishu message JSON content."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content

    if isinstance(data, str):
        return data

    text = data.get("text", "")
    return re.sub(r"@_\w+_\d+\s*", "", text).strip()
