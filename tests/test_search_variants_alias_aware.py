import pytest
from traider import repo


@pytest.fixture
def fabric_with_aliased_variant(clean_db):
    repo.create_fabric(fabric_code="LYC", name="Lycra")
    repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
    v = repo.get_variant_by_codes("LYC", "910")
    repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")
    return v


class TestSearchVariantsAliasAware:
    def test_free_text_search_matches_by_alias(self, fabric_with_aliased_variant):
        items, total = repo.search_variants(q="1101")
        assert total >= 1
        assert any(i.get("color_code") == "910" for i in items)

    def test_color_code_filter_matches_by_alias(self, fabric_with_aliased_variant):
        items, total = repo.search_variants(color_code="1101")
        assert total >= 1
        assert any(i.get("color_code") == "910" for i in items)

    def test_search_variants_batch_finds_by_alias(self, fabric_with_aliased_variant):
        fabric_id, found, not_found = repo.search_variants_batch(
            fabric_code="LYC", color_codes=["1101"], include_stock=False
        )
        assert not_found == []
        assert len(found) == 1
        assert found[0]["color_code"] == "1101"
        assert found[0]["variant"]["color_code"] == "910"
