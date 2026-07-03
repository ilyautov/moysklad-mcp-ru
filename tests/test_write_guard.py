"""Write-guard policy. No network, no token, no env (inputs passed explicitly)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moysklad_mcp.write_guard import evaluate_write_guard  # noqa: E402


def test_writes_off_by_default():
    err = evaluate_write_guard(allow_write=None, allowlist=None, active_cabinet="test")
    assert err is not None
    assert err["error_type"] == "forbidden"
    assert err["details"]["http_call_skipped"] is True


def test_writes_off_when_flag_falsy():
    for v in ("0", "false", "no", "", "off"):
        err = evaluate_write_guard(allow_write=v, allowlist=None, active_cabinet="test")
        assert err is not None, f"{v!r} must keep writes off"


def test_writes_on_with_flag_no_allowlist():
    assert evaluate_write_guard(allow_write="1", allowlist=None, active_cabinet="anything") is None


def test_truthy_variants_enable():
    for v in ("1", "true", "YES", "On", " true "):
        assert evaluate_write_guard(allow_write=v, allowlist=None, active_cabinet="t") is None, v


def test_allowlist_blocks_non_listed_cabinet():
    err = evaluate_write_guard(allow_write="1", allowlist="test,sandbox",
                               active_cabinet="production")
    assert err is not None
    assert err["error_type"] == "forbidden"
    assert err["details"]["active_cabinet"] == "production"


def test_allowlist_permits_listed_cabinet():
    assert evaluate_write_guard(allow_write="1", allowlist="test, sandbox",
                                active_cabinet="sandbox") is None


def test_allowlist_set_but_no_active_cabinet_blocks():
    # env-token install (no named cabinet) + an allowlist -> cannot verify -> block.
    err = evaluate_write_guard(allow_write="1", allowlist="test", active_cabinet=None)
    assert err is not None


# --- GuardedClient: process guard on EVERY mutating call (closes raw tools) ----

import asyncio  # noqa: E402
import contextlib  # noqa: E402
import os  # noqa: E402

from moysklad_mcp.write_guard import GuardedClient  # noqa: E402


class _Spec:
    def __init__(self, method):
        self.method = method


class _FakeInner:
    """Minimal stand-in for the core client. Records whether the network method
    was actually reached, so we can prove the guard blocks BEFORE any send."""
    class _Store:
        def list_cabinets(self, name):
            return {"active": None, "cabinets": []}

    class _Cfg:
        name = "ms"
        store = None

    def __init__(self):
        self.config = self._Cfg()
        self.config.store = self._Store()
        self.requested = []
        self.specced = []

    async def request(self, method, *a, **kw):
        self.requested.append(method)
        return {"ok": True, "sent": True}

    async def call_spec(self, spec, *a, **kw):
        self.specced.append(spec.method)
        return {"ok": True, "sent": True}


@contextlib.contextmanager
def _env(**kw):
    old = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def _run(coro):
    return asyncio.run(coro)


def test_guarded_request_blocks_write_when_disabled():
    inner = _FakeInner()
    g = GuardedClient(inner)
    with _env(MOYSKLAD_ALLOW_WRITE=None, MOYSKLAD_WRITE_CABINETS=None):
        r = _run(g.request("POST", "host", "/entity/supply", json_body={}))
    assert r["error_type"] == "forbidden"
    assert inner.requested == []  # network NOT reached


def test_guarded_request_allows_write_when_enabled():
    inner = _FakeInner()
    g = GuardedClient(inner)
    with _env(MOYSKLAD_ALLOW_WRITE="1", MOYSKLAD_WRITE_CABINETS=None):
        r = _run(g.request("POST", "host", "/entity/supply", json_body={}))
    assert r == {"ok": True, "sent": True}
    assert inner.requested == ["POST"]


def test_guarded_reads_always_pass():
    inner = _FakeInner()
    g = GuardedClient(inner)
    with _env(MOYSKLAD_ALLOW_WRITE=None):
        r = _run(g.request("GET", "host", "/entity/assortment"))
    assert r == {"ok": True, "sent": True}
    assert inner.requested == ["GET"]


def test_guarded_call_spec_blocks_write_verb_when_disabled():
    inner = _FakeInner()
    g = GuardedClient(inner)
    with _env(MOYSKLAD_ALLOW_WRITE=None, MOYSKLAD_WRITE_CABINETS=None):
        r = _run(g.call_spec(_Spec("DELETE")))
    assert r["error_type"] == "forbidden"
    assert inner.specced == []


def test_guarded_call_spec_read_passes():
    inner = _FakeInner()
    g = GuardedClient(inner)
    with _env(MOYSKLAD_ALLOW_WRITE=None):
        r = _run(g.call_spec(_Spec("GET")))
    assert r == {"ok": True, "sent": True}
    assert inner.specced == ["GET"]


def test_guarded_attr_delegates_to_inner():
    g = GuardedClient(_FakeInner())
    assert g.config.name == "ms"  # __getattr__ delegation


def test_server_wires_guarded_client():
    from moysklad_mcp.server import client as server_client
    assert type(server_client).__name__ == "GuardedClient"
