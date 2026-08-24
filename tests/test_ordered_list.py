"""Tests for ordered-list numbering preservation."""

from parser.ordered_list import fix_ordered_list_numbering


def test_renumbers_after_image_between_list_items():
    body = (
        "1. **first**\n"
        "2. **second**\n"
        "3. **third**\n"
        "4. **fourth**\n"
        "\n"
        "![diagram](/image/example.png)\n"
        "\n"
        "*Figure 6. caption text*\n"
        "\n"
        "1. **fifth**"
    )
    result = fix_ordered_list_numbering(body)
    assert "5. **fifth**" in result
    assert "1. **fifth**" not in result


def test_does_not_renumber_genuine_new_list():
    body = (
        "1. **only item**\n"
        "\n"
        "Plain paragraph between lists.\n"
        "\n"
        "1. **new list**"
    )
    result = fix_ordered_list_numbering(body)
    assert result.count("1. **") == 2


def test_renumbers_after_video_shortcode():
    body = (
        "1. one\n"
        "2. two\n"
        "\n"
        '{{< video src="/video/demo.mp4" >}}\n'
        "\n"
        "1. three"
    )
    result = fix_ordered_list_numbering(body)
    assert "3. three" in result


def test_wm_wrm_wpm_list_section():
    body = (
        "1. **云端通用模型基座**：text\n"
        "2. **WPM 蒸馏**：text\n"
        "3. **真机 rollout**：text\n"
        "4. **异常归因与接管决策**：text\n"
        "\n"
        "![panel](/image/e3607becfaba1358.png)\n"
        "\n"
        "*Figure 6. 多机器人监控与优先级人类干预交互界面*\n"
        "\n"
        "1. **数据回流形成持续优化闭环**：text"
    )
    result = fix_ordered_list_numbering(body)
    assert "5. **数据回流形成持续优化闭环**" in result
