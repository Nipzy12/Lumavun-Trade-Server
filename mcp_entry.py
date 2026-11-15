"""MCP stdio server entrypoint with the same packaged MT5 import test."""
from multiprocessing import freeze_support
import sys

def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test-mt5":
        from lumavun.diagnostics import self_test_mt5
        return self_test_mt5(sys.argv[2])
    from lumavun.mcp_server import main as mcp_main
    mcp_main()
    return 0

if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
