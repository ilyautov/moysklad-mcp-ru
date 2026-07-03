"""Process-level guard for write operations (Phase 2).

Two independent layers protect a mutation:
  - core safety gate (per call): confirm_write / i_understand flags.
  - THIS guard (per process): writes are OFF by default and must be switched on
    explicitly, optionally pinned to a named test cabinet.

Why a second layer: the token lives locally and the active cabinet may point at
real books. A confirm flag protects against a careless call; this guard protects
against the whole process being aimed at production by accident. Default off.

Env:
  MOYSKLAD_ALLOW_WRITE   truthy (1/true/yes/on) to permit writes at all.
  MOYSKLAD_WRITE_CABINETS optional comma list of cabinet names allowed for write.
                          When set, the active cabinet must be one of them.
"""
from __future__ import annotations

import os
from typing import Optional

from core.errors import make_error

_TRUTHY = {"1", "true", "yes", "on"}


def _truthy(value: Optional[str]) -> bool:
    return str(value).strip().lower() in _TRUTHY if value is not None else False


def evaluate_write_guard(*, allow_write: Optional[str], allowlist: Optional[str],
                         active_cabinet: Optional[str]) -> Optional[dict]:
    """Pure policy. Return an error envelope if writes are NOT permitted, else None.

    Kept free of os.environ so it is unit-testable with explicit inputs.
    """
    if not _truthy(allow_write):
        return make_error(
            "forbidden",
            "Запись выключена по умолчанию. Включи MOYSKLAD_ALLOW_WRITE=1 и направляй "
            "ТОЛЬКО на тестовый кабинет (не на боевой). Ничего не отправлено.",
            retryable=False,
            details={"http_call_skipped": True, "required": ["MOYSKLAD_ALLOW_WRITE=1"]},
        )
    names = [n.strip() for n in (allowlist or "").split(",") if n.strip()]
    if names and (active_cabinet or "") not in names:
        return make_error(
            "forbidden",
            f"Активный кабинет {active_cabinet!r} не в списке записи "
            f"MOYSKLAD_WRITE_CABINETS={names}. Отказ писать в не-разрешённый кабинет. "
            "Ничего не отправлено.",
            retryable=False,
            details={"http_call_skipped": True, "active_cabinet": active_cabinet,
                     "allowed": names},
        )
    return None


def check_write_guard(client) -> Optional[dict]:
    """Env+cabinet wrapper around evaluate_write_guard for live tools."""
    try:
        info = client.config.store.list_cabinets(client.config.name)
        active = info.get("active")
    except Exception:  # noqa: BLE001 — env-token install may have no cabinet store
        active = None
    return evaluate_write_guard(
        allow_write=os.environ.get("MOYSKLAD_ALLOW_WRITE"),
        allowlist=os.environ.get("MOYSKLAD_WRITE_CABINETS"),
        active_cabinet=active,
    )


_WRITE_VERBS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class GuardedClient:
    """Compose the process write-guard over the vendored core client so EVERY
    mutating HTTP call passes it — not only the typed write tools. The generic
    meta-tools (`ms_call_method` / `ms_call_raw`) reach the network through
    `client.request` / `client.call_spec`; wrapping BOTH closes the gap where a
    raw write could hit a (possibly production) cabinet while writes are globally
    disabled. GET/read calls pass through untouched (no guard, no overhead).

    Core is NOT patched — this is composition in our layer. Attribute access
    (config, store, …) delegates to the inner client, so `check_write_guard(self)`
    and the cabinet tools keep working unchanged.
    """

    def __init__(self, inner) -> None:
        self._inner = inner

    def __getattr__(self, name: str):
        if name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)

    async def request(self, method: str, *args, **kwargs):
        if str(method).upper() in _WRITE_VERBS:
            blocked = check_write_guard(self._inner)
            if blocked:
                return blocked
        return await self._inner.request(method, *args, **kwargs)

    async def call_spec(self, spec, *args, **kwargs):
        if str(getattr(spec, "method", "GET")).upper() in _WRITE_VERBS:
            blocked = check_write_guard(self._inner)
            if blocked:
                return blocked
        return await self._inner.call_spec(spec, *args, **kwargs)
