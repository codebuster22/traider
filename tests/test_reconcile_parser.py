"""Tests for reconcile.parser — file parsing and normalization."""
from decimal import Decimal
from pathlib import Path
import pytest
from openpyxl import Workbook

from traider.reconcile.parser import parse_reconcile_file

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def build_golden_xlsx():
    """Generate reconcile_golden.xlsx from the .csv on first run."""
    xlsx_path = FIXTURES_DIR / "reconcile_golden.xlsx"
    csv_path = FIXTURES_DIR / "reconcile_golden.csv"
    if xlsx_path.exists():
        return xlsx_path
    wb = Workbook()
    ws = wb.active
    with open(csv_path) as f:
        for line in f:
            ws.append([cell.strip() for cell in line.strip().split(",")])
    wb.save(xlsx_path)
    return xlsx_path


class TestParseReconcileFile:
    def test_parses_csv(self):
        path = FIXTURES_DIR / "reconcile_golden.csv"
        with open(path, "rb") as f:
            rows = parse_reconcile_file(f.read(), "reconcile_golden.csv")
        assert len(rows) == 6
        assert rows[0].fabric_name == "Mull Dobby"
        assert rows[0].colour_no == "910"
        assert rows[0].total_mtr == Decimal("450.5")
        assert rows[0].alias_group == "g1"
        assert rows[0].gsm == 120
        assert rows[0].width == 58

    def test_parses_xlsx(self, build_golden_xlsx):
        path = build_golden_xlsx
        rows = parse_reconcile_file(path.read_bytes(), "reconcile_golden.xlsx")
        assert len(rows) == 6
        assert rows[3].colour_no == "905B"
        assert rows[3].alias_group is None or rows[3].alias_group == ""

    def test_row_numbers_are_1_indexed_and_skip_header(self):
        path = FIXTURES_DIR / "reconcile_golden.csv"
        with open(path, "rb") as f:
            rows = parse_reconcile_file(f.read(), "reconcile_golden.csv")
        # Row 1 is the header; first data row is row 2
        assert rows[0].row_number == 2
        assert rows[-1].row_number == 7

    def test_empty_total_mtr_becomes_none(self):
        csv_bytes = b"FABRIC NAME,FINISH,COLOUR NO.,TOTAL MTR,ALIAS GROUP\nMull,Standard,910,,g1\n"
        rows = parse_reconcile_file(csv_bytes, "empty.csv")
        assert rows[0].total_mtr is None

    def test_invalid_number_raises_value_on_parsed_row(self):
        csv_bytes = b"FABRIC NAME,FINISH,COLOUR NO.,TOTAL MTR,ALIAS GROUP\nMull,Standard,910,abc,g1\n"
        # Parser does not raise — it leaves total_mtr as None and records the raw string
        # so the validator can produce a useful error. See Task F.
        rows = parse_reconcile_file(csv_bytes, "bad.csv")
        assert rows[0].total_mtr is None
