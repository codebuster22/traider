import pytest
from fastapi.testclient import TestClient
from traider.main import app
from traider import repo


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def variant_with_alias(clean_db):
    repo.create_fabric(fabric_code="LYC", name="Lycra")
    repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
    v = repo.get_variant_by_codes("LYC", "910")
    repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")
    return v


class TestAliasCRUDRoutes:
    def test_get_aliases_by_primary(self, client, variant_with_alias):
        r = client.get("/fabrics/LYC/variants/910/aliases")
        assert r.status_code == 200
        assert r.json() == ["1101"]

    def test_get_aliases_by_alias_resolves_same_variant(self, client, variant_with_alias):
        r = client.get("/fabrics/LYC/variants/1101/aliases")
        assert r.status_code == 200
        assert r.json() == ["1101"]

    def test_get_aliases_404_when_variant_missing(self, client, clean_db):
        repo.create_fabric(fabric_code="LYC", name="Lycra")
        r = client.get("/fabrics/LYC/variants/999/aliases")
        assert r.status_code == 404

    def test_delete_alias(self, client, variant_with_alias):
        r = client.delete("/fabrics/LYC/variants/910/aliases/1101")
        assert r.status_code == 200
        r2 = client.get("/fabrics/LYC/variants/910/aliases")
        assert r2.json() == []

    def test_delete_alias_404_when_missing(self, client, variant_with_alias):
        r = client.delete("/fabrics/LYC/variants/910/aliases/NOPE")
        assert r.status_code == 404
