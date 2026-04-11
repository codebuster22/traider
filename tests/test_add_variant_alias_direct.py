"""Tests for repo.add_variant_alias_direct cross-table invariants."""
import pytest
from traider import repo
from traider.repo import AliasCollisionError  # will add this exception


@pytest.fixture
def fabric_with_variant(clean_db):
    repo.create_fabric(fabric_code="LYC", name="Lycra")
    repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
    return repo.get_variant_by_codes("LYC", "910")


class TestAddVariantAliasDirect:
    def test_adds_alias_for_valid_new_code(self, fabric_with_variant):
        v = fabric_with_variant
        added = repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")
        assert added is True
        assert repo.resolve_variant_id("LYC", "1101") == v["id"]

    def test_rejects_alias_colliding_with_existing_primary(self, fabric_with_variant):
        v = fabric_with_variant
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="920", finish="Standard")
        with pytest.raises(AliasCollisionError) as exc:
            repo.add_variant_alias_direct(v["fabric_id"], v["id"], "920")
        assert "920" in str(exc.value)

    def test_rejects_alias_colliding_with_existing_alias(self, fabric_with_variant):
        v = fabric_with_variant
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="920", finish="Standard")
        v2 = repo.get_variant_by_codes("LYC", "920")
        repo.add_variant_alias_direct(v2["fabric_id"], v2["id"], "1101")
        with pytest.raises(AliasCollisionError):
            repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")

    def test_idempotent_when_alias_already_on_same_variant(self, fabric_with_variant):
        v = fabric_with_variant
        repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")
        # Second call on same (variant, alias) returns False but doesn't raise
        added = repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")
        assert added is False
