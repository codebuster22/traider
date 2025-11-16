"""Routes for fabrics."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from psycopg import errors as pg_errors

from traider.models import FabricCreate, Fabric, FabricSearchResult
from traider import repo

router = APIRouter(prefix="/fabrics", tags=["fabrics"])


@router.post("", response_model=Fabric, status_code=201)
def create_fabric(fabric: FabricCreate):
    """Create a new fabric."""
    try:
        result = repo.create_fabric(
            fabric_code=fabric.fabric_code,
            name=fabric.name,
            image_url=fabric.image_url
        )
        return result
    except pg_errors.UniqueViolation:
        raise HTTPException(status_code=400, detail=f"Fabric code '{fabric.fabric_code}' already exists")


@router.get("", response_model=FabricSearchResult)
def search_fabrics(
    q: Optional[str] = Query(None, description="Free text search across fabric_code and name"),
    fabric_code: Optional[str] = Query(None, description="Filter by fabric code (partial match)"),
    name: Optional[str] = Query(None, description="Filter by name (partial match)"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    sort_by: str = Query("fabric_code", description="Sort field: id, fabric_code, name"),
    sort_dir: str = Query("asc", description="Sort direction: asc or desc")
):
    """Search fabrics with optional filters and pagination."""
    items, total = repo.search_fabrics(
        q=q,
        fabric_code=fabric_code,
        name=name,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir
    )

    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "total": total
    }
