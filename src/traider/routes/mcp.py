"""MCP SSE endpoint for HTTP-based MCP connections."""
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount, Router

from traider.mcp import mcp_server


# Create SSE transport with the message endpoint path (full path from root)
sse_transport = SseServerTransport("/mcp/messages")


async def handle_sse(request):
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


# Create Starlette app for MCP routes (to be mounted in FastAPI at /mcp)
# Use Router with redirect_slashes=False to prevent 307 redirects
mcp_router = Router(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Route("/messages", endpoint=sse_transport.handle_post_message, methods=["POST"]),
    ],
    redirect_slashes=False
)

mcp_app = Starlette(routes=mcp_router.routes)
