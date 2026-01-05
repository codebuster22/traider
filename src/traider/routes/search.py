"""Routes for unified search."""
from fastapi import APIRouter, Query

from traider.models import UnifiedSearchResult
from traider import repo

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=UnifiedSearchResult)
def unified_search(
    q: str = Query(..., min_length=1, description="Search query"),
    include_fabrics: bool = Query(True, description="Include fabrics in results"),
    include_variants: bool = Query(True, description="Include variants in results"),
    include_stock: bool = Query(False, description="Include stock info for variants"),
    limit: int = Query(20, ge=1, le=100, description="Max results per category")
):
    """
    Unified search across fabrics and variants.

    Searches:
    - Fabrics: by fabric_code, name, and aliases
    - Variants: by color_code, finish, and parent fabric (name, code, aliases)

    Returns both fabrics and variants matching the query.
    """
    result = repo.unified_search(
        q=q,
        include_fabrics=include_fabrics,
        include_variants=include_variants,
        include_stock=include_stock,
        limit=limit
    )

    # Convert to Pydantic models
    fabrics = []
    for f in result.get("fabrics", []):
        fabrics.append({
            "fabric_code": f["fabric_code"],
            "name": f["name"],
            "aliases": f.get("aliases", []),
            "image_url": f.get("image_url"),
            "gallery": f.get("gallery", {}),
            "match_source": f.get("match_source", "name")
        })

    variants = []
    for v in result.get("variants", []):
        variants.append({
            "id": v["id"],
            "fabric_id": v["fabric_id"],
            "fabric_code": v["fabric_code"],
            "fabric_name": v["fabric_name"],
            "fabric_image_url": v.get("fabric_image_url"),
            "fabric_gallery": v.get("fabric_gallery", {}),
            "color_code": v["color_code"],
            "finish": v["finish"],
            "gsm": v.get("gsm"),
            "width": v.get("width"),
            "variant_image_url": v.get("variant_image_url"),
            "variant_gallery": v.get("variant_gallery", {}),
            "on_hand_m": v.get("on_hand_m"),
            "on_hand_rolls": v.get("on_hand_rolls"),
            "updated_at": v.get("updated_at")
        })

    return {
        "fabrics": fabrics,
        "variants": variants
    }
