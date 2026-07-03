"""Resolve human names to MoySklad meta references for write payloads.

A MoySklad document references other entities by `meta`
({href, type, mediaType}). To build one from human input ("поставщик Ромашка",
"товар Цепь ГРМ") we look the entity up by its read endpoint and extract a
minimal meta. READS ONLY — никаких мутаций. Ambiguity (0 or >1 match) is
returned as an error envelope, never guessed: picking the wrong agent or product
silently is worse than failing loudly.

Split for testability: `choose()` is pure (selection logic over rows, no
network); `resolve_ref()` does the read call then delegates to `choose()`.
"""
from __future__ import annotations

from typing import Any, Optional

from core.errors import make_error

API_ENTITY = "/api/remap/1.2/entity/"
DEFAULT_HOST = "api.moysklad.ru"

# Reference kind -> entity path segment (MoySklad entity name).
ENTITY_PATH = {
    "organization": "organization",   # своя организация (продавец)
    "counterparty": "counterparty",   # контрагент (поставщик/покупатель)
    "store": "store",                 # склад
    "assortment": "assortment",       # товар/услуга/комплект/модификация
}


def extract_meta(row: Any) -> Optional[dict]:
    """Minimal reference meta from an entity row. None if there is no href.

    MoySklad accepts a reference as {"meta": {href, type, mediaType}}; extra
    fields in the read meta (uuidHref, metadataHref) are dropped to keep the
    body clean.
    """
    if not isinstance(row, dict):
        return None
    meta = row.get("meta")
    if not isinstance(meta, dict) or not meta.get("href"):
        return None
    out = {"href": meta["href"], "mediaType": meta.get("mediaType", "application/json")}
    if meta.get("type"):
        out["type"] = meta["type"]
    return out


def _name(row: Any) -> str:
    return str(row.get("name", "")).strip() if isinstance(row, dict) else ""


def choose(rows: list, *, kind: str, name: Optional[str] = None,
           allow_single: bool = False) -> dict:
    """Pure selection over already-fetched rows.

    Returns {"ok": True, "meta": {...}, "name": str} on a unique resolution, or
    a canonical error envelope (not_found / invalid_params) describing why it
    could not pick exactly one.
    """
    rows = rows if isinstance(rows, list) else []
    if name:
        wanted = name.strip().lower()
        exact = [r for r in rows if _name(r).lower() == wanted]
        pick = exact or rows
        if len(pick) == 1:
            meta = extract_meta(pick[0])
            if not meta:
                return make_error("invalid_params",
                                  f"{kind} «{name}»: запись без meta.href.",
                                  retryable=False)
            return {"ok": True, "meta": meta, "name": _name(pick[0])}
        if not pick:
            return make_error("not_found",
                              f"{kind}: ничего не найдено по name~«{name}». Уточни название.",
                              retryable=False)
        names = [_name(r) for r in pick[:10]]
        return make_error("invalid_params",
                          f"{kind}: под «{name}» подходит {len(pick)}, уточни. "
                          f"Кандидаты: {names}",
                          retryable=False, details={"candidates": names})
    # no name given
    if allow_single:
        if len(rows) == 1:
            meta = extract_meta(rows[0])
            if meta:
                return {"ok": True, "meta": meta, "name": _name(rows[0])}
            return make_error("invalid_params",
                              f"{kind}: единственная запись без meta.href.", retryable=False)
        if not rows:
            return make_error("not_found", f"{kind}: на кабинете нет ни одной записи.",
                              retryable=False)
        names = [_name(r) for r in rows[:10]]
        return make_error("invalid_params",
                          f"{kind}: на кабинете {len(rows)} шт., передай name. "
                          f"Например: {names}",
                          retryable=False, details={"candidates": names})
    return make_error("invalid_params", f"{kind}: нужно имя (name).", retryable=False)


def _rows_of(resp: Any) -> list:
    data = resp.get("data") if isinstance(resp, dict) else None
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return data["rows"]
    return []


async def resolve_ref(client, kind: str, *, name: Optional[str] = None,
                      allow_single: bool = False, host: str = DEFAULT_HOST) -> dict:
    """Resolve one entity by name to {"ok": True, "meta": {...}, "name": ...}.

    Read-only: lists the entity (filtered by name~ when given) and delegates the
    pick to `choose()`. Propagates a read error (auth/network/...) unchanged.
    """
    seg = ENTITY_PATH.get(kind)
    if not seg:
        return make_error("invalid_params", f"Неизвестный тип ссылки {kind!r}.",
                          retryable=False)
    query: dict[str, Any] = {"limit": 100}
    if name:
        query["filter"] = f"name~{name}"
    resp = await client.request("GET", host, API_ENTITY + seg, query=query)
    if not (isinstance(resp, dict) and resp.get("ok")):
        return resp  # propagate the read failure (auth/forbidden/network/...)
    return choose(_rows_of(resp), kind=kind, name=name, allow_single=allow_single)
