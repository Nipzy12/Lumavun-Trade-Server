"""Console entrypoint for local MCP stdio clients."""
from multiprocessing import freeze_support
from lumavun.mcp_server import main

if __name__ == "__main__":
    freeze_support()
    main()
