"""Routes for variants."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from psycopg import errors as pg_errors

from app.models import VariantCreate, Variant, VariantDetail, VariantSearchResult
from app import repo

router = APIRouter(prefix="/variants", tags=["variants"])


@router.post("", response_model=Variant, status_code=201)
def create_variant(variant: VariantCreate):
    """Create a new variant."""
    try:
        result = repo.create_variant(
            fabric_id=variant.fabric_id,
            color_code=variant.color_code,
            gsm=variant.gsm,
            width=variant.width,
            finish=variant.finish,
            image_url=variant.image_url
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"Fabric with id {variant.fabric_id} not found")
        return result
    except pg_errors.UniqueViolation:
        raise HTTPException(
            status_code=400,
            detail=f"Variant with fabric_id={variant.fabric_id}, color_code={variant.color_code}, "
                   f"gsm={variant.gsm}, width={variant.width}, finish={variant.finish} already exists"
        )


@router.get("/{variant_id}", response_model=VariantDetail)
def get_variant(variant_id: int):
    """Get a variant by ID with joined fabric details."""
    result = repo.get_variant_detail(variant_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Variant with id {variant_id} not found")
    return result


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
