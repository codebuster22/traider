"""Reconcile file parser — xlsx and csv → list of ParsedRow."""
import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Optional

from openpyxl import load_workbook

from traider.reconcile.models import ParsedRow

# Column name → ParsedRow field name. Matched case-insensitively after normalization.
COLUMN_MAP = {
    "fabric name": "fabric_name",
    "finish": "finish",
    "colour no.": "colour_no",
    "colour no": "colour_no",  # tolerate missing period
    "color no.": "colour_no",  # tolerate US spelling
    "color no": "colour_no",
    "total mtr": "total_mtr",
    "alias group": "alias_group",
    "gsm": "gsm",
    "width": "width",
    # Ignored columns — parser silently drops these
    "stock": None,
    "in": None,
    "out": None,
}


def _normalize_header(raw: str) -> str:
    return (raw or "").strip().lower()


def _coerce_decimal(value) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _coerce_int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def _coerce_str(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _parse_rows(raw_rows: list[list]) -> list[ParsedRow]:
    """Shared logic for xlsx and csv. raw_rows[0] is the header."""
    if not raw_rows:
        return []
    header = [_normalize_header(c) for c in raw_rows[0]]
    # Build column index → field name, skipping unknown columns
    col_to_field: dict[int, Optional[str]] = {}
    for idx, col in enumerate(header):
        field = COLUMN_MAP.get(col)
        col_to_field[idx] = field  # may be None (unknown or ignored)

    parsed: list[ParsedRow] = []
    for row_idx, raw_row in enumerate(raw_rows[1:], start=2):  # row 2 is first data row
        if not any(str(c).strip() if c is not None else "" for c in raw_row):
            continue  # skip fully-blank rows
        values: dict[str, object] = {}
        for col_idx, value in enumerate(raw_row):
            field = col_to_field.get(col_idx)
            if field is None:
                continue
            values[field] = value
        parsed.append(ParsedRow(
            row_number=row_idx,
            fabric_name=_coerce_str(values.get("fabric_name")),
            finish=_coerce_str(values.get("finish")),
            colour_no=_coerce_str(values.get("colour_no")),
            total_mtr=_coerce_decimal(values.get("total_mtr")),
            alias_group=_coerce_str(values.get("alias_group")),
            gsm=_coerce_int(values.get("gsm")),
            width=_coerce_int(values.get("width")),
        ))
    return parsed


def parse_csv(file_bytes: bytes) -> list[ParsedRow]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    raw_rows = list(reader)
    return _parse_rows(raw_rows)


def parse_xlsx(file_bytes: bytes) -> list[ParsedRow]:
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    ws = wb.active
    raw_rows = [list(row) for row in ws.iter_rows(values_only=True)]
    return _parse_rows(raw_rows)


def parse_reconcile_file(file_bytes: bytes, filename: str) -> list[ParsedRow]:
    """Dispatch to csv or xlsx parser based on filename extension."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        return parse_csv(file_bytes)
    if lower.endswith((".xlsx", ".xls")):
        return parse_xlsx(file_bytes)
    raise ValueError(f"Unsupported file extension for '{filename}'. Supported: .csv, .xlsx, .xls")
