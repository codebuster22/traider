"""Routes for variants."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from psycopg import errors as pg_errors

from fastapi.responses import JSONResponse
from traider.models import (
    VariantCreate, VariantUpdate, Variant, VariantDetail, VariantSearchResult,
    VariantBatchRequest, VariantBatchResponse, VariantSearchBatchRequest, VariantSearchBatchResponse,
    VariantSearchItem, MessageResponse,
    LinkVariantsRequest, LinkVariantsResponse, LinkConfirmationRequired,
)
from traider import repo
from traider.cloudinary_utils import upload_image as cloudinary_upload

# Flat routes for backward compatibility and flexibility
router = APIRouter(prefix="/variants", tags=["variants"])

# Nested routes under fabrics
nested_router = APIRouter(tags=["variants"])


# ============================================================================
# Nested Routes (Primary) - /fabrics/{fabric_code}/variants
# ============================================================================

@nested_router.post("/fabrics/{fabric_code}/variants", response_model=VariantDetail, status_code=201)
def create_variant_nested(fabric_code: str, variant: VariantCreate):
    """Create a new variant under a fabric."""
    try:
        # Handle inline image upload
        image_url = variant.image_url
        if variant.image_data:
            try:
                upload_result = cloudinary_upload(
                    image_data=variant.image_data,
                    folder="traider/variants",
                    filename=f"{fabric_code}_{variant.color_code}"
                )
                image_url = upload_result['secure_url']
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Image upload failed: {str(e)}")

        result = repo.create_variant_by_fabric_code(
            fabric_code=fabric_code,
            color_code=variant.color_code,
            gsm=variant.gsm,
            width=variant.width,
            finish=variant.finish,
            image_url=image_url,
            gallery=variant.gallery
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"Fabric '{fabric_code}' not found")

        # Return with full details
        return repo.get_variant_by_codes(fabric_code, variant.color_code)
    except pg_errors.UniqueViolation:
        raise HTTPException(
            status_code=400,
            detail=f"Variant with color_code='{variant.color_code}' already exists for fabric '{fabric_code}'"
        )


@nested_router.get("/fabrics/{fabric_code}/variants", response_model=VariantSearchResult)
def list_variants_for_fabric(
    fabric_code: str,
    include_stock: bool = Query(False, description="Include stock information"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip")
):
    """List all variants for a specific fabric."""
    # First check if fabric exists
    fabric = repo.get_fabric_by_code(fabric_code)
    if fabric is None:
        raise HTTPException(status_code=404, detail=f"Fabric '{fabric_code}' not found")

    items, total = repo.search_variants(
        fabric_id=fabric["id"],
        include_stock=include_stock,
        limit=limit,
        offset=offset
    )

    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "total": total
    }


@nested_router.get("/fabrics/{fabric_code}/variants/{color_code}", response_model=VariantDetail)
def get_variant_by_codes(fabric_code: str, color_code: str):
    """Get a variant by fabric_code and color_code."""
    result = repo.get_variant_by_codes(fabric_code, color_code)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Variant '{color_code}' not found for fabric '{fabric_code}'"
        )
    return result


@nested_router.put("/fabrics/{fabric_code}/variants/{color_code}", response_model=VariantDetail)
def update_variant_by_codes(fabric_code: str, color_code: str, variant: VariantUpdate):
    """Update a variant by fabric_code and color_code."""
    # Handle inline image upload
    image_url = variant.image_url
    if variant.image_data:
        try:
            upload_result = cloudinary_upload(
                image_data=variant.image_data,
                folder="traider/variants",
                filename=f"{fabric_code}_{color_code}"
            )
            image_url = upload_result['secure_url']
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Image upload failed: {str(e)}")

    result = repo.update_variant_by_codes(
        fabric_code=fabric_code,
        color_code=color_code,
        new_color_code=variant.color_code,
        gsm=variant.gsm,
        width=variant.width,
        finish=variant.finish,
        image_url=image_url,
        gallery=variant.gallery
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Variant '{color_code}' not found for fabric '{fabric_code}'"
        )

    # Return with full details
    final_color = variant.color_code if variant.color_code else color_code
    return repo.get_variant_by_codes(fabric_code, final_color)


@nested_router.delete("/fabrics/{fabric_code}/variants/{color_code}", response_model=MessageResponse, status_code=200)
def delete_variant_by_codes(fabric_code: str, color_code: str):
    """Delete a variant by fabric_code and color_code."""
    deleted = repo.delete_variant_by_codes(fabric_code, color_code)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Variant '{color_code}' not found for fabric '{fabric_code}'"
        )
    return MessageResponse(message=f"Variant '{color_code}' deleted from fabric '{fabric_code}'")


# ============================================================================
# Batch Routes - /fabrics/{fabric_code}/variants/batch
# ============================================================================

@nested_router.post(
    "/fabrics/{fabric_code}/variants/batch",
    response_model=VariantBatchResponse,
    status_code=201,
    responses={207: {"model": VariantBatchResponse, "description": "Partial success - some variants failed"}}
)
def create_variants_batch(fabric_code: str, batch: VariantBatchRequest):
    """
    Create multiple variants under a single fabric.

    Returns 201 if all succeed, 207 if partial success.
    Max batch size: 100 variants.
    """
    # Validate batch size
    if len(batch.variants) > 100:
        raise HTTPException(status_code=400, detail="Max batch size is 100 variants")

    if len(batch.variants) == 0:
        raise HTTPException(status_code=400, detail="At least one variant is required")

    # Convert to dicts for repo
    variants = [v.model_dump() for v in batch.variants]

    fabric_id, created, failed = repo.create_variants_batch(fabric_code, variants)

    if fabric_id is None:
        raise HTTPException(status_code=404, detail=f"Fabric '{fabric_code}' not found")

    response = {
        "created": created,
        "failed": failed,
        "summary": {
            "total": len(batch.variants),
            "created": len(created),
            "failed": len(failed)
        }
    }

    # Return 207 Multi-Status if partial success
    if failed and created:
        return JSONResponse(status_code=207, content=response)

    # Return 201 if all succeeded (or empty batch)
    return JSONResponse(status_code=201, content=response)


@nested_router.post("/fabrics/{fabric_code}/variants/search/batch", response_model=VariantSearchBatchResponse)
def search_variants_batch(fabric_code: str, request: VariantSearchBatchRequest):
    """
    Search multiple variants by color codes within a fabric.

    Returns found variants and list of not found color codes.
    """
    if len(request.color_codes) == 0:
        raise HTTPException(status_code=400, detail="At least one color_code is required")

    fabric_id, found, not_found = repo.search_variants_batch(
        fabric_code=fabric_code,
        color_codes=request.color_codes,
        include_stock=request.include_stock
    )

    if fabric_id is None:
        raise HTTPException(status_code=404, detail=f"Fabric '{fabric_code}' not found")

    # Convert found items to proper format with VariantSearchItem
    found_items = []
    for item in found:
        variant_data = item["variant"]
        found_items.append({
            "color_code": item["color_code"],
            "variant": VariantSearchItem(
                id=variant_data["id"],
                fabric_id=variant_data["fabric_id"],
                fabric_code=variant_data["fabric_code"],
                fabric_name=variant_data["fabric_name"],
                fabric_image_url=variant_data.get("fabric_image_url"),
                fabric_gallery=variant_data.get("fabric_gallery", {}),
                color_code=variant_data["color_code"],
                finish=variant_data["finish"],
                gsm=variant_data.get("gsm"),
                width=variant_data.get("width"),
                variant_image_url=variant_data.get("variant_image_url"),
                variant_gallery=variant_data.get("variant_gallery", {})
            ),
            "stock": item.get("stock")
        })

    return {
        "found": found_items,
        "not_found": not_found,
        "summary": {
            "total": len(request.color_codes),
            "found": len(found),
            "not_found": len(not_found),
            "failed": 0
        }
    }


# ============================================================================
# Variant Linking - /fabrics/{fabric_code}/variants/link
# ============================================================================

@nested_router.post(
    "/fabrics/{fabric_code}/variants/link",
    responses={
        200: {"model": LinkVariantsResponse},
        404: {"description": "No matching variants"},
        409: {"model": LinkConfirmationRequired, "description": "Confirmation required for destructive merge"},
    },
)
def link_variants_route(fabric_code: str, request: LinkVariantsRequest):
    """Link multiple color codes to the same fabric variant.

    The first code in `color_codes` is the user-intended primary. See spec §6.3.
    """
    result = repo._execute_link(fabric_code, request.color_codes, confirm=request.confirm)
    if result["result"] == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"No matching variants in fabric '{fabric_code}' for any of the given codes",
        )
    if result["result"] == "confirmation_required":
        # Translate internal `result` discriminator → public `status` (per spec §6.3 Pydantic shape)
        public_body = {
            "status": "confirmation_required",
            "plan": result["plan"],
            "message": result["message"],
        }
        return JSONResponse(status_code=409, content=public_body)
    return result


# ============================================================================
# Variant Alias Routes - /fabrics/{fabric_code}/variants/{color_code}/aliases
# ============================================================================

@nested_router.get(
    "/fabrics/{fabric_code}/variants/{color_code}/aliases",
    response_model=list[str],
)
def get_variant_aliases_route(fabric_code: str, color_code: str):
    """List all aliases for a variant."""
    variant_id = repo.resolve_variant_id(fabric_code, color_code)
    if variant_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"Variant '{color_code}' not found in fabric '{fabric_code}'",
        )
    return repo.list_variant_aliases(variant_id)


@nested_router.delete(
    "/fabrics/{fabric_code}/variants/{color_code}/aliases/{alias}",
    response_model=MessageResponse,
)
def delete_variant_alias_route(fabric_code: str, color_code: str, alias: str):
    """Delete a specific alias from a variant."""
    variant_id = repo.resolve_variant_id(fabric_code, color_code)
    if variant_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"Variant '{color_code}' not found in fabric '{fabric_code}'",
        )
    removed = repo.remove_variant_alias(variant_id, alias)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Alias '{alias}' not found on variant '{color_code}'",
        )
    return MessageResponse(message=f"Alias '{alias}' removed")


# ============================================================================
# Flat Routes (Fallback) - /variants
# ============================================================================

@router.get("", response_model=VariantSearchResult)
def search_variants(
    q: Optional[str] = Query(None, description="Free text search across color_code, finish, fabric_code, fabric_name"),
    fabric_id: Optional[int] = Query(None, description="Filter by fabric ID"),
    fabric_code: Optional[str] = Query(None, description="Filter by fabric code (partial match)"),
    color_code: Optional[str] = Query(None, description="Filter by color code (partial match)"),
    gsm: Optional[int] = Query(None, description="Filter by exact GSM"),
    gsm_min: Optional[int] = Query(None, description="Filter by minimum GSM"),
    gsm_max: Optional[int] = Query(None, description="Filter by maximum GSM"),
    width: Optional[int] = Query(None, description="Filter by exact width"),
    width_min: Optional[int] = Query(None, description="Filter by minimum width"),
    width_max: Optional[int] = Query(None, description="Filter by maximum width"),
    finish: Optional[str] = Query(None, description="Filter by finish (partial match)"),
    include_stock: bool = Query(False, description="Include stock information"),
    in_stock_only: bool = Query(False, description="Only return variants with stock > 0 (implies include_stock)"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    sort_by: str = Query("id", description="Sort field: id, fabric_code, color_code, gsm, width, finish, on_hand_m"),
    sort_dir: str = Query("asc", description="Sort direction: asc or desc")
):
    """Search variants with optional filters, stock, and pagination."""
    items, total = repo.search_variants(
        q=q,
        fabric_id=fabric_id,
        fabric_code=fabric_code,
        color_code=color_code,
        gsm=gsm,
        gsm_min=gsm_min,
        gsm_max=gsm_max,
        width=width,
        width_min=width_min,
        width_max=width_max,
        finish=finish,
        include_stock=include_stock,
        in_stock_only=in_stock_only,
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


@router.get("/{variant_id}", response_model=VariantDetail)
def get_variant(variant_id: int):
    """Get a variant by ID with joined fabric details (fallback)."""
    result = repo.get_variant_detail(variant_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Variant with id {variant_id} not found")
    return result
