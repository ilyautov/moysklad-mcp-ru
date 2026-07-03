"""Catalog safety integrity. No network, no token.

Guards the invariant that matters once writes land: no mutating verb may be
labelled `read`, and every declared safety level is valid. Cheap now (all read),
but it is the CI gate that protects the write phase.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.registry import Catalog  # noqa: E402
from core.safety import SAFETY_LEVELS, infer_safety  # noqa: E402

CATALOG_PATH = Path(__file__).resolve().parents[1] / "moysklad_mcp" / "endpoints.yaml"
MUTATING_VERBS = {"PUT", "PATCH", "DELETE"}
ALL_VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
API_PREFIX = "/api/remap/1.2/"
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}")


def _catalog():
    return Catalog.from_yaml(CATALOG_PATH)


def test_catalog_loads_and_nonempty():
    specs = _catalog().all()
    # The generated map is large; a sharp drop means the parser regressed.
    assert len(specs) >= 500, f"map too small ({len(specs)}) — parser regression?"
    ids = {s.operation_id for s in specs}
    assert {"ms_stock_current", "ms_stock_all",
            "ms_assortment_list", "ms_customerorder_list"} <= ids


def test_every_safety_level_valid():
    for s in _catalog().all():
        assert s.safety in SAFETY_LEVELS, f"{s.operation_id}: bad safety {s.safety!r}"


def test_no_mutating_verb_labelled_read():
    for s in _catalog().all():
        if s.method.upper() in MUTATING_VERBS:
            assert s.safety != "read", f"{s.operation_id}: {s.method} cannot be read"
        # infer_safety must never downgrade a mutating verb below its floor
        assert infer_safety(s.method, s.safety) != "read" or s.method.upper() == "GET"


def test_items_path_for_metaarray_lists():
    cat = _catalog()
    for op in ("ms_stock_all", "ms_assortment_list", "ms_customerorder_list"):
        assert cat.get(op).items_path == "rows", f"{op}: MetaArray rows expected"
    # /current returns a bare array, not a MetaArray
    assert cat.get("ms_stock_current").items_path == ""


# --- generated-map integrity (892 records parsed from the doc) ----------------

def test_all_records_well_formed():
    """Every record must construct cleanly for core: host set, real verb, path
    normalised (prefix present, no leftover uuid, no double slash)."""
    for s in _catalog().all():
        assert s.host, f"{s.operation_id}: empty host (core needs it)"
        assert s.method.upper() in ALL_VERBS, f"{s.operation_id}: bad verb {s.method!r}"
        assert s.path.startswith(API_PREFIX), f"{s.operation_id}: path {s.path!r}"
        assert "//" not in s.path[len("https://"):], f"{s.operation_id}: // in {s.path!r}"
        assert not UUID_RE.search(s.path), f"{s.operation_id}: raw uuid in {s.path!r}"


def test_delete_is_destructive():
    """DELETE wipes data — must be destructive (both confirmations), never just write."""
    for s in _catalog().all():
        if s.method.upper() == "DELETE":
            assert s.safety == "destructive", f"{s.operation_id}: DELETE must be destructive"


def test_post_bulk_delete_is_destructive():
    """MoySklad bulk delete is POST .../delete with an id array — destructive despite POST."""
    for s in _catalog().all():
        if s.method.upper() == "POST" and s.path.rstrip("/").endswith("/delete"):
            assert s.safety == "destructive", f"{s.operation_id}: bulk delete must be destructive"


def test_read_offset_endpoints_have_items_path():
    """An offset-paginated read with no items_path silently returns nothing.
    It must be a real string ('rows', '' for a bare array, or a sub-collection key),
    never the WB default 'result.items' leaking through."""
    for s in _catalog().all():
        if s.safety == "read" and s.pagination == "offset":
            assert isinstance(s.items_path, str), f"{s.operation_id}: items_path not a string"
            assert s.items_path != "result.items", f"{s.operation_id}: WB default leaked"


def test_curated_live_records_preserved():
    """The 4 live-verified records keep their hard-won facts after a re-ingest
    (curated layer must win over the generated map)."""
    cat = _catalog()
    assert "LIVE" in cat.get("ms_stock_all").rate_limit, "curated rate_limit lost"
    for op in ("ms_stock_current", "ms_assortment_list", "ms_customerorder_list"):
        assert cat.get(op).safety == "read"
        assert cat.get(op).keywords, f"{op}: curated keywords lost"
