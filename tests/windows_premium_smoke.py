"""Run the frozen premium GUI layout test and verify generated screenshot assets."""
import json
import os
from pathlib import Path
import subprocess
import sys

exe = Path(sys.argv[1]).resolve()
report = exe.parent / "premium-layout-smoke.json"
env = dict(os.environ)
env["QT_QPA_PLATFORM"] = "offscreen"
env["LUMAVUN_OFFICE_SMOKE"] = "1"
completed = subprocess.run(
    [str(exe), "--self-test-premium-ui", str(report)],
    env=env, capture_output=True, text=True, timeout=120,
)
assert report.exists(), (
    f"Windows UI failed before report generation: {completed.returncode}, {completed.stderr}"
)
result = json.loads(report.read_text(encoding="utf-8"))
print(json.dumps(result, indent=2))
assert completed.returncode == 0 and result["ok"], result
assert result["frozen"] is True
assert result["icon_loaded"] is True
assert result["mcp_field_min_height"] >= 30
assert result["mcp_scrollable"] is True
assert len(result["screenshots"]) == 6
for path in result["screenshots"].values():
    assert (exe.parent / path).is_file(), path
