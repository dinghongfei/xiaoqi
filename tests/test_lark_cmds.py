"""Tests for lark-cli command strings and fetch payload parsing."""

import json

from feishu import lark_cmds
from feishu.payload import document_from_fetch


def test_cmds_omit_profile_and_as():
    wiki = lark_cmds.inspect_wiki("WikiTok")
    assert wiki == "lark-cli drive +inspect --url 'WikiTok' --type wiki"
    assert "https://" not in wiki
    fetch = lark_cmds.fetch_markdown("doxcn1")
    assert "--doc 'doxcn1'" in fetch
    assert "https://" not in fetch
    assert "--as" not in fetch
    assert "--profile" not in lark_cmds.media_download("tok", "/tmp/tok")
    assert " --type whiteboard" in lark_cmds.media_download(
        "wb", "/tmp/wb", whiteboard=True
    )
    insert = lark_cmds.media_insert("doxcn1", "data/jobs/tok/cover.png")
    assert "--file 'data/jobs/tok/cover.png'" in insert
    assert "--as" not in insert
    assert "--profile" not in insert
    download = lark_cmds.download_skill("TokOne")
    assert "skills/download-feishu-doc/scripts/run.py" in download
    assert "--token 'TokOne'" in download
    assert "--kind wiki" not in download
    wiki_dl = lark_cmds.download_skill("WikiTok", kind="wiki")
    assert "--kind wiki" in wiki_dl
    assert "不要传 feishu.doubao.com" in lark_cmds.AUTH_HINT


def test_extract_doc_refs_from_doubao_url():
    from parser.message import extract_doc_refs

    refs = extract_doc_refs(
        "看这篇 https://feishu.doubao.com/docx/AbCToken 谢谢"
    )
    assert len(refs) == 1
    assert refs[0].kind == "docx"
    assert refs[0].token == "AbCToken"


def test_document_from_fetch_json_and_plain():
    content, doc_id = document_from_fetch(
        '{"ok":true,"data":{"document":{"content":"# hi","document_id":"dox1"}}}'
    )
    assert content == "# hi"
    assert doc_id == "dox1"
    plain, empty = document_from_fetch("# already markdown")
    assert plain == "# already markdown"
    assert empty == ""


def test_document_from_fetch_unwraps_v2_envelope_variants():
    xml = "<title>标题</title><p>正文</p>"
    wrapped = (
        '\ufeff{"ok":true,"data":{"document":{"content":'
        + json.dumps(xml)
        + ',"document_id":"dox2"}}}\nfetch done\n'
    )
    content, doc_id = document_from_fetch(wrapped)
    assert content == xml
    assert doc_id == "dox2"

    notice_then_doc = (
        '{"_notice":{"update":true}}\n'
        '{"ok":true,"data":{"document":{"content":"# from ndjson","document_id":"dox3"}}}'
    )
    content, doc_id = document_from_fetch(notice_then_doc)
    assert content == "# from ndjson"
    assert doc_id == "dox3"

    fenced = '```json\n{"data":{"document":{"content":"# fenced"}}}\n```'
    content, doc_id = document_from_fetch(fenced)
    assert content == "# fenced"
    assert doc_id == ""

    nested = json.dumps(
        {
            "data": {
                "document": {
                    "content": json.dumps(
                        {"data": {"document": {"content": "# inner", "document_id": "dox4"}}}
                    )
                }
            }
        }
    )
    content, doc_id = document_from_fetch(nested)
    assert content == "# inner"
    assert doc_id == "dox4"
