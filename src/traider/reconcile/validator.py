"""Reconcile validator — stage 6 of the pipeline (see spec §6.4.1)."""
from decimal import Decimal
from typing import Optional

from traider.db import sanitize_fabric_code, sanitize_color_code
from traider.reconcile.models import ParsedRow, ValidationError


def validate_rows(rows: list[ParsedRow]) -> tuple[list[ValidationError], list[ParsedRow]]:
    """Run all structural validations on parsed rows.

    Returns (errors, normalized_rows). If errors is non-empty, the file is
    rejected; normalized_rows is still returned for debug but callers must
    NOT write anything on validation failure.

    Normalizes by:
      - Computing sanitized fabric_code from fabric_name
      - Computing sanitized colour_no
      - Assigning synthetic_group_id to rows with blank alias_group
    """
    errors: list[ValidationError] = []

    # Pass 1: per-row required-field and number validation + sanitization
    for row in rows:
        if row.fabric_name is None:
            errors.append(ValidationError(
                row=row.row_number, column="FABRIC NAME",
                code="EMPTY_REQUIRED_CELL", message="FABRIC NAME is required",
            ))
        else:
            row.fabric_code = sanitize_fabric_code(row.fabric_name)

        if row.finish is None:
            errors.append(ValidationError(
                row=row.row_number, column="FINISH",
                code="EMPTY_REQUIRED_CELL", message="FINISH is required",
            ))

        if row.colour_no is None:
            errors.append(ValidationError(
                row=row.row_number, column="COLOUR NO.",
                code="EMPTY_REQUIRED_CELL", message="COLOUR NO. is required",
            ))
        else:
            row.sanitized_colour_no = sanitize_color_code(row.colour_no)

        if row.total_mtr is None:
            errors.append(ValidationError(
                row=row.row_number, column="TOTAL MTR",
                code="INVALID_NUMBER",
                message="TOTAL MTR must be a non-negative number",
            ))
        elif row.total_mtr < 0:
            errors.append(ValidationError(
                row=row.row_number, column="TOTAL MTR",
                code="NEGATIVE_STOCK",
                message=f"TOTAL MTR: negative values not allowed (got {row.total_mtr})",
                value=str(row.total_mtr),
            ))

    # Pass 2: assign synthetic group ids for blank alias_group rows
    for row in rows:
        if row.alias_group is None or row.alias_group == "":
            row.synthetic_group_id = f"__singleton_{row.row_number}"
        else:
            row.synthetic_group_id = row.alias_group

    # Pass 3: DUPLICATE_FABRIC_AFTER_SANITIZE — two different fabric_names → same code
    fabric_code_to_names: dict[str, list[tuple[int, str]]] = {}
    for row in rows:
        if row.fabric_code and row.fabric_name:
            fabric_code_to_names.setdefault(row.fabric_code, []).append((row.row_number, row.fabric_name))
    for fcode, entries in fabric_code_to_names.items():
        distinct_names = {name for _, name in entries}
        if len(distinct_names) > 1:
            rows_listed = ", ".join(str(r) for r, _ in entries[:4])
            errors.append(ValidationError(
                row=entries[0][0], column="FABRIC NAME",
                code="DUPLICATE_FABRIC_AFTER_SANITIZE",
                message=(
                    f"Rows {rows_listed}: FABRIC NAME values {sorted(distinct_names)} "
                    f"all resolve to fabric code '{fcode}'. Use one spelling consistently."
                ),
            ))

    # Pass 4: DUPLICATE_COLOR_IN_FABRIC across groups within one fabric
    color_index: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for row in rows:
        if row.fabric_code and row.sanitized_colour_no:
            key = (row.fabric_code, row.sanitized_colour_no)
            color_index.setdefault(key, []).append((row.row_number, row.synthetic_group_id or ""))
    for (fcode, color), entries in color_index.items():
        groups = {g for _, g in entries}
        if len(groups) > 1:
            errors.append(ValidationError(
                row=entries[0][0], column="COLOUR NO.",
                code="DUPLICATE_COLOR_IN_FABRIC",
                message=(
                    f"COLOUR NO. '{color}' appears in fabric '{fcode}' under multiple alias groups "
                    f"{sorted(groups)}. Every color must belong to exactly one group."
                ),
            ))

    # Pass 5: FABRIC_NAME_DIFFERS_WITHIN_GROUP — rows in same alias_group have different fabric
    group_to_fabrics: dict[str, set[str]] = {}
    group_first_row: dict[str, int] = {}
    for row in rows:
        if row.alias_group and row.fabric_code:
            group_to_fabrics.setdefault(row.alias_group, set()).add(row.fabric_code)
            group_first_row.setdefault(row.alias_group, row.row_number)
    for group, fabrics in group_to_fabrics.items():
        if len(fabrics) > 1:
            errors.append(ValidationError(
                row=group_first_row[group], column="ALIAS GROUP",
                code="FABRIC_NAME_DIFFERS_WITHIN_GROUP",
                message=(
                    f"Alias group '{group}' spans multiple fabrics {sorted(fabrics)}. "
                    f"Alias groups must be within one fabric."
                ),
            ))

    # Pass 6: PRIMARY_COLOR_BLANK — first row by file order in a group has blank colour_no
    first_by_group: dict[str, ParsedRow] = {}
    for row in rows:
        gid = row.synthetic_group_id
        if gid and gid not in first_by_group:
            first_by_group[gid] = row
    for gid, first_row in first_by_group.items():
        if first_row.sanitized_colour_no is None and first_row.colour_no is None:
            # Only emit if we didn't already emit EMPTY_REQUIRED_CELL for this cell
            # (we did, but the PRIMARY_COLOR_BLANK message is clearer for group context)
            if not first_row.alias_group:
                continue  # singleton — already covered by EMPTY_REQUIRED_CELL
            errors.append(ValidationError(
                row=first_row.row_number, column="COLOUR NO.",
                code="PRIMARY_COLOR_BLANK",
                message=(
                    f"ALIAS GROUP '{first_row.alias_group}', fabric '{first_row.fabric_name}': "
                    f"the first row's COLOUR NO. cannot be blank (it becomes the primary)."
                ),
            ))

    return errors, rows
