import pytest
from fastapi.testclient import TestClient
from traider.main import app
from traider import repo


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def setup_lycra(clean_db):
    repo.create_fabric(fabric_code="LYC", name="Lycra")
    repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")


class TestLinkRoute:
    def test_add_aliases_to_existing_variant(self, client, setup_lycra):
        r = client.post(
            "/fabrics/LYC/variants/link",
            json={"color_codes": ["910", "1101", "12A"], "confirm": False},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "linked"
        assert body["primary"] == "910"
        assert set(body["aliases_added"]) == {"1101", "12A"}

    def test_404_when_no_variants_resolve(self, client, setup_lycra):
        r = client.post(
            "/fabrics/LYC/variants/link",
            json={"color_codes": ["999", "888"], "confirm": False},
        )
        assert r.status_code == 404

    def test_409_when_merging_with_stock(self, client, clean_db):
        repo.create_fabric(fabric_code="LYC", name="Lycra")
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="920", finish="Standard")
        repo.create_movement_by_codes("LYC", "910", "RECEIPT", 100.0, "m")
        repo.create_movement_by_codes("LYC", "920", "RECEIPT", 50.0, "m")
        r = client.post(
            "/fabrics/LYC/variants/link",
            json={"color_codes": ["910", "920"], "confirm": False},
        )
        assert r.status_code == 409
        body = r.json()
        assert body["status"] == "confirmation_required"
        assert body["plan"]["result_on_hand_m"] == 150.0

    def test_409_followed_by_confirm_commits(self, client, clean_db):
        repo.create_fabric(fabric_code="LYC", name="Lycra")
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="920", finish="Standard")
        repo.create_movement_by_codes("LYC", "910", "RECEIPT", 100.0, "m")
        repo.create_movement_by_codes("LYC", "920", "RECEIPT", 50.0, "m")
        r = client.post(
            "/fabrics/LYC/variants/link",
            json={"color_codes": ["910", "920"], "confirm": True},
        )
        assert r.status_code == 200
        assert r.json()["final_on_hand_m"] == 150.0
