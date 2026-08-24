"""Parse Feishu doc content into metadata and body."""

from dataclasses import dataclass

from media.downloader import (
    IMAGE_TAG_PATTERN,
    IMG_TAG_PATTERN,
    MARKDOWN_IMAGE_PATTERN,
)
from parser.feishu_text import prepare_feishu_markdown
from parser.metadata import MetadataError
from parser.metadata_table import parse_metadata_table


@dataclass
class DocContent:
    metadata: dict
    body: str
    metadata_region: str


def _metadata_text_from_region(metadata_region: str) -> str:
    """Strip embedded images from metadata so parsing still works."""
    text = metadata_region
    for pattern in (IMG_TAG_PATTERN, IMAGE_TAG_PATTERN, MARKDOWN_IMAGE_PATTERN):
        text = pattern.sub("", text)
    return text


def split_doc_content(raw: str) -> DocContent:
    """Split raw markdown from Feishu into metadata table and body."""
    text = prepare_feishu_markdown(raw)
    lines = text.splitlines()

    end_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise MetadataError("元数据和正文之间得画条分界线～请用 --- 隔开 🚧")

    metadata_region = "\n".join(lines[:end_idx])
    body = "\n".join(lines[end_idx + 1 :]).strip()

    metadata_text = _metadata_text_from_region(metadata_region)
    if not metadata_text.strip():
        raise MetadataError("元数据区空空如也？表格还没填呢 📭")

    metadata = parse_metadata_table(metadata_text)
    return DocContent(metadata=metadata, body=body, metadata_region=metadata_region)
