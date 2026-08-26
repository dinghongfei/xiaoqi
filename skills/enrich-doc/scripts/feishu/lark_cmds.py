"""lark-cli command strings for Agent prompts. Never include --profile or --as."""

from __future__ import annotations


def inspect_wiki(url: str) -> str:
    return f"lark-cli drive +inspect --url '{url}'"


def fetch_markdown(doc: str) -> str:
    return (
        "lark-cli docs +fetch --api-version v2 "
        f"--doc '{doc}' --doc-format markdown"
    )


def fetch_xml(doc: str) -> str:
    return (
        "lark-cli docs +fetch --api-version v2 "
        f"--doc '{doc}' --doc-format xml --detail full"
    )


def fetch_xml_with_ids(doc: str) -> str:
    return (
        "lark-cli docs +fetch --api-version v2 "
        f"--doc '{doc}' --doc-format xml --detail with-ids"
    )


def media_download(token: str, output: str, *, whiteboard: bool = False) -> str:
    extra = " --type whiteboard" if whiteboard else ""
    return (
        f"lark-cli docs +media-download --token '{token}' "
        f"--output '{output}'{extra}"
    )


def docs_append_xml(doc: str, xml_path: str) -> str:
    return (
        f"lark-cli docs +update --doc '{doc}' --command append "
        f"--doc-format xml --content \"$(cat '{xml_path}')\""
    )


def docs_move_blocks(page_id: str, src_block_ids: str) -> str:
    return (
        f"lark-cli docs +update --doc '{page_id}' --command block_move_after "
        f"--block-id '{page_id}' --src-block-ids '{src_block_ids}'"
    )


AUTH_HINT = "调用 lark-cli 时不要加 --profile 或 --as。"
