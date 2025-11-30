"""FastAPI application for Fabric Inventory Service."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from traider.db import init_db, close_db
from traider.routes import fabrics, variants, movements, stock
from traider.routes.mcp import mcp_asgi_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # Startup
    init_db()
    yield
    # Shutdown
    close_db()


# Create the FastAPI app first
_app = FastAPI(
    title="Fabric Inventory Service",
    description="Dead-simple fabric stock tracking service",
    version="1.0.0",
    lifespan=lifespan
)


# Add CORS middleware
_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routers
_app.include_router(fabrics.router)
_app.include_router(variants.router)
_app.include_router(movements.router)
_app.include_router(stock.router)


@_app.get("/")
def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "fabric-inventory"}


@_app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Wrap the FastAPI app with MCP routing
# This ASGI wrapper intercepts /mcp requests BEFORE FastAPI processes them
class MCPRoutingMiddleware:
    """ASGI middleware that routes /mcp requests to the MCP ASGI app."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            # Handle both /mcp and /mcp/
            if path == "/mcp" or path == "/mcp/":
                await mcp_asgi_app(scope, receive, send)
                return

        await self.app(scope, receive, send)


# Export the wrapped app
app = MCPRoutingMiddleware(_app)
