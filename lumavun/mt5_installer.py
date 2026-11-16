"""Install the official MetaTrader5 package using a compatible local Python.

The frozen Windows executable bundles its own dependencies; installing into an
external interpreter does not repair a broken EXE build.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

PY_LAUNCHER_COMMAND = "py -3.11 -m pip install --upgrade MetaTrader5"
PYTHON_COMMAND = "python -m pip install --upgrade MetaTrader5"


def choose_install_command(*, platform: str | None = None) -> str:
    platform = sys.platform if platform is None else platform
    if platform != "win32":
        raise RuntimeError("Installer CMD hanya tersedia di Windows.")

    # Prefer the dedicated environment created by the Windows setup guide.
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "LumavunTradeServer" / ".venv" / "Scripts" / "python.exe"
    if os.environ.get("LOCALAPPDATA") and local.is_file():
        return f'"{local}" -m pip install --upgrade MetaTrader5'

    if shutil.which("py"):
        probe = subprocess.run(["py", "-3.11", "--version"], capture_output=True, check=False)
        if probe.returncode == 0:
            return PY_LAUNCHER_COMMAND
        raise RuntimeError(
            "Python 3.11 belum tersedia. Instal Python 3.11 x64 atau buat "
            "%LOCALAPPDATA%\\LumavunTradeServer\\.venv dahulu."
        )
    if shutil.which("python"):
        probe = subprocess.run(["python", "--version"], capture_output=True, text=True, check=False)
        if probe.returncode == 0 and probe.stdout.strip().startswith("Python 3.11."):
            return PYTHON_COMMAND
    raise RuntimeError(
        "Python 3.11 x64 tidak ditemukan. Pasang dari python.org. "
        "Menginstal pip ke Python sistem tidak memperbaiki dependensi EXE yang telah dikemas."
    )


def open_install_cmd(*, platform: str | None = None) -> str:
    command = choose_install_command(platform=platform)
    subprocess.Popen(["cmd.exe", "/k", command],
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return command
