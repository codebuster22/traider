"""Routes for fabrics."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from psycopg import errors as pg_errors

from traider.models import FabricCreate, FabricUpdate, Fabric, FabricSearchResult, AliasCreate, MessageResponse
from traider import repo
from traider.cloudinary_utils import upload_image as cloudinary_upload

router = APIRouter(prefix="/fabrics", tags=["fabrics"])


@router.post("", response_model=Fabric, status_code=201)
def create_fabric(fabric: FabricCreate):
    """Create a new fabric with optional aliases."""
    try:
        # Handle inline image upload
        image_url = fabric.image_url
        if fabric.image_data:
            try:
                upload_result = cloudinary_upload(
                    image_data=fabric.image_data,
                    folder="traider/fabrics",
                    filename=fabric.fabric_code
                )
                image_url = upload_result['secure_url']
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Image upload failed: {str(e)}")

        result = repo.create_fabric(
            fabric_code=fabric.fabric_code,
            name=fabric.name,
            image_url=image_url,
            gallery=fabric.gallery,
            aliases=fabric.aliases
        )
        return result
    except pg_errors.UniqueViolation:
        raise HTTPException(status_code=400, detail=f"Fabric code '{fabric.fabric_code}' already exists")


@router.get("/{fabric_code}", response_model=Fabric)
def get_fabric(fabric_code: str):
    """Get a fabric by its fabric_code."""
    result = repo.get_fabric_by_code(fabric_code)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Fabric '{fabric_code}' not found")
    return result


@router.put("/{fabric_code}", response_model=Fabric)
def update_fabric(fabric_code: str, fabric: FabricUpdate):
    """Update an existing fabric by fabric_code."""
    # Look up fabric by code first
    existing = repo.get_fabric_by_code(fabric_code)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Fabric '{fabric_code}' not found")

    # Handle inline image upload
    image_url = fabric.image_url
    if fabric.image_data:
        try:
            upload_result = cloudinary_upload(
                image_data=fabric.image_data,
                folder="traider/fabrics",
                filename=fabric_code
            )
            image_url = upload_result['secure_url']
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Image upload failed: {str(e)}")

    result = repo.update_fabric(
        fabric_id=existing["id"],
        name=fabric.name,
        image_url=image_url,
        gallery=fabric.gallery
    )
    return result


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


# ============================================================================
# Alias Management
# ============================================================================

@router.get("/{fabric_code}/aliases", response_model=list[str])
def get_aliases(fabric_code: str):
    """Get all aliases for a fabric."""
    fabric = repo.get_fabric_by_code(fabric_code)
    if fabric is None:
        raise HTTPException(status_code=404, detail=f"Fabric '{fabric_code}' not found")
    return repo.get_fabric_aliases(fabric["id"])


@router.post("/{fabric_code}/aliases", response_model=MessageResponse, status_code=201)
def add_alias(fabric_code: str, body: AliasCreate):
    """Add an alias to a fabric."""
    fabric = repo.get_fabric_by_code(fabric_code)
    if fabric is None:
        raise HTTPException(status_code=404, detail=f"Fabric '{fabric_code}' not found")

    added = repo.add_fabric_alias(fabric["id"], body.alias)
    if not added:
        raise HTTPException(status_code=409, detail=f"Alias '{body.alias}' already exists for this fabric")
    return MessageResponse(message=f"Alias '{body.alias}' added successfully")


@router.delete("/{fabric_code}/aliases/{alias}", response_model=MessageResponse, status_code=200)
def remove_alias(fabric_code: str, alias: str):
    """Remove an alias from a fabric."""
    fabric = repo.get_fabric_by_code(fabric_code)
    if fabric is None:
        raise HTTPException(status_code=404, detail=f"Fabric '{fabric_code}' not found")

    removed = repo.remove_fabric_alias(fabric["id"], alias)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Alias '{alias}' not found for this fabric")
    return MessageResponse(message=f"Alias '{alias}' removed successfully")
