"""FastAPI application for Fabric Inventory Service."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.routing import Route

from traider.db import init_db, close_db
from traider.routes import fabrics, variants, movements, stock
from traider.routes.mcp import router as mcp_router, sse_transport


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # Startup
    init_db()
    yield
    # Shutdown
    close_db()


app = FastAPI(
    title="Fabric Inventory Service",
    description="Dead-simple fabric stock tracking service",
    version="1.0.0",
    lifespan=lifespan
)


# Register routers
app.include_router(fabrics.router)
app.include_router(variants.router)
app.include_router(movements.router)
app.include_router(stock.router)
app.include_router(mcp_router)


# Add the MCP messages endpoint as a raw ASGI route
# handle_post_message is an ASGI app that sends its own response,
# so we wrap it to extract ASGI primitives from the Request object
async def mcp_messages_handler(request: Request):
    """Wrapper to call handle_post_message as ASGI app."""
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)

app.router.routes.append(
    Route("/mcp/messages", endpoint=mcp_messages_handler, methods=["POST"])
)


@app.get("/")
def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "fabric-inventory"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
