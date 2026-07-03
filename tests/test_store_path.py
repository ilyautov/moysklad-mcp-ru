"""Guard the MoySklad cabinet-store path (decision 2026-06-26).

MoySklad keeps its OWN store under ~/.moysklad-mcp (NOT the shared
~/.marketplace-mcp family store). The installer WRITES the token and the server
READS it — if those two paths ever drift apart, the token is saved in one place
and looked for in another, producing a silent 401. These tests pin both to the
same path so a refactor can't reintroduce that drift.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_server_store_under_moysklad_home():
    from moysklad_mcp import server
    assert server.MS_STORE_PATH == Path.home() / ".moysklad-mcp" / "cabinets.json"
    # The running config must actually use that store, not the vendored default.
    assert server.MOYSKLAD_CONFIG.store.path == server.MS_STORE_PATH


def test_install_writes_where_server_reads():
    import install
    from moysklad_mcp import server
    assert install.STORE_PATH == server.MS_STORE_PATH


def test_store_home_follows_env_override(monkeypatch, tmp_path):
    """MOYSKLAD_MCP_HOME relocates the store; install and server move together."""
    monkeypatch.setenv("MOYSKLAD_MCP_HOME", str(tmp_path))
    import importlib
    import install
    from moysklad_mcp import server
    importlib.reload(install)
    importlib.reload(server)
    try:
        assert install.STORE_PATH == tmp_path / "cabinets.json"
        assert server.MS_STORE_PATH == tmp_path / "cabinets.json"
        assert server.MOYSKLAD_CONFIG.store.path == tmp_path / "cabinets.json"
    finally:
        monkeypatch.delenv("MOYSKLAD_MCP_HOME", raising=False)
        importlib.reload(install)
        importlib.reload(server)
