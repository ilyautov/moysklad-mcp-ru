"""Document body assembly (rubles, pre-money-conversion). No network, no token."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moysklad_mcp.build import document_body, position  # noqa: E402

ORG = {"href": "h/organization/1", "type": "organization", "mediaType": "application/json"}
AGENT = {"href": "h/counterparty/2", "type": "counterparty", "mediaType": "application/json"}
STORE = {"href": "h/store/3", "type": "store", "mediaType": "application/json"}
PROD = {"href": "h/product/4", "type": "product", "mediaType": "application/json"}


def test_body_defaults_to_draft():
    body = document_body(organization_meta=ORG, agent_meta=AGENT)
    assert body["applicable"] is False          # never auto-posted
    assert body["organization"] == {"meta": ORG}
    assert body["agent"] == {"meta": AGENT}
    assert "store" not in body                   # omitted when not given
    assert "positions" not in body


def test_body_with_store_and_fields():
    body = document_body(organization_meta=ORG, agent_meta=AGENT, store_meta=STORE,
                         moment="2026-06-01 10:00:00", name="ЗП-1", description="тест")
    assert body["store"] == {"meta": STORE}
    assert body["moment"] == "2026-06-01 10:00:00"
    assert body["name"] == "ЗП-1"
    assert body["description"] == "тест"


def test_position_shape():
    p = position(assortment_meta=PROD, quantity=5, price=250.0)
    assert p["assortment"] == {"meta": PROD}
    assert p["quantity"] == 5
    assert p["price"] == 250.0          # rubles here; converted later
    assert "discount" not in p          # 0 discount omitted
    assert "vat" not in p               # None vat omitted


def test_position_optional_discount_vat():
    p = position(assortment_meta=PROD, quantity=1, price=10, discount=5, vat=20)
    assert p["discount"] == 5
    assert p["vat"] == 20


def test_body_with_positions():
    poss = [position(assortment_meta=PROD, quantity=2, price=100.0)]
    body = document_body(organization_meta=ORG, agent_meta=AGENT, positions=poss)
    assert body["positions"][0]["assortment"] == {"meta": PROD}
    assert body["positions"][0]["price"] == 100.0
