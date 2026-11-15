"""Windows console executable for the LUMAVUN MCP HTTP Gateway."""
import sys
from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test-mt5":
        from lumavun.diagnostics import self_test_mt5
        sys.exit(self_test_mt5(sys.argv[2]))
    from lumavun.gateway_server import main
    sys.exit(main())
