"""POST /reconcile/inventory — multipart upload endpoint. See spec §6.4."""
import secrets
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors

from traider.reconcile.conflict_detector import detect_conflicts
from traider.reconcile.grouping import group_rows
from traider.reconcile.parser import parse_reconcile_file
from traider.reconcile.validator import validate_rows
from traider.reconcile.writer import execute_reconcile

router = APIRouter(prefix="/reconcile", tags=["reconcile"])

MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def _generate_batch_id() -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"reconcile_{ts}_{secrets.token_hex(2)}"


@router.post("/inventory")
async def reconcile_inventory(
    file: UploadFile = File(...),
    reason: str = Form(default="FY 2026-27 opening balance reconciliation"),
    batch_id: str | None = Form(default=None),
):
    """Ingest a reconciliation file. See spec §6.4."""
    batch_id = batch_id or _generate_batch_id()

    # Stage 1: size check
    raw = await file.read()
    if len(raw) > MAX_FILE_BYTES:
        return JSONResponse(
            status_code=413,
            content={"status": "file_too_large", "max_mb": 15},
        )

    # Stage 2: extension check
    filename = file.filename or ""
    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        return JSONResponse(
            status_code=400,
            content={
                "status": "validation_failed",
                "errors": [{
                    "row": 0, "column": None,
                    "code": "UNSUPPORTED_FILE_EXTENSION",
                    "message": f"File '{filename}': extension not supported. Use .xlsx, .xls, or .csv.",
                }],
            },
        )

    # Stages 3-5: parse + normalize
    try:
        rows = parse_reconcile_file(raw, filename)
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={
                "status": "validation_failed",
                "errors": [{"row": 0, "column": None, "code": "PARSE_ERROR", "message": str(e)}],
            },
        )

    # Stage 6: structural validation
    errors, normalized = validate_rows(rows)
    if errors:
        return JSONResponse(
            status_code=400,
            content={
                "status": "validation_failed",
                "errors": [e.to_dict() for e in errors],
            },
        )

    # Stage 7: grouping
    groups = group_rows(normalized)

    # Stages 8-9 + 10: conflict detection and write, inside one SERIALIZABLE txn
    try:
        conflicts = detect_conflicts(groups)
        if conflicts:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "conflict",
                    "conflicts": [c.to_dict() for c in conflicts],
                },
            )
        summary, actions = execute_reconcile(groups, batch_id, reason=reason)
    except pg_errors.SerializationFailure:
        return JSONResponse(
            status_code=503,
            content={
                "status": "retry",
                "message": "Concurrent update, please retry.",
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "batch_id": batch_id,
            "summary": summary.to_dict(),
            "actions": [a.to_dict() for a in actions],
        },
    )
