"""Group normalized ParsedRows into TargetGroups. See spec §6.4.3 stage 7."""
from decimal import Decimal

from traider.reconcile.models import ParsedRow, TargetGroup


def group_rows(rows: list[ParsedRow]) -> list[TargetGroup]:
    """Group rows by (fabric_code, synthetic_group_id), preserving file order.

    Primary color = first row in the group by file order (spec §6.4.3).
    Balance = sum of TOTAL MTR across all rows in the group.
    """
    groups: dict[tuple[str, str], TargetGroup] = {}
    for row in rows:
        key = (row.fabric_code or "", row.synthetic_group_id or f"__row_{row.row_number}")
        if key not in groups:
            groups[key] = TargetGroup(
                fabric_code=row.fabric_code or "",
                fabric_name=row.fabric_name or "",
                finish=row.finish or "Standard",
                gsm=row.gsm,
                width=row.width,
                primary_color_code=row.sanitized_colour_no or "",
                alias_codes=[],
                total_mtr=Decimal(0),
                source_rows=[],
            )
        else:
            # This row is an alias of the primary (first row)
            if row.sanitized_colour_no:
                groups[key].alias_codes.append(row.sanitized_colour_no)

        if row.total_mtr is not None:
            groups[key].total_mtr += row.total_mtr
        groups[key].source_rows.append(row.row_number)

    return list(groups.values())
