"""FastAPI application for Fabric Inventory Service."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.routing import Route

from traider.db import init_db, close_db
from traider.routes import fabrics, variants, movements, stock
from traider.routes.mcp import handle_mcp_get, handle_mcp_post


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

# Add CORS middleware - allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routers
app.include_router(fabrics.router)
app.include_router(variants.router)
app.include_router(movements.router)
app.include_router(stock.router)

# Add MCP routes as raw Starlette routes (they handle their own ASGI responses)
# Using Route instead of Mount avoids the trailing slash redirect issue
app.routes.append(Route("/mcp", endpoint=handle_mcp_get, methods=["GET"]))
app.routes.append(Route("/mcp", endpoint=handle_mcp_post, methods=["POST"]))


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
