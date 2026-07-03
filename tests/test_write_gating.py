"""End-to-end gating of the write tools. No network, no token: the guard and the
safety gate both return BEFORE any HTTP call, so these run fully offline.

Covers the Phase 2 invariant that matters most: a mutation cannot leave the
machine unless (1) writes are switched on for the process AND (2) the per-call
confirmation(s) are present — two for a destructive op like posting/deleting.
"""
import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.safety import check_gate  # noqa: E402
from moysklad_mcp.server import (  # noqa: E402
    _DOC_TYPES, _WRITE_DOC_TYPES, catalog,
    ms_build_document, ms_build_purchaseorder,
    ms_create_document, ms_create_purchaseorder,
    ms_delete_document, ms_post_document,
)


def _run(coro):
    return json.loads(asyncio.run(coro))


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


# --- core gate semantics our tools rely on ------------------------------------

def test_gate_write_needs_one_confirm():
    assert check_gate("write", confirm_write=False,
                      i_understand_this_modifies_data=False) is not None
    assert check_gate("write", confirm_write=True,
                      i_understand_this_modifies_data=False) is None


def test_gate_destructive_needs_both_confirms():
    assert check_gate("destructive", confirm_write=True,
                      i_understand_this_modifies_data=False) is not None
    assert check_gate("destructive", confirm_write=False,
                      i_understand_this_modifies_data=True) is not None
    assert check_gate("destructive", confirm_write=True,
                      i_understand_this_modifies_data=True) is None


# --- guard fires first: writes off by default ---------------------------------

def test_create_blocked_when_writes_disabled():
    # confirm_write=True is not enough — the process-level guard blocks first.
    with _env(MOYSKLAD_ALLOW_WRITE=None, MOYSKLAD_WRITE_CABINETS=None):
        r = _run(ms_create_purchaseorder(agent="Ромашка", confirm_write=True))
    assert r["error_type"] == "forbidden"
    assert r["details"]["http_call_skipped"] is True


def test_post_blocked_when_writes_disabled():
    with _env(MOYSKLAD_ALLOW_WRITE=None, MOYSKLAD_WRITE_CABINETS=None):
        r = _run(ms_post_document(doc_type="purchaseorder", doc_id="x",
                                  confirm_write=True, i_understand_this_modifies_data=True))
    assert r["error_type"] == "forbidden"
    assert r["details"]["http_call_skipped"] is True


# --- with writes enabled, the per-call gate still applies ---------------------

def test_create_needs_confirm_even_when_enabled():
    with _env(MOYSKLAD_ALLOW_WRITE="1", MOYSKLAD_WRITE_CABINETS=None):
        r = _run(ms_create_purchaseorder(agent="Ромашка", confirm_write=False))
    assert r["error_type"] == "safety_gate"
    assert r["details"]["http_call_skipped"] is True


def test_post_needs_both_confirms_even_when_enabled():
    with _env(MOYSKLAD_ALLOW_WRITE="1", MOYSKLAD_WRITE_CABINETS=None):
        r = _run(ms_post_document(doc_type="purchaseorder", doc_id="x",
                                  confirm_write=True))  # missing i_understand
    assert r["error_type"] == "safety_gate"
    assert any("i_understand" in s for s in r["details"]["required"])


def test_delete_needs_both_confirms_even_when_enabled():
    with _env(MOYSKLAD_ALLOW_WRITE="1", MOYSKLAD_WRITE_CABINETS=None):
        r = _run(ms_delete_document(doc_type="demand", doc_id="x", confirm_write=True))
    assert r["error_type"] == "safety_gate"


# --- input validation (no network) --------------------------------------------

def test_post_rejects_unknown_doc_type():
    r = _run(ms_post_document(doc_type="bogus", doc_id="x",
                              confirm_write=True, i_understand_this_modifies_data=True))
    assert r["error_type"] == "invalid_params"
    assert "purchaseorder" in r["details"]["allowed"]


def test_preview_requires_agent_and_is_read_only():
    # Preview performs no write and needs no guard; empty agent fails fast, offline.
    with _env(MOYSKLAD_ALLOW_WRITE=None):
        r = _run(ms_build_purchaseorder(agent=""))
    assert r["error_type"] == "invalid_params"


def test_every_write_doc_type_has_read_spec_for_readback():
    # post/delete target these entities; each must have a curated read spec so
    # the document can be read back and verified after a write.
    for dt in _WRITE_DOC_TYPES:
        op = _DOC_TYPES.get(dt)
        assert op, f"{dt}: no read-op mapping in _DOC_TYPES"
        spec = catalog.get(op)
        assert spec is not None, f"{op}: missing from catalog"
        assert spec.safety == "read", f"{op}: read-back spec must be read"


# --- generic ms_create_document / ms_build_document (veer, all role types) -----

def test_create_document_blocked_when_writes_disabled():
    # Same two-gate invariant as the typed PO tool, for any doc_type.
    with _env(MOYSKLAD_ALLOW_WRITE=None, MOYSKLAD_WRITE_CABINETS=None):
        r = _run(ms_create_document(doc_type="supply", agent="Ромашка", confirm_write=True))
    assert r["error_type"] == "forbidden"
    assert r["details"]["http_call_skipped"] is True


def test_create_document_needs_confirm_even_when_enabled():
    with _env(MOYSKLAD_ALLOW_WRITE="1", MOYSKLAD_WRITE_CABINETS=None):
        r = _run(ms_create_document(doc_type="demand", agent="Ромашка", confirm_write=False))
    assert r["error_type"] == "safety_gate"
    assert r["details"]["http_call_skipped"] is True


def test_create_document_rejects_unknown_doc_type():
    # doc_type is validated first, offline — before guard/gate/network.
    r = _run(ms_create_document(doc_type="bogus", agent="Ромашка", confirm_write=True))
    assert r["error_type"] == "invalid_params"
    assert "supply" in r["details"]["allowed"]


def test_build_document_rejects_unknown_doc_type():
    r = _run(ms_build_document(doc_type="bogus", agent="Ромашка"))
    assert r["error_type"] == "invalid_params"


def test_build_document_requires_agent_offline():
    # Valid doc_type, empty agent -> fails fast in assembly, no network.
    with _env(MOYSKLAD_ALLOW_WRITE=None):
        r = _run(ms_build_document(doc_type="supply", agent=""))
    assert r["error_type"] == "invalid_params"
