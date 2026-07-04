"""Guards on serve.py's self-bootstrapping launcher contract.

serve.py is the single entry point every MCP client points at. These tests pin
the two facts the bundle/manifests depend on: the service key ("ms" -> the
MoySklad server module) and the exact runtime dependency list installed into the
bootstrap venv. If either drifts, the .mcpb bundle, gemini-extension, and
.mcp.json args silently break.
"""
import importlib.util
from pathlib import Path


def _load_serve():
    spec = importlib.util.spec_from_file_location(
        "serve", Path(__file__).resolve().parent.parent / "serve.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_serve_declares_ms_service():
    serve = _load_serve()
    assert serve.SERVICES == {"ms": "moysklad_mcp.server"}


def test_serve_deps_are_pinned_lower_bounds():
    serve = _load_serve()
    assert serve.DEPS == ["mcp>=1.2.0", "httpx>=0.27", "pyyaml>=6.0"]
