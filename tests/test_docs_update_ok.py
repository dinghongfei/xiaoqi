"""Tests for docs +update success/failure handling."""

import pytest

from feishu.client import (
    FeishuAPIError,
    auth_result_from_payload,
    ensure_docs_update_ok,
    find_enrichment_block_ids,
    format_docs_update_failure,
    is_edit_permission_error,
    list_top_level_block_ids,
)


def test_ensure_docs_update_ok_success():
    ensure_docs_update_ok({"ok": True, "data": {"result": "success"}})
    ensure_docs_update_ok({"ok": True, "data": {}})


def test_ensure_docs_update_ok_failed_permission():
    payload = {
        "ok": True,
        "data": {
            "result": "failed",
            "warnings": [
                "degrade_code=4030004,msg=Document operation failed: No permission "
                "to operate on this document: the current user lacks view or edit access"
            ],
        },
    }
    with pytest.raises(FeishuAPIError, match="编辑权限") as exc:
        ensure_docs_update_ok(payload)
    assert "可编辑" in str(exc.value)


def test_format_docs_update_failure_generic():
    message = format_docs_update_failure(
        {"data": {"result": "failed", "warnings": ["something else broke"]}}
    )
    assert "写回文档失败" in message
    assert "something else broke" in message


def test_is_edit_permission_error():
    assert is_edit_permission_error("degrade_code=4030004,msg=No permission")
    assert is_edit_permission_error("机器人没有该文档的编辑权限")
    assert not is_edit_permission_error("写回后未找到「属性」区块")


def test_auth_result_from_payload():
    assert auth_result_from_payload({"data": {"auth_result": True}}) is True
    assert auth_result_from_payload({"data": {"auth_result": False}}) is False
    assert auth_result_from_payload({"data": {}}) is None


def test_list_top_level_block_ids():
    xml = (
        '<title>标题</title>'
        '<p id="blk1">一段</p>'
        '<table id="blk2"><tr><td><p id="cell1">x</p></td></tr></table>'
        '<hr id="blk3"/>'
    )
    assert list_top_level_block_ids(xml) == ["blk1", "blk2", "blk3"]


def test_find_enrichment_block_ids_skips_nested_cells():
    xml = (
        '<h1 id="old1">导读</h1>'
        '<p id="old2">正文</p>'
        '<h1 id="attr">属性</h1>'
        '<table id="tbl"><tr><td><p id="c1">slug</p></td>'
        '<td><p id="c2">说明</p></td><td><p id="c3">val</p></td></tr></table>'
        '<h1 id="img">图片</h1>'
        '<p id="prompt">封面提示词</p>'
        '<hr id="line"/>'
    )
    assert find_enrichment_block_ids(xml) == ["attr", "tbl", "img", "prompt", "line"]
