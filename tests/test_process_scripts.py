"""start.sh / stop.sh must free same-named processes and the preview port."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROCESS_SH = REPO / "scripts" / "process.sh"
START_SH = REPO / "scripts" / "start.sh"
STOP_SH = REPO / "scripts" / "stop.sh"


def _run_stop(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", "source \"$PROCESS_SH\"; stop_project_services"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _base_env(tmp_path: Path, *, port: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PROJECT_ROOT"] = str(tmp_path)
    env["DATA_DIR"] = str(tmp_path / "data" / "run")
    env["PREVIEW_PORT"] = port
    env["PROCESS_SH"] = str(PROCESS_SH)
    env["XIAOQI_SKIP_NAME_MATCH"] = "1"
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_scripts_stop_before_restart():
    start = START_SH.read_text(encoding="utf-8")
    stop = STOP_SH.read_text(encoding="utf-8")
    helper = PROCESS_SH.read_text(encoding="utf-8")
    assert "source" in start and "process.sh" in start
    assert "stop_project_services" in start
    assert "已在运行" not in start
    assert "stop_project_services" in stop
    assert "bot preview-http" in helper
    assert "bot serve" in helper
    assert "lsof" in helper
    assert "_pids_on_port" in helper
    assert "_pids_by_name" in helper


def test_stop_kills_pidfile_process(tmp_path: Path):
    run_dir = tmp_path / "data" / "run"
    run_dir.mkdir(parents=True)
    proc = subprocess.Popen(["sleep", "60"])
    try:
        (run_dir / "bot.pid").write_text(str(proc.pid), encoding="utf-8")
        result = _run_stop(_base_env(tmp_path, port=str(_free_port())))
        assert result.returncode == 0, result.stdout + result.stderr
        proc.wait(timeout=5)
        assert proc.poll() is not None
        assert not (run_dir / "bot.pid").exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)


def test_stop_kills_process_listening_on_preview_port(tmp_path: Path):
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(tmp_path),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.05)
        else:
            raise AssertionError("dummy preview server did not bind")

        result = _run_stop(_base_env(tmp_path, port=str(port)))
        assert result.returncode == 0, result.stdout + result.stderr
        proc.wait(timeout=5)
        assert proc.poll() is not None
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            assert sock.connect_ex(("127.0.0.1", port)) != 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
