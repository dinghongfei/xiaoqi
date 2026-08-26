"""Tests for media index builder."""

from media.index import MediaIndex, build_media_index_from_xml


def test_build_media_index_from_xml():
    xml = (
        '<img src="TokenABC" href="https://example.feishu.cn/authcode?code=abc"/>'
        '<whiteboard token="BoardToken123"></whiteboard>'
        '<video token="VideoToken" href="https://example.feishu.cn/video?code=v1"/>'
        '<source token="SourceVideoToken" href="https://example.feishu.cn/video?code=s1" mime="video/mp4"/>'
        '<file token="FileToken" href="https://example.feishu.cn/file?code=f1"/>'
    )
    index = build_media_index_from_xml(xml)

    assert index.by_url["https://example.feishu.cn/authcode?code=abc"] == "TokenABC"
    assert index.by_prefix["TokenABC"] == "TokenABC"
    assert index.by_prefix["TokenABC"][:8] == "TokenABC"[:8]
    assert index.lookup_by_url("https://example.feishu.cn/authcode?code=abc") == "TokenABC"
    assert index.lookup_by_relative_path("images/image-TokenABC.png") == "TokenABC"
    assert index.by_prefix["BoardTok"] == "BoardToken123"
    assert index.by_url["https://example.feishu.cn/video?code=v1"] == "VideoToken"
    assert index.by_prefix["VideoTok"] == "VideoToken"
    assert index.by_url["https://example.feishu.cn/video?code=s1"] == "SourceVideoToken"
    assert index.by_prefix["SourceVi"] == "SourceVideoToken"
    assert index.by_url["https://example.feishu.cn/file?code=f1"] == "FileToken"


def test_build_media_index_registers_http_src():
    xml = '<img src="https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=abc"/>'
    index = build_media_index_from_xml(xml)
    url = "https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=abc"
    assert index.lookup_by_url(url) == url


def test_lookup_by_relative_path_prefix():
    index = MediaIndex(by_prefix={"IjpLbMxl": "IjpLbMxljoZvRQxZrEucXAhGnrf"})
    assert (
        index.lookup_by_relative_path("images/image-IjpLbMxl.png")
        == "IjpLbMxljoZvRQxZrEucXAhGnrf"
    )
