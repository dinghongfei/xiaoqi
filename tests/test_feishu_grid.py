"""Tests for Feishu grid/column conversion."""

from parser.feishu_grid import convert_feishu_grid_to_shortcode


def test_convert_single_line_grid_with_videos():
    body = (
        '<grid><column width-ratio="0.200000">'
        '{{< video src="/video/a.mp4" >}}<p></p></column>'
        '<column width-ratio="0.200000">'
        '{{< video src="/video/b.mp4" >}}<p></p></column></grid>'
    )
    result = convert_feishu_grid_to_shortcode(body)
    assert "{{< grid >}}" in result
    assert "{{< /grid >}}" in result
    assert result.count("{{< column") == 2
    assert result.count("{{< /column >}}") == 2
    assert "<grid" not in result.lower()
    assert "<p></p>" not in result


def test_convert_multiline_grid():
    body = (
        "<grid>\n"
        '<column width-ratio="0.2"><figure>video</figure></column>\n'
        '<column width-ratio="0.2"><figure>video2</figure></column>\n'
        "</grid>"
    )
    result = convert_feishu_grid_to_shortcode(body)
    assert "{{< grid >}}" in result
    assert "video2" in result
    assert "<column" not in result.lower()
