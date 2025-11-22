"""CLI entry points for Traider Fabric Inventory Service."""
import os
import sys

import uvicorn


def main():
    """Main entry point - starts the FastAPI server."""
    serve()


def serve():
    """Start the FastAPI server."""
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload_flag = os.environ.get("RELOAD", "false").lower() == "true"

    # Verify DATABASE_URL is set
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL environment variable is not set", file=sys.stderr)
        print("Example: export DATABASE_URL=postgresql://user:pass@localhost:5432/inventory", file=sys.stderr)
        sys.exit(1)

    print(f"Starting Traider Fabric Inventory Service on {host}:{port}")
    print(f"MCP endpoint: http://{host}:{port}/mcp/sse")
    print(f"API docs: http://{host}:{port}/docs")

    uvicorn.run(
        "traider.main:app",
        host=host,
        port=port,
        reload=reload_flag,
    )


if __name__ == "__main__":
    main()
