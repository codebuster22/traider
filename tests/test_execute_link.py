"""Tests for repo._execute_link — the shared helper behind link_variants and reconcile."""
import pytest
from traider import repo
from traider.repo import AliasCollisionError


@pytest.fixture
def lycra(clean_db):
    repo.create_fabric(fabric_code="LYC", name="Lycra")


def _make_variant(fabric_code, color_code, with_stock=0.0):
    repo.create_variant_by_fabric_code(
        fabric_code=fabric_code, color_code=color_code, finish="Standard"
    )
    if with_stock > 0:
        repo.create_movement_by_codes(
            fabric_code=fabric_code, color_code=color_code,
            movement_type="RECEIPT", qty=with_stock, uom="m",
        )
    return repo.get_variant_by_codes(fabric_code, color_code)


class TestExecuteLink:
    def test_case_a_no_variants_resolve(self, lycra):
        result = repo._execute_link("LYC", ["910", "1101"], confirm=False)
        assert result["result"] == "not_found"

    def test_case_b_single_variant_add_aliases(self, lycra):
        _make_variant("LYC", "910")
        result = repo._execute_link("LYC", ["910", "1101", "12A"], confirm=False)
        assert result["result"] == "linked"
        assert result["primary"] == "910"
        assert set(result["aliases_added"]) == {"1101", "12A"}
        assert repo.resolve_variant_id("LYC", "1101") == repo.resolve_variant_id("LYC", "910")

    def test_case_c_all_codes_already_on_same_variant(self, lycra):
        _make_variant("LYC", "910")
        repo._execute_link("LYC", ["910", "1101"], confirm=False)
        result = repo._execute_link("LYC", ["910", "1101"], confirm=False)
        assert result["result"] == "already_linked"
        assert result["primary"] == "910"

    def test_case_d_multiple_variants_no_stock_silent_merge(self, lycra):
        _make_variant("LYC", "910", with_stock=0)
        _make_variant("LYC", "920", with_stock=0)
        result = repo._execute_link("LYC", ["910", "920"], confirm=False)
        assert result["result"] == "linked"
        assert result["primary"] == "910"
        assert "920" in result["merged_from"]
        assert repo.resolve_variant_id("LYC", "910") == repo.resolve_variant_id("LYC", "920")

    def test_case_e_multiple_variants_with_stock_requires_confirm(self, lycra):
        _make_variant("LYC", "910", with_stock=100.0)
        _make_variant("LYC", "920", with_stock=50.0)
        result = repo._execute_link("LYC", ["910", "920"], confirm=False)
        assert result["result"] == "confirmation_required"
        assert result["plan"]["primary"] == "910"
        assert result["plan"]["result_on_hand_m"] == 150.0

    def test_case_e_with_confirm_executes_merge(self, lycra):
        _make_variant("LYC", "910", with_stock=100.0)
        _make_variant("LYC", "920", with_stock=50.0)
        result = repo._execute_link("LYC", ["910", "920"], confirm=True)
        assert result["result"] == "linked"
        assert result["final_on_hand_m"] == 150.0
        balance = repo.get_stock_balance_by_codes("LYC", "910", uom="m")
        assert float(balance["on_hand_m"]) == 150.0

    def test_promote_alias_to_primary(self, lycra):
        v = _make_variant("LYC", "910")
        repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")
        result = repo._execute_link("LYC", ["1101", "910"], confirm=False)
        assert result["result"] == "linked"
        assert result["primary"] == "1101"
        v_after = repo.get_variant_by_codes("LYC", "1101")
        assert v_after["color_code"] == "1101"
        assert "910" in repo.list_variant_aliases(v_after["id"])

    def test_rename_on_missing_primary(self, lycra):
        _make_variant("LYC", "101")
        result = repo._execute_link("LYC", ["106", "101"], confirm=False)
        assert result["result"] == "linked"
        assert result["primary"] == "106"
        v = repo.get_variant_by_codes("LYC", "106")
        assert v["color_code"] == "106"
        assert "101" in repo.list_variant_aliases(v["id"])
