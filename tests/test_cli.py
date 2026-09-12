"""Контракт консольной команды `moysklad-mcp-ru`.

Точкой входа пакета раньше был `main`, который просто запускает stdio-сервер и
любой аргумент проглатывает молча: `moysklad-mcp-ru --help` завершался с кодом
0 и пустым выводом. Человек, поставивший сервер через `uvx moysklad-mcp-ru`
(этот путь рекламируют и реестр, и каталоги), не мог отличить рабочую установку
от сломанной, потому что `--selfcheck` живёт в `serve.py`, а он пакетом не
ставится. Тесты держат три факта: точка входа это `cli`, `doctor` печатает
диагностику и не ходит в сеть, мусорный аргумент падает с кодом 2.
"""
import sys
import tomllib
from pathlib import Path

import pytest

from moysklad_mcp import server

ROOT = Path(__file__).resolve().parent.parent


def _scripts() -> dict[str, str]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"]["scripts"]


def test_console_scripts_point_at_cli_not_main():
    # main() уходит в mcp.run() сразу, без разбора argv: если сюда вернётся
    # ":main", команда снова начнёт молча глотать --help.
    assert set(_scripts().values()) == {"moysklad_mcp.server:cli"}


def test_doctor_prints_tool_and_method_counts(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["moysklad-mcp-ru", "doctor"])
    with pytest.raises(SystemExit) as exc:
        server.cli()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert str(len(server.catalog.all())) in out
    assert "OK:" in out


def test_help_exits_clean_and_says_something(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["moysklad-mcp-ru", "--help"])
    server.cli()
    assert "doctor" in capsys.readouterr().out


def test_unknown_argument_is_an_error_not_a_silent_server_start(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["moysklad-mcp-ru", "--wat"])
    with pytest.raises(SystemExit) as exc:
        server.cli()
    assert exc.value.code == 2
    assert "--wat" in capsys.readouterr().err
