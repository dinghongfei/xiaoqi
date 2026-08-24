"""Tests for subprocess helper."""

from unittest.mock import MagicMock, patch

import pytest

from pipeline.subprocess_util import run_command


def test_run_command_success():
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = "ok"
    completed.stderr = ""

    with patch("pipeline.subprocess_util.subprocess.run", return_value=completed):
        result = run_command(["echo", "hi"], cwd="/tmp", timeout=5, step_name="Echo")

    assert result.status == "ok"


def test_run_command_failure_with_stderr():
    completed = MagicMock()
    completed.returncode = 1
    completed.stdout = ""
    completed.stderr = "line1\nsomething went wrong"

    with patch("pipeline.subprocess_util.subprocess.run", return_value=completed):
        result = run_command(["false"], cwd="/tmp", timeout=5, step_name="Fail")

    assert result.status == "error"
    assert "something went wrong" in result.message


def test_run_command_timeout():
    import subprocess

    with patch(
        "pipeline.subprocess_util.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["sleep"], timeout=1),
    ):
        result = run_command(["sleep", "9"], cwd="/tmp", timeout=1, step_name="Sleep")

    assert result.status == "error"
    assert "超时" in result.message
