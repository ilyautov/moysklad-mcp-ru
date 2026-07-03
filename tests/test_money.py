"""Kopeck→ruble conversion. No network, no token."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moysklad_mcp.money import (  # noqa: E402
    convert_money, convert_money_to_kopecks, kopecks_to_rubles, rubles_to_kopecks,
)


def test_scalar_kopecks_to_rubles():
    assert kopecks_to_rubles(150000) == 1500.0
    assert kopecks_to_rubles(4650) == 46.5
    assert kopecks_to_rubles(0) == 0.0
    assert kopecks_to_rubles(1) == 0.01


def test_scalar_roundtrip():
    for rub in (0.0, 1.0, 46.5, 1500.0, 99999.99):
        assert kopecks_to_rubles(rubles_to_kopecks(rub)) == rub


def test_scalar_passthrough_non_numbers():
    assert kopecks_to_rubles(None) is None
    assert kopecks_to_rubles("x") == "x"
    assert kopecks_to_rubles(True) is True  # bool is not money


def test_order_sum_converted():
    order = {"name": "00123", "sum": 1250000, "vatSum": 0}
    out = convert_money(order)
    assert out["sum"] == 12500.0
    assert order["sum"] == 1250000  # input not mutated


def test_price_object_converted_only_with_marker():
    row = {
        "name": "Цепь ГРМ",
        "salePrices": [
            {"value": 350000, "currency": {"meta": {}}},
            {"value": 420000, "priceType": {"name": "Розница"}},
        ],
        "buyPrice": {"value": 280000, "currency": {"meta": {}}},
    }
    out = convert_money(row)
    assert out["salePrices"][0]["value"] == 3500.0
    assert out["salePrices"][1]["value"] == 4200.0
    assert out["buyPrice"]["value"] == 2800.0


def test_custom_attribute_value_not_touched():
    # A custom attribute also uses "value" but has no currency/priceType marker.
    row = {"attributes": [{"name": "Артикул поставщика", "value": 406000}]}
    out = convert_money(row)
    assert out["attributes"][0]["value"] == 406000  # left as-is, not /100


def test_metaarray_rows():
    data = {"meta": {"size": 1}, "rows": [{"sum": 500000}]}
    out = convert_money(data)
    assert out["rows"][0]["sum"] == 5000.0
    assert out["meta"]["size"] == 1


# --- write path: rubles -> kopecks (convert_money_to_kopecks) -----------------

def test_position_price_rubles_to_kopecks():
    # The bug this guards: a 100-ruble unit price sent as 100 (= 1 ruble) instead
    # of 10000 kopecks. The position "price" scalar MUST be multiplied by 100.
    pos = {"quantity": 10, "price": 100.0, "discount": 5, "vat": 20}
    out = convert_money_to_kopecks(pos)
    assert out["price"] == 10000          # 100 руб -> 10000 коп
    assert out["quantity"] == 10          # count untouched
    assert out["discount"] == 5           # percent untouched
    assert out["vat"] == 20               # percent untouched


def test_document_sum_rubles_to_kopecks_no_mutation():
    doc = {"name": "ЗП-1", "sum": 1500.0}
    out = convert_money_to_kopecks(doc)
    assert out["sum"] == 150000
    assert doc["sum"] == 1500.0           # input not mutated


def test_price_object_value_to_kopecks_only_with_marker():
    row = {"buyPrice": {"value": 2800.0, "currency": {"meta": {}}}}
    out = convert_money_to_kopecks(row)
    assert out["buyPrice"]["value"] == 280000


def test_custom_attribute_value_not_touched_on_write():
    row = {"attributes": [{"name": "Артикул поставщика", "value": 406}]}
    out = convert_money_to_kopecks(row)
    assert out["attributes"][0]["value"] == 406  # no currency/priceType marker


def test_roundtrip_read_after_write_on_shared_fields():
    # For fields BOTH walkers handle (sum, price-object value), write then read
    # must return the original rubles.
    obj = {"sum": 1234.56, "buyPrice": {"value": 99.99, "priceType": {"name": "x"}}}
    back = convert_money(convert_money_to_kopecks(obj))
    assert back["sum"] == 1234.56
    assert back["buyPrice"]["value"] == 99.99


def test_realistic_purchaseorder_body():
    body = {
        "organization": {"meta": {"type": "organization"}},
        "agent": {"meta": {"type": "counterparty"}},
        "store": {"meta": {"type": "store"}},
        "positions": [
            {"assortment": {"meta": {"type": "product"}}, "quantity": 3, "price": 250.0},
            {"assortment": {"meta": {"type": "product"}}, "quantity": 1, "price": 1000.5},
        ],
    }
    out = convert_money_to_kopecks(body)
    assert out["positions"][0]["price"] == 25000
    assert out["positions"][1]["price"] == 100050
    assert out["positions"][0]["quantity"] == 3   # untouched
    assert out["organization"]["meta"]["type"] == "organization"  # meta untouched
