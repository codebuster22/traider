"""Routes for stock movements."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from traider.models import (
    MovementCreate,
    MovementResponse,
    MovementBatchRequest,
    MovementBatchResponse,
    MovementHistoryResponse,
    CancelMovementRequest,
    CancelMovementResponse,
)
from traider import repo

router = APIRouter(prefix="/movements", tags=["movements"])


# ============================================================================
# Movement History & Cancellation
# ============================================================================

@router.get("", response_model=MovementHistoryResponse)
def list_movements(
    fabric_code: Optional[str] = Query(None, description="Filter by fabric code (exact match)"),
    color_code: Optional[str] = Query(None, description="Filter by color code (exact match)"),
    movement_type: Optional[str] = Query(None, description="Filter by type: RECEIPT, ISSUE, ADJUST"),
    date_from: Optional[datetime] = Query(None, description="Movements on or after this date"),
    date_to: Optional[datetime] = Query(None, description="Movements on or before this date"),
    min_qty: Optional[float] = Query(None, description="Minimum absolute quantity in meters"),
    max_qty: Optional[float] = Query(None, description="Maximum absolute quantity in meters"),
    document_id: Optional[str] = Query(None, description="Filter by document reference"),
    include_cancelled: bool = Query(False, description="Include cancelled movements"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_by: str = Query("ts", description="Sort field: ts, delta_qty_m, movement_type"),
    sort_dir: str = Query("desc", description="Sort direction: asc, desc"),
):
    """Search movement history with optional filters, pagination, and sorting."""
    items, total = repo.search_movements(
        fabric_code=fabric_code,
        color_code=color_code,
        movement_type=movement_type,
        date_from=date_from,
        date_to=date_to,
        min_qty=min_qty,
        max_qty=max_qty,
        document_id=document_id,
        include_cancelled=include_cancelled,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{movement_id}/cancel", response_model=CancelMovementResponse)
def cancel_movement_route(
    movement_id: int,
    request: Optional[CancelMovementRequest] = None,
):
    """
    Cancel a movement (soft delete) and reverse its effect on stock balance.

    Returns 200 on success, 400 if already cancelled, 404 if not found.
    """
    reason = request.reason if request else None

    try:
        result = repo.cancel_movement(movement_id, reason=reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result is None:
        raise HTTPException(status_code=404, detail=f"Movement {movement_id} not found")

    return result


# ============================================================================
# Create Movements
# ============================================================================

@router.post("/receive", response_model=MovementResponse, status_code=201)
def receive(movement: MovementCreate):
    """Record a receipt of fabric using fabric_code + color_code."""
    result = repo.create_movement_by_codes(
        fabric_code=movement.fabric_code,
        color_code=movement.color_code,
        movement_type="RECEIPT",
        qty=movement.qty,
        uom=movement.uom,
        roll_count=movement.roll_count,
        document_id=movement.document_id,
        reason=movement.reason
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Variant '{movement.color_code}' not found for fabric '{movement.fabric_code}'"
        )
    return result


@router.post("/issue", response_model=MovementResponse, status_code=201)
def issue(movement: MovementCreate):
    """Record an issue/consumption of fabric using fabric_code + color_code."""
    # For ISSUE, negate the quantity to reduce stock
    result = repo.create_movement_by_codes(
        fabric_code=movement.fabric_code,
        color_code=movement.color_code,
        movement_type="ISSUE",
        qty=-abs(movement.qty),  # Always negative for issues
        uom=movement.uom,
        roll_count=-abs(movement.roll_count) if movement.roll_count is not None else None,
        document_id=movement.document_id,
        reason=movement.reason
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Variant '{movement.color_code}' not found for fabric '{movement.fabric_code}'"
        )
    return result


@router.post("/adjust", response_model=MovementResponse, status_code=201)
def adjust(movement: MovementCreate):
    """Record a stock adjustment using fabric_code + color_code."""
    result = repo.create_movement_by_codes(
        fabric_code=movement.fabric_code,
        color_code=movement.color_code,
        movement_type="ADJUST",
        qty=movement.qty,
        uom=movement.uom,
        roll_count=movement.roll_count,
        document_id=movement.document_id,
        reason=movement.reason
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Variant '{movement.color_code}' not found for fabric '{movement.fabric_code}'"
        )
    return result


# ============================================================================
# Batch Routes
# ============================================================================

@router.post("/receive/batch", response_model=MovementBatchResponse)
def receive_batch(batch: MovementBatchRequest):
    """
    Record stock inflow for multiple variants.

    Returns 201 if all succeed, 207 if partial success.
    Max batch size: 50 items.
    """
    # Validate batch size
    if len(batch.items) > 50:
        raise HTTPException(status_code=400, detail="Max batch size is 50 items")

    if len(batch.items) == 0:
        raise HTTPException(status_code=400, detail="At least one item is required")

    # Convert to dicts for repo
    items = [item.model_dump() for item in batch.items]

    # Build reason including customer_name if provided
    reason = batch.reason
    if batch.customer_name:
        reason = f"{batch.customer_name}: {reason}" if reason else batch.customer_name

    processed, failed = repo.create_movements_batch(
        items=items,
        movement_type="RECEIPT",
        document_id=batch.document_id,
        reason=reason
    )

    total_qty = sum(p["qty"] for p in processed)

    response = {
        "processed": processed,
        "failed": failed,
        "summary": {
            "total": len(batch.items),
            "processed": len(processed),
            "failed": len(failed),
            "total_qty": total_qty
        }
    }

    # Return 207 Multi-Status if partial success
    if failed and processed:
        return JSONResponse(status_code=207, content=response)

    # Return 201 if all succeeded
    return JSONResponse(status_code=201, content=response)


@router.post("/issue/batch", response_model=MovementBatchResponse)
def issue_batch(batch: MovementBatchRequest):
    """
    Record stock outflow for multiple variants.

    Returns 201 if all succeed, 207 if partial success.
    Max batch size: 50 items.
    Negative stock is allowed.
    """
    # Validate batch size
    if len(batch.items) > 50:
        raise HTTPException(status_code=400, detail="Max batch size is 50 items")

    if len(batch.items) == 0:
        raise HTTPException(status_code=400, detail="At least one item is required")

    # Convert to dicts for repo with negated quantities (issue reduces stock)
    items = []
    for item in batch.items:
        item_dict = item.model_dump()
        item_dict["qty"] = -abs(item_dict["qty"])  # Always negative for issues
        if item_dict.get("roll_count") is not None:
            item_dict["roll_count"] = -abs(item_dict["roll_count"])
        items.append(item_dict)

    # Build reason including customer_name if provided
    reason = batch.reason
    if batch.customer_name:
        reason = f"{batch.customer_name}: {reason}" if reason else batch.customer_name

    processed, failed = repo.create_movements_batch(
        items=items,
        movement_type="ISSUE",
        document_id=batch.document_id,
        reason=reason
    )

    # Calculate total_qty (use absolute values for summary)
    total_qty = sum(abs(p["qty"]) for p in processed)

    response = {
        "processed": processed,
        "failed": failed,
        "summary": {
            "total": len(batch.items),
            "processed": len(processed),
            "failed": len(failed),
            "total_qty": total_qty
        }
    }

    # Return 207 Multi-Status if partial success
    if failed and processed:
        return JSONResponse(status_code=207, content=response)

    # Return 201 if all succeeded
    return JSONResponse(status_code=201, content=response)
