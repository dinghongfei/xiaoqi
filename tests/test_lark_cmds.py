"""Tests for lark-cli command strings and fetch payload parsing."""

from feishu import lark_cmds
from feishu.payload import document_from_fetch


def test_cmds_omit_profile_and_as():
    url = "https://example.feishu.cn/wiki/WikiTok"
    assert "--profile" not in lark_cmds.inspect_wiki(url)
    assert "--as" not in lark_cmds.fetch_markdown("doxcn1")
    assert "--as" not in lark_cmds.fetch_xml("doxcn1")
    assert "--profile" not in lark_cmds.media_download("tok", "/tmp/tok")
    assert " --type whiteboard" in lark_cmds.media_download(
        "wb", "/tmp/wb", whiteboard=True
    )
    assert lark_cmds.AUTH_HINT == "调用 lark-cli 时不要加 --profile 或 --as。"


def test_document_from_fetch_json_and_plain():
    content, doc_id = document_from_fetch(
        '{"ok":true,"data":{"document":{"content":"# hi","document_id":"dox1"}}}'
    )
    assert content == "# hi"
    assert doc_id == "dox1"
    plain, empty = document_from_fetch("# already markdown")
    assert plain == "# already markdown"
    assert empty == ""
