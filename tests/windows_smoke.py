"""Executed on a real GitHub Actions Windows runner against a frozen EXE."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile

def main():
    binary = Path(sys.argv[1]).resolve()
    native_mcp = len(sys.argv) > 2 and sys.argv[2] == "native-mcp"
    flag = "--self-test-native-mcp" if native_mcp else "--self-test-mt5"
    assert binary.is_file(), binary
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder) / "mt5-import.json"
        result = subprocess.run([str(binary), flag, str(report)],
                                capture_output=True, text=True, timeout=100)
        assert report.exists(), (
            "EXE never created the smoke-test report. exit="
            + str(result.returncode) + ", stderr=" + str(result.stderr)
        )
        payload = json.loads(report.read_text(encoding="utf-8"))
        print("EXE:", binary.name, "returncode:", result.returncode)
        print(json.dumps(payload, indent=2))
        assert result.returncode == 0, payload
        assert payload.get("ok") is True, payload
        assert payload.get("frozen") is True, payload
        assert payload.get("module") == ("mcp.client.streamable_http" if native_mcp else "MetaTrader5"), payload

if __name__ == "__main__":
    main()
