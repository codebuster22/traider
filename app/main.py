"""FastAPI application for Fabric Inventory Service."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.db import init_db, close_db
from app.routes import fabrics, variants, movements, stock


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
