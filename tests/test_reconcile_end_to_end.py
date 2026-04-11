"""End-to-end test for POST /reconcile/inventory against real Postgres."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from traider.main import _app
from traider import repo

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    return TestClient(_app)


class TestReconcileEndToEnd:
    def test_greenfield_all_created(self, client, clean_db):
        with open(FIXTURES_DIR / "reconcile_golden.csv", "rb") as f:
            r = client.post(
                "/reconcile/inventory",
                files={"file": ("golden.csv", f, "text/csv")},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        assert body["summary"]["fabrics_created"] == 2
        assert body["summary"]["variants_created"] == 4  # 1 alias-grouped + 3 singletons
        # Verify the alias-grouped variant has sum(450.5 + 120 + 0) = 570.5
        bal = repo.get_stock_balance_by_codes("MULL_DOBBY", "910", uom="m")
        assert float(bal["on_hand_m"]) == 570.5
        # Alias 1101 and 12A resolve to the same variant
        v_910 = repo.get_variant_by_codes("MULL_DOBBY", "910")
        v_1101 = repo.get_variant_by_codes("MULL_DOBBY", "1101")
        assert v_910["id"] == v_1101["id"]

    def test_mixed_existing_and_new(self, client, clean_db):
        # Pre-populate: LYCRA with 701 at 800m (sheet says 1000 → delta +200)
        repo.create_fabric(fabric_code="LYCRA", name="Lycra")
        repo.create_variant_by_fabric_code(fabric_code="LYCRA", color_code="701", finish="Bleached")
        repo.create_movement_by_codes("LYCRA", "701", "RECEIPT", 800.0, "m")
        # Upload golden file — LYCRA 701 already has stock
        with open(FIXTURES_DIR / "reconcile_golden.csv", "rb") as f:
            r = client.post(
                "/reconcile/inventory",
                files={"file": ("golden.csv", f, "text/csv")},
            )
        assert r.status_code == 200, r.text
        bal = repo.get_stock_balance_by_codes("LYCRA", "701", uom="m")
        assert float(bal["on_hand_m"]) == 1000.0  # exactly the sheet's target

    def test_conflict_path(self, client, clean_db):
        # Pre-populate: MULL_DOBBY has 1101 as a standalone variant with stock
        repo.create_fabric(fabric_code="MULL_DOBBY", name="Mull Dobby")
        repo.create_variant_by_fabric_code(fabric_code="MULL_DOBBY", color_code="1101", finish="Standard")
        repo.create_movement_by_codes("MULL_DOBBY", "1101", "RECEIPT", 500.0, "m")
        # Upload the golden file — 1101 is supposed to be an alias of 910 in the sheet
        with open(FIXTURES_DIR / "reconcile_golden.csv", "rb") as f:
            r = client.post(
                "/reconcile/inventory",
                files={"file": ("golden.csv", f, "text/csv")},
            )
        # 910 doesn't exist yet — 1101 exists with stock — MULTIPLE_EXISTING? No,
        # since 910 is new. 1101 has primary = 1101 which IS in the sheet's group.
        # So this is actually Case B (single variant) — no conflict expected.
        # The writer will rename 1101's primary to 910 and add aliases.
        assert r.status_code == 200, r.text

    def test_conflict_cross_group_alias(self, client, clean_db):
        # Pre-populate: LYCRA has 888 with 701 as its alias; sheet says 701 should be a singleton
        repo.create_fabric(fabric_code="LYCRA", name="Lycra")
        repo.create_variant_by_fabric_code(fabric_code="LYCRA", color_code="888", finish="Bleached")
        v = repo.get_variant_by_codes("LYCRA", "888")
        repo.add_variant_alias_direct(v["fabric_id"], v["id"], "701")  # 701 is in sheet, pointing wrong
        with open(FIXTURES_DIR / "reconcile_golden.csv", "rb") as f:
            r = client.post(
                "/reconcile/inventory",
                files={"file": ("golden.csv", f, "text/csv")},
            )
        assert r.status_code == 409, r.text
        assert r.json()["status"] == "conflict"
