"""MCP SSE endpoint for HTTP-based MCP connections."""
from fastapi import APIRouter, Request
from mcp.server.sse import SseServerTransport

from traider.mcp import mcp_server


router = APIRouter(prefix="/mcp", tags=["mcp"])

# Create SSE transport with the message endpoint path
# This path is sent to clients, so it must be the full path they should POST to
sse_transport = SseServerTransport("/mcp/messages")


@router.get("/sse")
async def handle_sse(request: Request):
    """
    SSE endpoint for MCP connections.

    This endpoint allows MCP clients (like Claude Desktop) to connect via HTTP/SSE
    instead of using stdio transport.

    Usage in Claude Desktop/Claude Code config:
    {
      "mcpServers": {
        "fabric-inventory": {
          "url": "https://your-domain.com/mcp/sse"
        }
      }
    }
    """
    async with sse_transport.connect_sse(
        request.scope,
        request.receive,
        request._send
    ) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options()
        )


# Note: The /mcp/messages POST endpoint is added in main.py as a raw Starlette route
# because sse_transport.handle_post_message is an ASGI app that sends its own response.
# FastAPI routes would try to send an additional response, causing conflicts.
