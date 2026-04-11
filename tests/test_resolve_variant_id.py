"""Tests for repo.resolve_variant_id."""
import pytest
from traider import repo


@pytest.fixture
def fabric_with_variants(clean_db):
    """Create one fabric with two variants; attach an alias to one of them."""
    fabric = repo.create_fabric(fabric_code="LYCRA", name="Lycra")
    repo.create_variant_by_fabric_code(
        fabric_code="LYCRA", color_code="910", finish="Standard"
    )
    repo.create_variant_by_fabric_code(
        fabric_code="LYCRA", color_code="920", finish="Standard"
    )
    # Attach alias "1101" to variant 910 directly
    v = repo.get_variant_by_codes("LYCRA", "910")
    repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")
    return fabric


class TestResolveVariantId:
    def test_resolves_primary_color_code(self, fabric_with_variants):
        v = repo.get_variant_by_codes("LYCRA", "910")
        assert repo.resolve_variant_id("LYCRA", "910") == v["id"]

    def test_resolves_alias(self, fabric_with_variants):
        v = repo.get_variant_by_codes("LYCRA", "910")
        assert repo.resolve_variant_id("LYCRA", "1101") == v["id"]

    def test_returns_none_for_unknown_code(self, fabric_with_variants):
        assert repo.resolve_variant_id("LYCRA", "9999") is None

    def test_returns_none_for_unknown_fabric(self, fabric_with_variants):
        assert repo.resolve_variant_id("NOPE", "910") is None

    def test_alias_in_one_fabric_does_not_leak_to_another(self, clean_db):
        repo.create_fabric(fabric_code="LYC", name="Lycra")
        repo.create_fabric(fabric_code="MULL", name="Mull")
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        v = repo.get_variant_by_codes("LYC", "910")
        repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")
        # 1101 is an alias in LYC, not in MULL
        assert repo.resolve_variant_id("LYC", "1101") == v["id"]
        assert repo.resolve_variant_id("MULL", "1101") is None
