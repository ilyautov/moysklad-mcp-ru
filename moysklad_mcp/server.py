#!/usr/bin/env python3
"""moysklad_mcp — MCP server for the MoySklad JSON API 1.2.

Exposes MoySklad through the schema-driven meta-tools from `core`
(ms_search_methods / ms_describe_method / ms_call_method / ms_call_raw /
ms_fetch_all / ms_check_auth + cabinet tools) plus a few typed convenience
tools for the everyday manager questions (stock, products, orders).

PoC thin slice: read-only curated core (4 endpoints), Bearer-token auth,
kopecks→rubles in the typed tools. Heavy-report async, the X-Lognex-Retry-After
patch and a proactive throttle are deferred until after the live-cabinet go.

Auth: MoySklad access token (Settings → Users → Access tokens) sent as
    Authorization: Bearer <token>
MoySklad requires gzip — we always send Accept-Encoding: gzip (a request without
it is rejected with HTTP 415).

Run:
    MOYSKLAD_TOKEN=... python -m moysklad_mcp.server
    # or via the launcher:  python serve.py ms  [--selfcheck]
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from core.client import MarketplaceClient, ServiceConfig
from core.credentials import CredentialStore
from core.entities import EntityIndex
from core.errors import make_error
from core.registry import Catalog
from core.safety import check_gate
from core.tools import register_cabinet_tools, register_generic_tools
from core.workflows import Workflows, register_workflow_tools

from .build import document_body, position
from .money import convert_money, convert_money_to_kopecks
from .refs import resolve_ref
from .write_guard import GuardedClient, check_write_guard

CATALOG_PATH = Path(__file__).with_name("endpoints.yaml")
WORKFLOWS_PATH = Path(__file__).with_name("workflows.yaml")
ENTITIES_PATH = Path(__file__).with_name("entities.yaml")

KEY_HELP = (
    "MoySklad: Настройки → Пользователи → Токены доступа (Bearer-токен). "
    "Положите его в MOYSKLAD_TOKEN или в кабинет через ms_add_cabinet. "
    "Не вставляйте токен в чат."
)


def _build_headers(creds: dict[str, str]) -> dict[str, str]:
    """MoySklad auth + required headers.

    Primary: a personal access token -> 'Authorization: Bearer <token>'.
    Optional: login+password -> HTTP Basic, if a token is not supplied.
    MoySklad is strict about two headers (live-verified 2026-06-25):
      - Accept MUST be 'application/json;charset=utf-8' exactly. The engine's
        default 'application/json' is rejected with 400 code 1062. We override
        it here (build_headers is merged over the engine defaults).
      - Accept-Encoding MUST include gzip, or the request is rejected with 415.
    """
    headers = {
        "Accept": "application/json;charset=utf-8",
        "Accept-Encoding": "gzip",
    }
    token = creds.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        login, password = creds.get("login"), creds.get("password")
        if login and password:
            raw = f"{login}:{password}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    return headers


# MoySklad keeps its OWN cabinet store under ~/.moysklad-mcp — deliberately NOT
# the shared ~/.marketplace-mcp family store (decision 2026-06-26). One MoySklad
# home holds both the app copy (install.py) and the token store, so the path is
# obvious and never collides with Wildberries/Ozon cabinets. Override with
# MOYSKLAD_MCP_HOME (the same var install.py uses for the app dir).
MS_HOME = Path(os.environ.get("MOYSKLAD_MCP_HOME", Path.home() / ".moysklad-mcp"))
MS_STORE_PATH = MS_HOME / "cabinets.json"

MOYSKLAD_CONFIG = ServiceConfig(
    name="ms",
    scheme="https",
    fields=["token"],
    env_map={"token": "MOYSKLAD_TOKEN"},
    build_headers=_build_headers,
    user_agent="moysklad-mcp-ru/0.0.1 (+https://github.com/)",
    store=CredentialStore(path=MS_STORE_PATH),
    # whoami auto-naming deferred — needs a live-verified endpoint (/context/employee).
    whoami=None,
)

mcp = FastMCP("moysklad_mcp")
entities = EntityIndex.load(ENTITIES_PATH)
catalog = Catalog.from_yaml(CATALOG_PATH, entities=entities)
# Wrap the vendored client so the process write-guard covers EVERY mutating call
# (raw meta-tools included), not just the typed write tools. Core stays untouched.
client = GuardedClient(MarketplaceClient(MOYSKLAD_CONFIG))

register_generic_tools(
    mcp, svc="ms", client=client, catalog=catalog, entities=entities,
    key_help=KEY_HELP,
)
register_cabinet_tools(mcp, svc="ms", client=client, catalog=catalog)
register_workflow_tools(mcp, svc="ms", workflows=Workflows.from_yaml(WORKFLOWS_PATH))


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def _rubles(result: dict) -> dict:
    """Convert kopecks→rubles inside a successful envelope's data; pass errors through."""
    if isinstance(result, dict) and result.get("ok"):
        result = {**result, "data": convert_money(result.get("data")), "_money": "rubles"}
    return result


# --------------------------------------------------------------------------
# Typed convenience tools — everyday manager questions, one call each.
# They delegate to the same client; nothing is duplicated.
# --------------------------------------------------------------------------
@mcp.tool(
    name="ms_get_stock",
    annotations={"title": "MoySklad current stock", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ms_get_stock(stock_type: str = "quantity",
                       include_zero: bool = False) -> str:
    """Current stock snapshot, grouped by product (fast /report/stock/all/current).

    Args:
        stock_type: quantity | freeStock | reserve | inTransit | stock. Default quantity.
        include_zero: include zero-stock lines (adds include=zeroLines).
    Returns JSON: {"ok": true, "data": [ {assortmentId, <stock_type>}, ... ]}.
    No money in this report, so values are returned as-is (quantities).
    """
    spec = catalog.get("ms_stock_current")
    q: dict[str, object] = {"stockType": stock_type}
    if include_zero:
        q["include"] = "zeroLines"
    return _j(await client.call_spec(spec, query=q))


@mcp.tool(
    name="ms_get_products",
    annotations={"title": "MoySklad products (assortment)", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ms_get_products(limit: int = 100, offset: int = 0,
                          filter: Optional[str] = None,
                          rubles: bool = True) -> str:
    """List products/services/bundles (assortment) with prices and stock.

    Args:
        limit: page size, max 1000.
        offset: pagination offset.
        filter: optional MoySklad filter expression (e.g. "archived=false").
        rubles: convert kopeck money fields to rubles (default true).
    Returns JSON: {"ok": true, "data": {"meta", "rows": [ products ]}}.
    Sale prices and buy price are kopecks in the raw API; rubles=true converts them.
    """
    spec = catalog.get("ms_assortment_list")
    q: dict[str, object] = {"limit": min(limit, 1000), "offset": offset}
    if filter:
        q["filter"] = filter
    result = await client.call_spec(spec, query=q)
    return _j(_rubles(result) if rubles else result)


@mcp.tool(
    name="ms_get_orders",
    annotations={"title": "MoySklad customer orders", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ms_get_orders(limit: int = 100, offset: int = 0,
                        filter: Optional[str] = None,
                        rubles: bool = True) -> str:
    """List customer orders. Document total is "sum" (kopecks in raw API).

    Args:
        limit: page size, max 1000.
        offset: pagination offset.
        filter: optional MoySklad filter (e.g. "moment>=2026-06-01 00:00:00").
        rubles: convert "sum" and money fields to rubles (default true).
    Returns JSON: {"ok": true, "data": {"meta", "rows": [ orders ]}}.
    """
    spec = catalog.get("ms_customerorder_list")
    q: dict[str, object] = {"limit": min(limit, 1000), "offset": offset}
    if filter:
        q["filter"] = filter
    result = await client.call_spec(spec, query=q)
    return _j(_rubles(result) if rubles else result)


def _period(query: dict, moment_from: Optional[str], moment_to: Optional[str]) -> dict:
    """Attach momentFrom/momentTo if given (reports need a period)."""
    if moment_from:
        query["momentFrom"] = moment_from
    if moment_to:
        query["momentTo"] = moment_to
    return query


@mcp.tool(
    name="ms_get_profit",
    annotations={"title": "MoySklad profitability by product", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ms_get_profit(moment_from: Optional[str] = None,
                        moment_to: Optional[str] = None,
                        limit: int = 100, offset: int = 0,
                        rubles: bool = True) -> str:
    """Profitability by product (sale, cost, profit, margin). Money in kopecks.

    Args:
        moment_from / moment_to: period bounds "YYYY-MM-DD HH:MM:SS" (report needs them).
        limit/offset: pagination (rows under "rows"). rubles: kopecks→rubles (default true).
    Returns JSON: {"ok": true, "data": {"meta", "rows": [ ... ]}}.
    """
    spec = catalog.get("ms_get_profit")
    q = _period({"limit": min(limit, 1000), "offset": offset}, moment_from, moment_to)
    result = await client.call_spec(spec, query=q)
    return _j(_rubles(result) if rubles else result)


@mcp.tool(
    name="ms_get_money",
    annotations={"title": "MoySklad cash balances by account", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ms_get_money(rubles: bool = True) -> str:
    """Cash balances by account/cashbox (kopecks). For cashflow over time use
    ms_call_method('ms_get_report_money_plotseries', ...) from the map.

    Args:
        rubles: convert kopeck balances to rubles (default true).
    Returns JSON: {"ok": true, "data": {"meta", "rows": [ {account, balance, ...} ]}}.
    """
    spec = catalog.get("ms_get_money")
    result = await client.call_spec(spec, query={})
    return _j(_rubles(result) if rubles else result)


@mcp.tool(
    name="ms_get_turnover",
    annotations={"title": "MoySklad turnover by product", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ms_get_turnover(moment_from: Optional[str] = None,
                          moment_to: Optional[str] = None,
                          limit: int = 100, offset: int = 0,
                          rubles: bool = True) -> str:
    """Turnover by product: opening/income/outcome/closing in qty and money (kopecks).

    Args:
        moment_from / moment_to: period bounds "YYYY-MM-DD HH:MM:SS" (required by the report).
        limit/offset: pagination. rubles: kopecks→rubles (default true).
    Returns JSON: {"ok": true, "data": {"meta", "rows": [ ... ]}}.
    """
    spec = catalog.get("ms_get_turnover")
    q = _period({"limit": min(limit, 1000), "offset": offset}, moment_from, moment_to)
    result = await client.call_spec(spec, query=q)
    return _j(_rubles(result) if rubles else result)


@mcp.tool(
    name="ms_get_counterparties",
    annotations={"title": "MoySklad counterparties", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ms_get_counterparties(limit: int = 100, offset: int = 0,
                                filter: Optional[str] = None,
                                rubles: bool = True) -> str:
    """Counterparties (customers and suppliers). Balance fields in kopecks.

    Args:
        limit/offset: pagination. filter: MoySklad filter (e.g. "name~ООО").
        rubles: convert kopeck balance fields to rubles (default true).
    Returns JSON: {"ok": true, "data": {"meta", "rows": [ counterparties ]}}.
    """
    spec = catalog.get("ms_get_counterparties")
    q: dict[str, object] = {"limit": min(limit, 1000), "offset": offset}
    if filter:
        q["filter"] = filter
    result = await client.call_spec(spec, query=q)
    return _j(_rubles(result) if rubles else result)


@mcp.tool(
    name="ms_get_stores",
    annotations={"title": "MoySklad warehouses", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ms_get_stores(limit: int = 100, offset: int = 0) -> str:
    """Warehouses/stores (small dictionary). No money fields.

    Returns JSON: {"ok": true, "data": {"meta", "rows": [ {name, id, ...} ]}}.
    """
    spec = catalog.get("ms_get_stores")
    return _j(await client.call_spec(spec, query={"limit": min(limit, 1000), "offset": offset}))


# doc_type -> curated operation_id for the role documents (read).
_DOC_TYPES = {
    "demand": "ms_demand_list",                 # отгрузки
    "supply": "ms_supply_list",                 # приёмки
    "purchaseorder": "ms_purchaseorder_list",   # заказы поставщику
    "invoiceout": "ms_invoiceout_list",         # счета покупателям
    "invoicein": "ms_invoicein_list",           # счета поставщиков
    "salesreturn": "ms_salesreturn_list",       # возвраты покупателей
    "purchasereturn": "ms_purchasereturn_list",  # возвраты поставщикам
}


@mcp.tool(
    name="ms_get_documents",
    annotations={"title": "MoySklad role documents (read)", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ms_get_documents(doc_type: str, limit: int = 100, offset: int = 0,
                           filter: Optional[str] = None,
                           rubles: bool = True) -> str:
    """List a role document by type. Document total in "sum" (kopecks).

    Args:
        doc_type: one of demand | supply | purchaseorder | invoiceout |
            invoicein | salesreturn | purchasereturn.
        limit/offset: pagination. filter: MoySklad filter (e.g. "moment>=2026-06-01 00:00:00").
        rubles: convert "sum" and money fields to rubles (default true).
    Returns JSON: {"ok": true, "data": {"meta", "rows": [ documents ]}}.
    """
    op = _DOC_TYPES.get(doc_type)
    if not op:
        return _j({"error": "invalid_params", "doc_type": doc_type,
                   "allowed": sorted(_DOC_TYPES)})
    spec = catalog.get(op)
    q: dict[str, object] = {"limit": min(limit, 1000), "offset": offset}
    if filter:
        q["filter"] = filter
    result = await client.call_spec(spec, query=q)
    return _j(_rubles(result) if rubles else result)


@mcp.tool(
    name="ms_ping",
    annotations={"title": "MoySklad live auth check", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ms_ping() -> str:
    """Live connectivity + auth check: GET assortment?limit=1.

    Returns {"ok": true, "status": 200, "data": {...}} when the token works, or
    the canonical error envelope (auth/forbidden/network/...) otherwise. Use this
    on the cabinet to confirm the token before anything else.
    """
    spec = catalog.get("ms_assortment_list")
    return _j(await client.call_spec(spec, query={"limit": 1}))


# --------------------------------------------------------------------------
# WRITE (Phase 2) — behind two gates: the per-process write-guard
# (MOYSKLAD_ALLOW_WRITE, default off) AND the per-call safety gate
# (confirm_write / i_understand_this_modifies_data). Money goes out in kopecks.
# Create makes a DRAFT (applicable=false); posting is a separate destructive step.
# --------------------------------------------------------------------------
_ENTITY = "/api/remap/1.2/entity/"

# doc_type == entity path segment for all role documents (live/doc-verified).
_WRITE_DOC_TYPES = {
    "demand", "supply", "purchaseorder", "invoiceout",
    "invoicein", "salesreturn", "purchasereturn",
}


def _host() -> str:
    return catalog.default_host or "api.moysklad.ru"


async def _assemble_order_document(*, agent: str, organization: str, store: str,
                                   positions, moment, name, description) -> dict:
    """Resolve names -> refs and assemble the kopeck body for an order-like
    document. The skeleton (organization + agent + optional store + positions) is
    identical for all role docs (purchaseorder/supply/demand/invoicein/invoiceout/
    salesreturn/purchasereturn) — live-verified 2026-06-26 — so the caller only
    varies the POST entity path by doc_type.

    READ-only (resolves via list endpoints); sends no write. Returns
    {"ok": True, "body": {...}, "resolved": {...}, "summary": [...]} or a
    canonical error envelope (the first failed resolution, unguessed).
    """
    if not agent:
        return make_error("invalid_params", "Нужен agent (поставщик).", retryable=False)
    ar = await resolve_ref(client, "counterparty", name=agent)
    if not ar.get("ok"):
        return ar
    # own legal entity — auto-pick the only one when not named.
    orr = await resolve_ref(client, "organization",
                            name=(organization or None), allow_single=not organization)
    if not orr.get("ok"):
        return orr
    store_meta = store_name = None
    if store:
        sr = await resolve_ref(client, "store", name=store)
        if not sr.get("ok"):
            return sr
        store_meta, store_name = sr["meta"], sr["name"]

    built, summary = [], []
    for i, p in enumerate(positions or []):
        if not isinstance(p, dict) or not p.get("product"):
            return make_error("invalid_params",
                              f"Позиция #{i + 1}: нужен 'product' (название товара).",
                              retryable=False)
        pr = await resolve_ref(client, "assortment", name=p["product"])
        if not pr.get("ok"):
            return pr
        qty = p.get("quantity", 1)
        price = p.get("price", 0)
        built.append(position(assortment_meta=pr["meta"], quantity=qty, price=price,
                              discount=p.get("discount", 0), vat=p.get("vat")))
        summary.append(f'{pr["name"]} × {qty} @ {price} руб')

    body_rub = document_body(
        organization_meta=orr["meta"], agent_meta=ar["meta"], store_meta=store_meta,
        positions=built, moment=moment, name=name, description=description,
        applicable=False,
    )
    return {
        "ok": True,
        "body": convert_money_to_kopecks(body_rub),  # rubles -> kopecks for the API
        "resolved": {"agent": ar["name"], "organization": orr["name"], "store": store_name},
        "summary": summary,
    }


@mcp.tool(
    name="ms_build_purchaseorder",
    annotations={"title": "MoySklad build purchase order (preview, no write)",
                 "readOnlyHint": True, "openWorldHint": True},
)
async def ms_build_purchaseorder(agent: str, organization: str = "", store: str = "",
                                 positions: Optional[list] = None,
                                 moment: Optional[str] = None, name: Optional[str] = None,
                                 description: Optional[str] = None) -> str:
    """PREVIEW a purchase order: resolve names to refs and show the EXACT body
    ms_create_purchaseorder would send (money already kopecks). Performs READS to
    resolve names; sends NO write. Inspect the body/summary before creating.

    Args:
        agent: supplier counterparty name (поставщик) — required.
        organization: own legal entity; omit to auto-use the only one on the cabinet.
        store: warehouse name (optional).
        positions: list of {"product": name, "quantity": n, "price": rubles,
            optional "discount" %, "vat" %}.
        moment/name/description: optional fields. moment is "YYYY-MM-DD HH:MM:SS".
    Returns {"ok": true, "body", "resolved", "summary"} or an error envelope.
    """
    res = await _assemble_order_document(agent=agent, organization=organization,
                                        store=store, positions=positions, moment=moment,
                                        name=name, description=description)
    if res.get("ok"):
        res = {**res, "note": "PREVIEW — ничего не отправлено. Создать черновик: "
               "ms_create_purchaseorder с теми же аргументами + confirm_write=true."}
    return _j(res)


@mcp.tool(
    name="ms_create_purchaseorder",
    annotations={"title": "MoySklad create purchase order (draft)",
                 "readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
)
async def ms_create_purchaseorder(agent: str, organization: str = "", store: str = "",
                                  positions: Optional[list] = None,
                                  moment: Optional[str] = None, name: Optional[str] = None,
                                  description: Optional[str] = None,
                                  confirm_write: bool = False) -> str:
    """Create a purchase order as a DRAFT (applicable=false — not posted, moves
    nothing). WRITE — requires confirm_write=true. Posting is separate
    (ms_post_document). Writes also require MOYSKLAD_ALLOW_WRITE=1 (off by default).

    Args: same as ms_build_purchaseorder, plus confirm_write.
    Returns the created document envelope {"ok": true, "data": {... "id" ...}},
    or the guard/gate error (nothing sent).
    """
    guard = check_write_guard(client)
    if guard:
        return _j(guard)
    gate = check_gate("write", confirm_write=confirm_write,
                      i_understand_this_modifies_data=False,
                      endpoint="/entity/purchaseorder")
    if gate:
        return _j(gate)
    res = await _assemble_order_document(agent=agent, organization=organization,
                                        store=store, positions=positions, moment=moment,
                                        name=name, description=description)
    if not res.get("ok"):
        return _j(res)
    resp = await client.request("POST", _host(), _ENTITY + "purchaseorder",
                                json_body=res["body"], operation_id="ms_create_purchaseorder")
    if isinstance(resp, dict) and resp.get("ok"):
        resp = {**resp, "resolved": res["resolved"], "summary": res["summary"],
                "posted": False,
                "next": "Документ создан ЧЕРНОВИКОМ (не проведён). Провести: "
                        "ms_post_document(doc_type='purchaseorder', doc_id=<id>)."}
    return _j(resp)


@mcp.tool(
    name="ms_build_document",
    annotations={"title": "MoySklad build a role document (preview, no write)",
                 "readOnlyHint": True, "openWorldHint": True},
)
async def ms_build_document(doc_type: str, agent: str, organization: str = "",
                            store: str = "", positions: Optional[list] = None,
                            moment: Optional[str] = None, name: Optional[str] = None,
                            description: Optional[str] = None) -> str:
    """PREVIEW any role document: resolve names to refs and show the EXACT body
    ms_create_document would send (money already kopecks). READS only; no write.

    Args:
        doc_type: one of demand | supply | purchaseorder | invoiceout |
            invoicein | salesreturn | purchasereturn.
        agent: counterparty name — supplier for supply/invoicein/purchasereturn/
            purchaseorder, customer for demand/invoiceout/salesreturn.
        organization: own legal entity; omit to auto-use the only one on the cabinet.
        store: warehouse name. supply/demand move stock, so a store is expected;
            optional for the others.
        positions: list of {"product": name, "quantity": n, "price": rubles,
            optional "discount" %, "vat" %}.
        moment/name/description: optional. moment is "YYYY-MM-DD HH:MM:SS".
    Returns {"ok": true, "doc_type", "body", "resolved", "summary"} or an error.
    """
    if doc_type not in _WRITE_DOC_TYPES:
        return _j(make_error("invalid_params", f"doc_type {doc_type!r} не поддержан.",
                             retryable=False, details={"allowed": sorted(_WRITE_DOC_TYPES)}))
    res = await _assemble_order_document(agent=agent, organization=organization,
                                         store=store, positions=positions, moment=moment,
                                         name=name, description=description)
    if res.get("ok"):
        res = {**res, "doc_type": doc_type,
               "note": f"PREVIEW — ничего не отправлено. Создать черновик: "
                       f"ms_create_document(doc_type='{doc_type}', …) + confirm_write=true."}
    return _j(res)


@mcp.tool(
    name="ms_create_document",
    annotations={"title": "MoySklad create a role document (draft)",
                 "readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
)
async def ms_create_document(doc_type: str, agent: str, organization: str = "",
                             store: str = "", positions: Optional[list] = None,
                             moment: Optional[str] = None, name: Optional[str] = None,
                             description: Optional[str] = None,
                             confirm_write: bool = False) -> str:
    """Create ANY role document as a DRAFT (applicable=false — not posted, moves
    nothing). WRITE — requires confirm_write=true AND MOYSKLAD_ALLOW_WRITE=1.
    Posting is a separate destructive step (ms_post_document). One body shape fits
    every order-like document (live-verified 2026-06-26 on all 6 types).

    Args:
        doc_type: one of demand | supply | purchaseorder | invoiceout |
            invoicein | salesreturn | purchasereturn.
        agent / organization / store / positions / moment / name / description:
            same as ms_build_document.
        confirm_write: required (write gate).
    Returns the created document envelope {"ok": true, "data": {... "id" ...}},
    or the guard/gate/validation error (nothing sent).
    """
    if doc_type not in _WRITE_DOC_TYPES:
        return _j(make_error("invalid_params", f"doc_type {doc_type!r} не поддержан.",
                             retryable=False, details={"allowed": sorted(_WRITE_DOC_TYPES)}))
    guard = check_write_guard(client)
    if guard:
        return _j(guard)
    gate = check_gate("write", confirm_write=confirm_write,
                      i_understand_this_modifies_data=False,
                      endpoint=f"/entity/{doc_type}")
    if gate:
        return _j(gate)
    res = await _assemble_order_document(agent=agent, organization=organization,
                                         store=store, positions=positions, moment=moment,
                                         name=name, description=description)
    if not res.get("ok"):
        return _j(res)
    resp = await client.request("POST", _host(), _ENTITY + doc_type,
                                json_body=res["body"], operation_id="ms_create_document")
    if isinstance(resp, dict) and resp.get("ok"):
        resp = {**resp, "doc_type": doc_type, "resolved": res["resolved"],
                "summary": res["summary"], "posted": False,
                "next": f"Документ создан ЧЕРНОВИКОМ (не проведён). Провести: "
                        f"ms_post_document(doc_type='{doc_type}', doc_id=<id>)."}
    return _j(resp)


@mcp.tool(
    name="ms_post_document",
    annotations={"title": "MoySklad post (провести) a document",
                 "readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
)
async def ms_post_document(doc_type: str, doc_id: str, confirm_write: bool = False,
                           i_understand_this_modifies_data: bool = False) -> str:
    """POST / провести a document: sets applicable=true, which MOVES STOCK AND
    MONEY in the books. DESTRUCTIVE — requires confirm_write=true AND
    i_understand_this_modifies_data=true. Separate from creation on purpose.

    Args:
        doc_type: one of demand|supply|purchaseorder|invoiceout|invoicein|
            salesreturn|purchasereturn.
        doc_id: document id (the "id" field returned by create).
    Returns the updated document envelope, or the guard/gate error (nothing sent).
    """
    if doc_type not in _WRITE_DOC_TYPES:
        return _j(make_error("invalid_params", f"doc_type {doc_type!r} не поддержан.",
                             retryable=False, details={"allowed": sorted(_WRITE_DOC_TYPES)}))
    guard = check_write_guard(client)
    if guard:
        return _j(guard)
    gate = check_gate("destructive", confirm_write=confirm_write,
                      i_understand_this_modifies_data=i_understand_this_modifies_data,
                      endpoint=f"/entity/{doc_type}/{doc_id}")
    if gate:
        return _j(gate)
    resp = await client.request("PUT", _host(), f"{_ENTITY}{doc_type}/{doc_id}",
                                json_body={"applicable": True},
                                operation_id="ms_post_document")
    return _j(resp)


@mcp.tool(
    name="ms_delete_document",
    annotations={"title": "MoySklad delete a document",
                 "readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
)
async def ms_delete_document(doc_type: str, doc_id: str, confirm_write: bool = False,
                             i_understand_this_modifies_data: bool = False) -> str:
    """DELETE a document — e.g. remove a test draft to clean up. DESTRUCTIVE —
    requires both confirmations.

    Args:
        doc_type: one of demand|supply|purchaseorder|invoiceout|invoicein|
            salesreturn|purchasereturn.
        doc_id: document id.
    Returns {"ok": true, "status": 200} on success, or the guard/gate error.
    """
    if doc_type not in _WRITE_DOC_TYPES:
        return _j(make_error("invalid_params", f"doc_type {doc_type!r} не поддержан.",
                             retryable=False, details={"allowed": sorted(_WRITE_DOC_TYPES)}))
    guard = check_write_guard(client)
    if guard:
        return _j(guard)
    gate = check_gate("destructive", confirm_write=confirm_write,
                      i_understand_this_modifies_data=i_understand_this_modifies_data,
                      endpoint=f"/entity/{doc_type}/{doc_id}")
    if gate:
        return _j(gate)
    resp = await client.request("DELETE", _host(), f"{_ENTITY}{doc_type}/{doc_id}",
                                operation_id="ms_delete_document")
    return _j(resp)


def main() -> None:
    """Console entry point (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
