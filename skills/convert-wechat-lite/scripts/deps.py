"""Pre-check third-party packages and install via pip if missing."""

from __future__ import annotations

import importlib
import site
import subprocess
import sys
from pathlib import Path

_REQUIRED = ("markdown", "pygments", "httpx")
_REQUIREMENTS = Path(__file__).resolve().parent / "requirements.txt"


def _missing() -> list[str]:
    absent: list[str] = []
    for name in _REQUIRED:
        try:
            importlib.import_module(name)
        except ImportError:
            absent.append(name)
    return absent


def _refresh_sys_path() -> None:
    """Pick up packages installed into the user site mid-process."""
    try:
        user_site = site.getusersitepackages()
    except Exception:
        user_site = ""
    if user_site and user_site not in sys.path:
        sys.path.append(user_site)
    importlib.invalidate_caches()


def ensure() -> None:
    """Import-check; on failure run ``python3 -m pip install -r requirements.txt``."""
    if not _missing():
        return
    if not _REQUIREMENTS.is_file():
        raise RuntimeError(f"缺少依赖文件：{_REQUIREMENTS}")
    print(f"正在安装依赖：{_REQUIREMENTS}", flush=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(_REQUIREMENTS)],
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("pip 安装依赖失败，请检查网络或 Python 环境")
    _refresh_sys_path()
    still = _missing()
    if still:
        raise RuntimeError(f"依赖仍不可用：{', '.join(still)}")
