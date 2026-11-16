"""Install official MetaTrader5 Python package in a visible Windows CMD."""
from __future__ import annotations
import shutil
import subprocess
import sys

PY_LAUNCHER_COMMAND = "py -3 -m pip install --upgrade MetaTrader5"
PYTHON_COMMAND = "python -m pip install --upgrade MetaTrader5"

def choose_install_command(*, platform: str | None = None) -> str:
    platform = sys.platform if platform is None else platform
    if platform != "win32":
        raise RuntimeError("Installer CMD hanya tersedia di Windows.")
    if shutil.which("py"):
        return PY_LAUNCHER_COMMAND
    if shutil.which("python"):
        return PYTHON_COMMAND
    raise RuntimeError("Python tidak ditemukan di PATH. Pasang Python 64-bit dari python.org lalu coba lagi. Pip di Python sistem tidak memperbaiki dependensi yang telah dikemas di EXE.")

def open_install_cmd(*, platform: str | None = None) -> str:
    command = choose_install_command(platform=platform)
    subprocess.Popen(["cmd.exe", "/k", command],
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return command
