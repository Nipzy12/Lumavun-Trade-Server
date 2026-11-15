"""GUI executable entrypoint with a CI-verifiable MT5 import smoke test."""
from multiprocessing import freeze_support
import sys

def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test-mt5":
        from lumavun.diagnostics import self_test_mt5
        return self_test_mt5(sys.argv[2])
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test-native-mcp":
        from lumavun.diagnostics import self_test_native_mcp
        return self_test_native_mcp(sys.argv[2])
    from lumavun.gui import main as gui_main
    gui_main()
    return 0

if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
