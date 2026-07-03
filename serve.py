#!/usr/bin/env python3
"""Self-bootstrapping launcher for the MoySklad MCP server.

Point any MCP client at THIS file. On first run it quietly creates a local
virtual environment, installs deps, injects them into the current process, then
runs the server. Subsequent runs start instantly.

    python3 serve.py ms                # launch the MoySklad server
    python3 serve.py ms --selfcheck    # verify install, print tool count, exit

Bootstrap pattern vendored from ilyautov/marketplaces-mcp-ru (MIT). All
bootstrap chatter goes to STDERR; STDOUT stays clean for the stdio transport.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = Path(os.environ.get("MOYSKLAD_MCP_VENV", HERE / ".venv"))
DEPS = ["mcp>=1.2.0", "httpx>=0.27", "pyyaml>=6.0"]
SERVICES = {"ms": "moysklad_mcp.server"}


def _log(msg: str) -> None:
    print(f"[moysklad-mcp] {msg}", file=sys.stderr, flush=True)


def _venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _venv_site_packages() -> list[Path]:
    if os.name == "nt":
        return [VENV / "Lib" / "site-packages"]
    return list(VENV.glob("lib/python*/site-packages"))


def _deps_importable() -> bool:
    try:
        import httpx  # noqa: F401
        import mcp  # noqa: F401
        import yaml  # noqa: F401
        return True
    except ImportError:
        return False


def _ensure_deps() -> bool:
    if _deps_importable():
        return True
    vpy = _venv_python()
    if not vpy.exists():
        _log(f"first run — creating virtual environment at {VENV} …")
        import venv
        venv.EnvBuilder(with_pip=True).create(VENV)
    _log("installing dependencies (one-time) …")
    try:
        subprocess.run(
            [str(vpy), "-m", "pip", "install", "--quiet", "--upgrade", "pip", *DEPS],
            check=True, stdout=sys.stderr.fileno(), stderr=sys.stderr.fileno(),
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        _log(f"dependency install failed: {exc}")
        return False
    for sp in _venv_site_packages():
        if sp.is_dir():
            sys.path.insert(0, str(sp))
    return _deps_importable()


def main() -> None:
    if sys.version_info < (3, 10):
        _log(f"Python 3.10+ required, found {sys.version.split()[0]}.")
        sys.exit(1)
    args = list(sys.argv[1:])
    selfcheck = "--selfcheck" in args
    positional = [a for a in args if not a.startswith("-")]
    if not positional or positional[0] not in SERVICES:
        _log(f"usage: python serve.py [{'|'.join(SERVICES)}] [--selfcheck]")
        sys.exit(2)
    service = positional[0]

    sys.path.insert(0, str(HERE))  # make core/ and moysklad_mcp/ importable

    if not _ensure_deps():
        _log(f"dependencies unavailable. Install manually: pip install {' '.join(DEPS)}")
        sys.exit(1)

    import importlib
    server = importlib.import_module(SERVICES[service])

    if selfcheck:
        import asyncio
        tools = asyncio.run(server.mcp.list_tools())
        _log(f"selfcheck OK — {service} server exposes {len(tools)} tools.")
        print(f"OK: {service} ready, {len(tools)} tools.")
        return

    server.main()


if __name__ == "__main__":
    main()
