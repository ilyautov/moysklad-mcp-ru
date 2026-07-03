"""Assemble MoySklad document bodies (Phase 2 write).

Pure functions: given already-resolved meta references and ruble-priced
positions, build the request body. Money stays in RUBLES here; the caller runs
convert_money_to_kopecks on the result before sending. Keeping assembly pure and
money-conversion separate makes both unit-testable without a network or a token.

The order-like documents we cover (purchaseorder, supply, demand, invoiceout,
invoicein, salesreturn, purchasereturn) share the same skeleton:
organization + agent + optional store + positions. doc_type-specific differences
are handled by the caller (which refs are required, the entity path).
"""
from __future__ import annotations

from typing import Any, Optional


def _ref(meta: Optional[dict]) -> Optional[dict]:
    """Wrap a minimal meta into a MoySklad reference {"meta": {...}}."""
    return {"meta": meta} if meta else None


def position(*, assortment_meta: dict, quantity: float = 1, price: float = 0,
             discount: float = 0, vat: Optional[int] = None) -> dict:
    """One document position in RUBLES (price per unit). quantity/discount/vat
    are NOT money: quantity is a count, discount and vat are percentages."""
    pos: dict[str, Any] = {
        "assortment": _ref(assortment_meta),
        "quantity": quantity,
        "price": price,          # rubles here; walker -> kopecks before send
    }
    if discount:
        pos["discount"] = discount
    if vat is not None:
        pos["vat"] = vat
    return pos


def document_body(*, organization_meta: dict, agent_meta: dict,
                  store_meta: Optional[dict] = None,
                  positions: Optional[list] = None,
                  moment: Optional[str] = None, name: Optional[str] = None,
                  description: Optional[str] = None,
                  applicable: bool = False) -> dict:
    """Assemble an order-like document body in RUBLES.

    applicable defaults to False: a freshly created document is a DRAFT, never
    auto-posted. Posting (which moves stock and money) is a separate, explicit,
    destructive-gated step.

    positions: list of dicts already shaped by `position()` (assortment as a
    {"meta": ...} ref, price in rubles).
    """
    body: dict[str, Any] = {
        "organization": _ref(organization_meta),
        "agent": _ref(agent_meta),
        "applicable": bool(applicable),
    }
    if store_meta:
        body["store"] = _ref(store_meta)
    if moment:
        body["moment"] = moment
    if name:
        body["name"] = name
    if description:
        body["description"] = description
    if positions:
        body["positions"] = list(positions)
    return body
