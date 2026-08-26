"""lark-cli command strings for Agent prompts. Never include --profile or --as."""

from __future__ import annotations


def inspect_wiki(token: str) -> str:
    """Resolve a wiki node token to the underlying docx token. Pass token, not URL."""
    return f"lark-cli drive +inspect --url '{token}' --type wiki"


def fetch_markdown(token: str) -> str:
    return (
        "lark-cli docs +fetch --api-version v2 "
        f"--doc '{token}' --doc-format markdown"
    )


def fetch_xml(token: str) -> str:
    return (
        "lark-cli docs +fetch --api-version v2 "
        f"--doc '{token}' --doc-format xml --detail full"
    )


def fetch_xml_with_ids(token: str) -> str:
    return (
        "lark-cli docs +fetch --api-version v2 "
        f"--doc '{token}' --doc-format xml --detail with-ids"
    )


def media_download(token: str, output: str, *, whiteboard: bool = False) -> str:
    extra = " --type whiteboard" if whiteboard else ""
    return (
        f"lark-cli docs +media-download --token '{token}' "
        f"--output '{output}'{extra}"
    )


def docs_append_xml(token: str, xml_path: str) -> str:
    return (
        f"lark-cli docs +update --doc '{token}' --command append "
        f"--doc-format xml --content \"$(cat '{xml_path}')\""
    )


def docs_move_blocks(page_id: str, src_block_ids: str) -> str:
    return (
        f"lark-cli docs +update --doc '{page_id}' --command block_move_after "
        f"--block-id '{page_id}' --src-block-ids '{src_block_ids}'"
    )


AUTH_HINT = (
    "调用 lark-cli 时不要加 --profile 或 --as。"
    "拉文档、写回请传 token，不要传 feishu.doubao.com 等完整 URL。"
)
