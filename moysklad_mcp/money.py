"""Money conversion for MoySklad.

Every monetary value in the MoySklad JSON API is an integer number of KOPECKS
(1/100 of a ruble). If the agent reasons over raw values it is off by 100x on
every price and sum. We convert at our boundary: rubles in typed tools, kopecks
only inside raw meta-tools (documented).

Scope (PoC): scalar converters + a precise walker that converts MoySklad money
objects without touching look-alike integers (custom attributes, quantities).
Heuristic, verified against the official doc shapes:
  - a dict with a "sum" int   -> document/position total, kopecks
  - a price object  {"value": <int>, "currency"|"priceType": {...}}  -> kopecks
Custom attributes also use a "value" key but never carry "currency"/"priceType",
so they are left untouched. Full generic coverage is a Phase 2 task.
"""
from __future__ import annotations

from typing import Any

# Unambiguous top-level money keys whose scalar value is always kopecks.
SUM_KEYS = frozenset({
    "sum", "payedSum", "shippedSum", "invoicedSum", "reservedSum",
})

# A nested money object is recognised by a "value" alongside one of these.
_PRICE_MARKERS = ("currency", "priceType")


def kopecks_to_rubles(kopecks: Any) -> Any:
    """Integer kopecks -> float rubles (2 decimals). Passes through None/non-numbers."""
    if isinstance(kopecks, bool) or not isinstance(kopecks, (int, float)):
        return kopecks
    return round(kopecks / 100.0, 2)


def rubles_to_kopecks(rubles: Any) -> Any:
    """Float rubles -> integer kopecks. Passes through None/non-numbers."""
    if isinstance(rubles, bool) or not isinstance(rubles, (int, float)):
        return rubles
    return int(round(rubles * 100))


def _is_price_object(d: dict) -> bool:
    return "value" in d and any(m in d for m in _PRICE_MARKERS)


def convert_money(obj: Any) -> Any:
    """Return a deep copy of obj with MoySklad money values turned into rubles.

    Only touches:
      - scalar values under a key in SUM_KEYS,
      - the "value" of a recognised price object (has currency/priceType).
    Everything else is left exactly as-is. Non-destructive: input is not mutated.
    """
    if isinstance(obj, list):
        return [convert_money(x) for x in obj]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        price_object = _is_price_object(obj)
        for k, v in obj.items():
            if k in SUM_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = kopecks_to_rubles(v)
            elif k == "value" and price_object and isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = kopecks_to_rubles(v)
            else:
                out[k] = convert_money(v)
        return out
    return obj


# Scalar money keys that appear in WRITE payloads (request bodies we send).
# Superset of the read SUM_KEYS plus "price": a document position carries a
# scalar "price" in kopecks (the read layer leaves it raw, the write layer MUST
# convert it, or every order is created at 1/100 of the intended unit price).
# All keys here are unambiguously money. NOT included on purpose: "quantity"
# (count), "discount"/"vat" (percentages), "reserve"/"inTransit" (counts).
WRITE_MONEY_KEYS = SUM_KEYS | frozenset({"price"})


def convert_money_to_kopecks(obj: Any) -> Any:
    """Return a deep copy of obj with ruble money turned into integer kopecks.

    Inverse of convert_money, used on the WRITE boundary: typed tools accept
    rubles from the user, this turns the assembled body into the kopecks the
    API expects. Touches only:
      - scalar values under a key in WRITE_MONEY_KEYS (incl. position "price"),
      - the "value" of a recognised price object (has currency/priceType).
    Everything else (quantities, percentages, custom attribute "value" with no
    currency/priceType marker) is left exactly as-is. Input is not mutated.
    """
    if isinstance(obj, list):
        return [convert_money_to_kopecks(x) for x in obj]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        price_object = _is_price_object(obj)
        for k, v in obj.items():
            if k in WRITE_MONEY_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = rubles_to_kopecks(v)
            elif k == "value" and price_object and isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = rubles_to_kopecks(v)
            else:
                out[k] = convert_money_to_kopecks(v)
        return out
    return obj
