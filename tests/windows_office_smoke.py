"""GitHub Windows runner validates the frozen PySide6 Office UI and its preview."""
import json
import os
from pathlib import Path
import subprocess
import sys

exe = Path(sys.argv[1]).resolve()
report = exe.parent / "office-smoke.json"
env = dict(os.environ)
env["QT_QPA_PLATFORM"] = "offscreen"
env["LUMAVUN_OFFICE_SMOKE"] = "1"
result = subprocess.run([str(exe), "--self-test-office", str(report)],
                        capture_output=True, text=True, timeout=120, env=env)
assert report.is_file(), f"No GUI report. Exit {result.returncode} {result.stderr}"
data = json.loads(report.read_text(encoding="utf-8"))
print(data)
assert result.returncode == 0 and data["ok"], data
assert data["frozen"] is True
assert data["first_tab"] == "Trading Office"
assert data["preview_bytes"] > 1000
assert (exe.parent / data["preview"]).is_file()
