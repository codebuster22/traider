"""Proves that all point-lookup *_by_codes functions route through resolve_variant_id."""
import pytest
from traider import repo


@pytest.fixture
def lycra_910_with_alias_1101(clean_db):
    repo.create_fabric(fabric_code="LYC", name="Lycra")
    repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
    v = repo.get_variant_by_codes("LYC", "910")
    repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")
    repo.create_movement_by_codes(
        fabric_code="LYC", color_code="910",
        movement_type="RECEIPT", qty=100.0, uom="m",
    )
    return v


class TestAliasAwareLookups:
    def test_get_variant_by_codes_via_alias(self, lycra_910_with_alias_1101):
        v_primary = repo.get_variant_by_codes("LYC", "910")
        v_alias = repo.get_variant_by_codes("LYC", "1101")
        assert v_alias is not None
        assert v_primary["id"] == v_alias["id"]

    def test_get_stock_balance_by_codes_via_alias(self, lycra_910_with_alias_1101):
        balance = repo.get_stock_balance_by_codes("LYC", "1101", uom="m")
        assert balance is not None
        assert float(balance["on_hand_m"]) == 100.0

    def test_create_movement_by_codes_via_alias(self, lycra_910_with_alias_1101):
        # qty is negative for ISSUE (repo layer does not negate; route layer handles sign)
        result = repo.create_movement_by_codes(
            fabric_code="LYC", color_code="1101",
            movement_type="ISSUE", qty=-20.0, uom="m",
        )
        assert result is not None
        balance = repo.get_stock_balance_by_codes("LYC", "910", uom="m")
        assert float(balance["on_hand_m"]) == 80.0

    def test_update_variant_by_codes_via_alias(self, lycra_910_with_alias_1101):
        result = repo.update_variant_by_codes(
            fabric_code="LYC", color_code="1101", finish="Bleached"
        )
        assert result is not None
        v = repo.get_variant_by_codes("LYC", "910")
        assert v["finish"] == "Bleached"

    def test_delete_variant_by_codes_via_alias(self, clean_db):
        repo.create_fabric(fabric_code="DEL", name="Deletable")
        repo.create_variant_by_fabric_code(fabric_code="DEL", color_code="A", finish="Standard")
        v = repo.get_variant_by_codes("DEL", "A")
        repo.add_variant_alias_direct(v["fabric_id"], v["id"], "B")
        deleted = repo.delete_variant_by_codes("DEL", "B")
        assert deleted is True
        assert repo.get_variant_by_codes("DEL", "A") is None

    def test_create_movements_batch_via_alias(self, lycra_910_with_alias_1101):
        """create_movements_batch() has its own per-item variant lookup — must also be alias-aware."""
        items = [{"fabric_code": "LYC", "color_code": "1101", "qty": 10.0, "uom": "m"}]
        processed, failed = repo.create_movements_batch(items, movement_type="RECEIPT")
        assert failed == []
        assert len(processed) == 1
        # 1101 resolves to 910's variant; balance = 100 initial + 10 batch = 110
        balance = repo.get_stock_balance_by_codes("LYC", "910", uom="m")
        assert float(balance["on_hand_m"]) == 110.0
