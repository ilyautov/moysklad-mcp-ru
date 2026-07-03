"""Reference resolution (name -> meta) selection logic. No network, no token."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moysklad_mcp.refs import choose, extract_meta  # noqa: E402


def _row(name, href="https://api.moysklad.ru/api/remap/1.2/entity/counterparty/abc",
         type_="counterparty"):
    return {"name": name, "meta": {"href": href, "type": type_,
                                   "mediaType": "application/json",
                                   "uuidHref": "drop-me"}}


def test_extract_meta_minimal():
    meta = extract_meta(_row("Ромашка"))
    assert meta == {"href": "https://api.moysklad.ru/api/remap/1.2/entity/counterparty/abc",
                    "mediaType": "application/json", "type": "counterparty"}
    assert "uuidHref" not in meta  # extra fields dropped


def test_extract_meta_none_without_href():
    assert extract_meta({"name": "x"}) is None
    assert extract_meta({"name": "x", "meta": {}}) is None
    assert extract_meta("nope") is None


def test_choose_exact_beats_partial():
    rows = [_row("Ромашка"), _row("Ромашка-2"), _row("Ромашка и Ко")]
    res = choose(rows, kind="counterparty", name="Ромашка")
    assert res["ok"] is True
    assert res["name"] == "Ромашка"


def test_choose_single_partial_match():
    rows = [_row("ООО Поставщик Один")]
    res = choose(rows, kind="counterparty", name="Поставщик")
    assert res["ok"] is True
    assert res["name"] == "ООО Поставщик Один"


def test_choose_ambiguous_returns_candidates():
    rows = [_row("Поставщик А"), _row("Поставщик Б")]
    res = choose(rows, kind="counterparty", name="Поставщик")
    assert res.get("ok") is not True
    assert res["error_type"] == "invalid_params"
    assert "candidates" in res["details"]
    assert len(res["details"]["candidates"]) == 2


def test_choose_not_found():
    res = choose([], kind="counterparty", name="Нет такого")
    assert res["error_type"] == "not_found"


def test_choose_allow_single_picks_only_one():
    rows = [_row("Рога и Копыта", type_="organization")]
    res = choose(rows, kind="organization", allow_single=True)
    assert res["ok"] is True
    assert res["name"] == "Рога и Копыта"


def test_choose_allow_single_many_requires_name():
    rows = [_row("Орг 1", type_="organization"), _row("Орг 2", type_="organization")]
    res = choose(rows, kind="organization", allow_single=True)
    assert res.get("ok") is not True
    assert res["details"]["candidates"] == ["Орг 1", "Орг 2"]


def test_choose_no_name_no_single_errors():
    res = choose([_row("x")], kind="store")
    assert res["error_type"] == "invalid_params"
