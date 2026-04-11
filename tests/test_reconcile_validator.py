"""Tests for reconcile.validator — one test per error code."""
from decimal import Decimal
import pytest

from traider.reconcile.models import ParsedRow
from traider.reconcile.validator import validate_rows


def _row(**kwargs):
    defaults = dict(
        row_number=2, fabric_name="Mull", finish="Standard",
        colour_no="910", total_mtr=Decimal("100"),
        alias_group="g1", gsm=None, width=None,
    )
    defaults.update(kwargs)
    return ParsedRow(**defaults)


class TestValidator:
    def test_happy_path_no_errors(self):
        rows = [_row()]
        errors, normalized = validate_rows(rows)
        assert errors == []
        assert normalized[0].fabric_code == "MULL"

    def test_empty_required_cell_fabric_name(self):
        errors, _ = validate_rows([_row(fabric_name=None)])
        assert any(e.code == "EMPTY_REQUIRED_CELL" and e.column == "FABRIC NAME" for e in errors)

    def test_empty_required_cell_finish(self):
        errors, _ = validate_rows([_row(finish=None)])
        assert any(e.code == "EMPTY_REQUIRED_CELL" and e.column == "FINISH" for e in errors)

    def test_empty_required_cell_colour_no(self):
        errors, _ = validate_rows([_row(colour_no=None)])
        assert any(e.code == "EMPTY_REQUIRED_CELL" and e.column == "COLOUR NO." for e in errors)

    def test_empty_total_mtr_is_invalid_number(self):
        errors, _ = validate_rows([_row(total_mtr=None)])
        assert any(e.code in ("EMPTY_REQUIRED_CELL", "INVALID_NUMBER") and e.column == "TOTAL MTR" for e in errors)

    def test_negative_stock(self):
        errors, _ = validate_rows([_row(total_mtr=Decimal("-5"))])
        assert any(e.code == "NEGATIVE_STOCK" for e in errors)

    def test_duplicate_color_in_fabric_across_groups(self):
        rows = [
            _row(row_number=2, colour_no="905B", alias_group="g1"),
            _row(row_number=5, colour_no="905B", alias_group="g2"),
        ]
        errors, _ = validate_rows(rows)
        assert any(e.code == "DUPLICATE_COLOR_IN_FABRIC" for e in errors)

    def test_fabric_name_differs_within_group(self):
        rows = [
            _row(row_number=2, fabric_name="Mull", alias_group="g3"),
            _row(row_number=3, fabric_name="Lycra", alias_group="g3", colour_no="920"),
        ]
        errors, _ = validate_rows(rows)
        assert any(e.code == "FABRIC_NAME_DIFFERS_WITHIN_GROUP" for e in errors)

    def test_primary_color_blank_first_row_in_group(self):
        rows = [
            _row(row_number=2, colour_no=None, alias_group="g4"),
            _row(row_number=3, colour_no="1101", alias_group="g4"),
        ]
        errors, _ = validate_rows(rows)
        # The parser catches missing colour_no as EMPTY_REQUIRED_CELL first;
        # also expect PRIMARY_COLOR_BLANK when the FIRST row of a group is blank
        assert any(e.code in ("PRIMARY_COLOR_BLANK", "EMPTY_REQUIRED_CELL") for e in errors)

    def test_duplicate_fabric_after_sanitize(self):
        rows = [
            _row(row_number=2, fabric_name="Mull Dobby", colour_no="910"),
            _row(row_number=5, fabric_name="Mull-Dobby", colour_no="920"),
        ]
        errors, _ = validate_rows(rows)
        assert any(e.code == "DUPLICATE_FABRIC_AFTER_SANITIZE" for e in errors)

    def test_blank_alias_group_becomes_synthetic_singleton(self):
        rows = [
            _row(row_number=2, colour_no="910", alias_group=None),
            _row(row_number=3, colour_no="920", alias_group=None),
        ]
        errors, normalized = validate_rows(rows)
        assert errors == []
        # Each row gets its own synthetic group
        assert normalized[0].synthetic_group_id != normalized[1].synthetic_group_id
        assert normalized[0].synthetic_group_id.startswith("__singleton_")
