"""CMD installer tests: only a user click may launch a fixed pip command."""
import pytest
from lumavun import mt5_installer


def test_windows_python_launcher_builds_official_package_command(monkeypatch):
    monkeypatch.setattr(mt5_installer.shutil, "which",
                        lambda executable: "C:/Windows/py.exe" if executable == "py" else None)
    command = mt5_installer.choose_install_command(platform="win32")
    assert command == "py -3 -m pip install --upgrade MetaTrader5"
    assert "pip install mt5" not in command


def test_windows_python_fallback(monkeypatch):
    monkeypatch.setattr(mt5_installer.shutil, "which",
                        lambda executable: "C:/Python/python.exe" if executable == "python" else None)
    assert mt5_installer.choose_install_command(platform="win32") == (
        "python -m pip install --upgrade MetaTrader5")


def test_missing_python_gives_actionable_error(monkeypatch):
    monkeypatch.setattr(mt5_installer.shutil, "which", lambda executable: None)
    with pytest.raises(RuntimeError, match="Python"):
        mt5_installer.choose_install_command(platform="win32")


def test_install_launcher_is_fixed_cmd_with_no_shell_injection(monkeypatch):
    monkeypatch.setattr(mt5_installer.shutil, "which",
                        lambda executable: "C:/Windows/py.exe" if executable == "py" else None)
    launches = []
    monkeypatch.setattr(mt5_installer.subprocess, "Popen",
                        lambda args, **kwargs: launches.append((args, kwargs)))
    cmd = mt5_installer.open_install_cmd(platform="win32")
    assert cmd == "py -3 -m pip install --upgrade MetaTrader5"
    assert len(launches) == 1
    args, kwargs = launches[0]
    assert args == ["cmd.exe", "/k", cmd]
    assert kwargs.get("shell", False) is False


def test_install_not_supported_on_non_windows(monkeypatch):
    monkeypatch.setattr(mt5_installer.shutil, "which", lambda executable: "/usr/bin/python3")
    with pytest.raises(RuntimeError, match="Windows"):
        mt5_installer.choose_install_command(platform="linux")
