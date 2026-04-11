"""Internal dataclasses for the reconcile pipeline."""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class ParsedRow:
    """One row after parsing + normalization. Columns renamed to snake_case."""
    row_number: int  # 1-indexed, matches spreadsheet row for error messages
    fabric_name: Optional[str]
    finish: Optional[str]
    colour_no: Optional[str]
    total_mtr: Optional[Decimal]
    alias_group: Optional[str]  # None means "singleton"; parser assigns synthetic id
    gsm: Optional[int]
    width: Optional[int]
    # Normalized derivatives (filled by validator)
    fabric_code: Optional[str] = None  # sanitize_fabric_code(fabric_name)
    sanitized_colour_no: Optional[str] = None  # sanitize_color_code(colour_no)
    synthetic_group_id: Optional[str] = None  # set for blank alias_group rows


@dataclass
class ValidationError:
    row: int  # 0 for file-level errors
    column: Optional[str]
    code: str
    message: str
    value: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"row": self.row, "column": self.column, "code": self.code, "message": self.message}
        if self.value is not None:
            d["value"] = self.value
        return d


@dataclass
class TargetGroup:
    """One logical variant after grouping by (fabric_code, alias_group_id).

    The first row in file order is the primary. Aliases = remaining rows.
    """
    fabric_code: str
    fabric_name: str  # display name from first row
    finish: str  # from first row
    gsm: Optional[int]
    width: Optional[int]
    primary_color_code: str  # sanitized
    alias_codes: list[str] = field(default_factory=list)  # sanitized
    total_mtr: Decimal = Decimal(0)  # sum across all rows in the group
    source_rows: list[int] = field(default_factory=list)  # row numbers for error tracing


@dataclass
class ReconcileConflict:
    code: str  # CROSS_GROUP_ALIAS_CONFLICT | MULTIPLE_EXISTING_VARIANTS_NEED_MERGE
    row: int
    fabric_code: str
    color_code: str
    existing_variant_primary: Optional[str]
    remediation: str
    message: str

    def to_dict(self) -> dict:
        return {
            "code": self.code, "row": self.row,
            "fabric_code": self.fabric_code, "color_code": self.color_code,
            "existing_variant_primary": self.existing_variant_primary,
            "remediation": self.remediation, "message": self.message,
        }


@dataclass
class ReconcileAction:
    """One entry in the response `actions` list."""
    type: str  # fabric_created | variant_created | variant_adjusted | variant_already_balanced
    fabric_code: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"type": self.type, "fabric_code": self.fabric_code, **self.payload}


@dataclass
class ReconcileSummary:
    fabrics_created: int = 0
    fabrics_touched: int = 0
    variants_created: int = 0
    variants_adjusted: int = 0
    variants_already_balanced: int = 0
    aliases_created: int = 0
    movements_posted: int = 0
    total_delta_m: Decimal = Decimal(0)

    def to_dict(self) -> dict:
        return {
            "fabrics_created": self.fabrics_created,
            "fabrics_touched": self.fabrics_touched,
            "variants_created": self.variants_created,
            "variants_adjusted": self.variants_adjusted,
            "variants_already_balanced": self.variants_already_balanced,
            "aliases_created": self.aliases_created,
            "movements_posted": self.movements_posted,
            "total_delta_m": float(self.total_delta_m),
        }
