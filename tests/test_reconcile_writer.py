"""Tests for reconcile.writer — the transactional write stage."""
from decimal import Decimal
import pytest

from traider import repo
from traider.reconcile.models import TargetGroup, ReconcileSummary
from traider.reconcile.writer import execute_reconcile


@pytest.fixture
def lycra(clean_db):
    repo.create_fabric(fabric_code="LYC", name="Lycra")


def _group(primary="910", aliases=None, total=100.0, fabric_code="LYC", fabric_name="Lycra"):
    return TargetGroup(
        fabric_code=fabric_code, fabric_name=fabric_name, finish="Standard",
        gsm=None, width=None,
        primary_color_code=primary, alias_codes=aliases or [],
        total_mtr=Decimal(str(total)), source_rows=[2],
    )


class TestReconcileWriter:
    def test_branch_1_new_variant_and_fabric(self, clean_db):
        groups = [_group(primary="910", aliases=["1101"], total=570.5, fabric_name="Mull Dobby")]
        groups[0].fabric_code = "MULL_DOBBY"
        batch_id = "test_batch_1"
        summary, actions = execute_reconcile(groups, batch_id, reason="test")
        assert summary.fabrics_created == 1
        assert summary.variants_created == 1
        assert summary.aliases_created == 1
        balance = repo.get_stock_balance_by_codes("MULL_DOBBY", "910", uom="m")
        assert float(balance["on_hand_m"]) == 570.5

    def test_branch_2_variant_exists_delta_adjust(self, lycra):
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        repo.create_movement_by_codes("LYC", "910", "RECEIPT", 200.0, "m")
        groups = [_group(primary="910", total=675.0)]
        summary, actions = execute_reconcile(groups, "test_batch_2", reason="test")
        assert summary.variants_adjusted == 1
        balance = repo.get_stock_balance_by_codes("LYC", "910", uom="m")
        assert float(balance["on_hand_m"]) == 675.0

    def test_branch_2_no_change_when_already_balanced(self, lycra):
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        repo.create_movement_by_codes("LYC", "910", "RECEIPT", 100.0, "m")
        groups = [_group(primary="910", total=100.0)]
        summary, actions = execute_reconcile(groups, "test_batch_3", reason="test")
        assert summary.variants_already_balanced == 1
        # No new movement should be posted
        assert summary.movements_posted == 0

    def test_branch_3_add_new_alias_and_adjust(self, lycra):
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        repo.create_movement_by_codes("LYC", "910", "RECEIPT", 100.0, "m")
        groups = [_group(primary="910", aliases=["1101"], total=150.0)]
        summary, actions = execute_reconcile(groups, "test_batch_4", reason="test")
        assert summary.variants_adjusted == 1
        assert summary.aliases_created == 1
        assert repo.resolve_variant_id("LYC", "1101") == repo.resolve_variant_id("LYC", "910")
        balance = repo.get_stock_balance_by_codes("LYC", "910", uom="m")
        assert float(balance["on_hand_m"]) == 150.0

    def test_branch_0_silent_merge_no_stock(self, lycra):
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="1101", finish="Standard")
        # neither has stock
        groups = [_group(primary="910", aliases=["1101"], total=200.0)]
        summary, actions = execute_reconcile(groups, "test_batch_5", reason="test")
        # Should silently merge and end with one variant at 200.0
        assert repo.resolve_variant_id("LYC", "1101") == repo.resolve_variant_id("LYC", "910")
        balance = repo.get_stock_balance_by_codes("LYC", "910", uom="m")
        assert float(balance["on_hand_m"]) == 200.0

    def test_all_movements_tagged_with_batch_document_id(self, lycra):
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        groups = [_group(primary="910", total=100.0)]
        summary, actions = execute_reconcile(groups, "batch_xyz", reason="test")
        with repo.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT document_id FROM stock_movements WHERE document_id LIKE 'reconcile:%%'"
                )
                rows = cur.fetchall()
        assert any(r["document_id"] == "reconcile:batch_xyz" for r in rows)
