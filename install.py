#!/usr/bin/env python3
"""One-command installer: wires the MoySklad MCP server into Claude / Cowork.

Blessed path: drop the repo into Cowork and say "install MoySklad MCP". The
installer copies the app to a canonical, stable location (~/.moysklad-mcp/app)
and points the client config THERE — so when the mounted/cloned folder later
moves or unmounts, the MCP keeps working. It then asks for the API token (or
takes it as a flag), backs up the old config, and writes a secret-free server
entry. No manual JSON editing, no pip install — serve.py self-bootstraps deps on
first launch.

    python3 install.py                 # interactive (asks for token), copies to canonical dir
    python3 install.py --in-place      # do NOT copy; run from this folder (manual/dev)
    python3 install.py --print         # just print the JSON block, change nothing
    python3 install.py --token T       # non-interactive
    python3 install.py --client codex  # print CLI `mcp add` commands instead

Credentials live in MoySklad's OWN local cabinet store
(~/.moysklad-mcp/cabinets.json, keyed by service) — separate from the
marketplaces-mcp-ru store, so it never collides with Wildberries/Ozon cabinets.

Re-running is safe: it refreshes the app copy and the entry, leaving everything
else alone.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from glob import glob
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Canonical, stable home for OUR app copy — separate from the marketplaces home
# so co-installing alongside Wildberries/Ozon never clobbers their app/.
# Overridable for tests via MOYSKLAD_MCP_HOME.
APP_HOME = Path(os.environ.get("MOYSKLAD_MCP_HOME", Path.home() / ".moysklad-mcp"))
APP_DIR = APP_HOME / "app"
# MoySklad's OWN cabinet store (token), sibling of app/ — NOT the shared
# ~/.marketplace-mcp family store. Keeps install (write) and server (read) on the
# SAME path; the server reads MS_STORE_PATH from the same MOYSKLAD_MCP_HOME.
STORE_PATH = APP_HOME / "cabinets.json"
# Everything serve.py needs at runtime (moysklad_mcp carries its own *.yaml).
RUNTIME_ITEMS = ["core", "moysklad_mcp", "serve.py", "pyproject.toml"]
# SERVE points at the canonical copy once installed; reassigned in main().
SERVE = APP_DIR / "serve.py"
sys.path.insert(0, str(HERE))
from core.credentials import CredentialStore  # noqa: E402

CLAUDE_CONFIG_NAME = "claude_desktop_config.json"
SERVER_NAME = "moysklad"   # entry name in client configs
SERVICE = "ms"             # serve.py service id and cabinet-store key


def _windows_claude_dirs() -> list[Path]:
    """Existing Claude Desktop config folders on this Windows machine (Store +
    classic). The Store package name carries a publisher hash, so match Claude_*."""
    dirs: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        pattern = os.path.join(local, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude")
        dirs += [Path(p) for p in glob(pattern)]
    roaming = os.environ.get("APPDATA")
    if roaming:
        dirs.append(Path(roaming) / "Claude")
    return [d for d in dirs if d.is_dir()]


def _windows_config_paths() -> list[Path]:
    """EVERY Claude Desktop config path to write on Windows (Store + classic),
    so the entry lands wherever Claude actually looks."""
    dirs = _windows_claude_dirs()
    if dirs:
        return [d / CLAUDE_CONFIG_NAME for d in dirs]
    base = Path(os.environ.get("APPDATA", Path.home()))
    return [base / "Claude" / CLAUDE_CONFIG_NAME]


def config_path() -> Path:
    """Primary Claude desktop config path for this OS (for display/breadcrumb)."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / CLAUDE_CONFIG_NAME
    if sys.platform.startswith("win"):
        return _windows_config_paths()[0]
    return home / ".config" / "Claude" / CLAUDE_CONFIG_NAME


def build_entries() -> dict:
    """Claude config server entry. No secrets — the token lives in the cabinet
    store (~/.moysklad-mcp/cabinets.json)."""
    py = sys.executable
    return {SERVER_NAME: {"command": py, "args": [str(SERVE), SERVICE]}}


def build_opencode_entries() -> dict:
    """OpenCode 'mcp' entry: type local + command array, secret-free."""
    py = sys.executable
    return {SERVER_NAME: {"type": "local", "command": [py, str(SERVE), SERVICE], "enabled": True}}


def save_cabinet(cabinet: str, token: str) -> None:
    """Persist the MoySklad token as a named cabinet in MoySklad's own store."""
    if token:
        CredentialStore(path=STORE_PATH).add_cabinet(SERVICE, cabinet, {"token": token}, make_active=True)


def _ask(prompt: str, current: str) -> str:
    if current:
        return current
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def claude_code_commands() -> str:
    py = sys.executable
    return (
        f'claude mcp add {SERVER_NAME} -- "{py}" "{SERVE}" {SERVICE}\n'
        f"# then add the token from chat: ms_add_cabinet, or re-run: python3 install.py"
    )


def codex_commands() -> str:
    py = sys.executable
    return (
        f'codex mcp add {SERVER_NAME} -- "{py}" "{SERVE}" {SERVICE}\n'
        "# then add the token: python3 install.py  (token -> ~/.moysklad-mcp)"
    )


def opencode_config_path() -> Path:
    return Path.home() / ".config" / "opencode" / "opencode.json"


def install_app(src: Path, dest: Path) -> Path:
    """Copy the runtime app from `src` into the canonical `dest`; return the
    canonical serve.py. Skips if already running from `dest`. Never touches .git
    (safe on a Cowork FUSE mount)."""
    if src.resolve() == dest.resolve():
        return dest / "serve.py"
    dest.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", ".git", ".pytest_cache")
    for item in RUNTIME_ITEMS:
        s = src / item
        if not s.exists():
            continue
        d = dest / item
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True, ignore=ignore)
        else:
            shutil.copy2(s, d)
    return dest / "serve.py"


def write_breadcrumb(cfg_path: Path, entries: dict, serve_path: Path, source: Path) -> Path:
    """Visible, secret-free record of the install (Cowork blocks reading the
    client's config dir). Lands at ~/.moysklad-mcp/last_install.json."""
    APP_HOME.mkdir(parents=True, exist_ok=True)
    crumb = APP_HOME / "last_install.json"
    crumb.write_text(json.dumps({
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "servers": sorted(entries.keys()),
        "serve_py": str(serve_path),
        "installed_from": str(source),
        "client_config": str(cfg_path),
        "note": "Verify after restart via MCP tools (ms_check_auth), not by reading the config.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return crumb


def merge_into_config(cfg_path: Path, cfg_key: str, entries: dict) -> None:
    """Merge secret-free server entries into one client config, backing up any
    existing file first."""
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    config: dict = {}
    if cfg_path.exists():
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"⚠️  {cfg_path} is not valid JSON; starting fresh (old file backed up).")
        backup = cfg_path.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(cfg_path, backup)
        print(f"Backed up existing config → {backup.name}")
    config.setdefault(cfg_key, {})
    config[cfg_key].update(entries)
    cfg_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    if sys.version_info < (3, 10):
        sys.exit(f"Python 3.10+ required, found {sys.version.split()[0]}. "
                 "Install from https://python.org and retry.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--cabinet", default="main",
                    help="name for this cabinet (default 'main'); use different names for multiple accounts")
    ap.add_argument("--token", default="", help="MoySklad API token (non-interactive)")
    ap.add_argument("--print", action="store_true", dest="print_only",
                    help="print the config block and exit (change nothing)")
    ap.add_argument("--claude-code", action="store_true",
                    help="print `claude mcp add` commands for Claude Code instead")
    ap.add_argument("--client", choices=["claude-desktop", "claude-code", "codex", "opencode"],
                    default="", help="target client (default: claude-desktop). "
                    "codex/claude-code print CLI commands; opencode writes opencode.json")
    ap.add_argument("--config", default="", help="override config file path")
    ap.add_argument("--in-place", action="store_true",
                    help="do NOT copy to the canonical dir; point the config at this folder "
                         "(manual/dev use — the folder must not move)")
    args = ap.parse_args()

    global SERVE
    if args.print_only or args.in_place:
        SERVE = HERE / "serve.py"
    else:
        SERVE = install_app(HERE, APP_DIR)
        print(f"✅ App installed to {APP_DIR}\n"
              "   (stable location — you can move or delete the source folder now.)\n")

    client = args.client or ("claude-code" if args.claude_code else "claude-desktop")
    if client == "claude-code":
        print(claude_code_commands()); return
    if client == "codex":
        print(codex_commands()); return

    entries = build_entries()
    if args.print_only:
        print(json.dumps({"mcpServers": entries}, ensure_ascii=False, indent=2))
        return

    print("MoySklad MCP installer.\n"
          f"Cabinet name: '{args.cabinet}' (run again with --cabinet NAME to add more accounts).\n"
          "Token is saved to ~/.moysklad-mcp/cabinets.json (local, chmod 600), never to the repo.\n"
          "Get the token: MoySklad → Настройки → Пользователи → Токены доступа.\n")
    token = _ask("MoySklad API token (Enter to skip): ", args.token)

    save_cabinet(args.cabinet, token)

    # multi-account: offer to add more cabinets (interactive only — skipped in CI/piped).
    if sys.stdin and sys.stdin.isatty():
        n = 2
        while _ask("\nAdd another account? (y/N): ", "").lower() in ("y", "yes", "д", "да"):
            cab = _ask("  Account (cabinet) name: ", "") or f"account{n}"
            t2 = _ask("  MoySklad API token (Enter to skip): ", "")
            save_cabinet(cab, t2)
            print(f"  ✅ Cabinet '{cab}' saved.")
            n += 1

    if client == "opencode":
        targets = [opencode_config_path()]; cfg_key = "mcp"; entries = build_opencode_entries()
    elif args.config:
        targets = [Path(args.config)]; cfg_key = "mcpServers"
    elif sys.platform.startswith("win"):
        targets = _windows_config_paths(); cfg_key = "mcpServers"
    else:
        targets = [config_path()]; cfg_key = "mcpServers"
    for cfg_path in targets:
        merge_into_config(cfg_path, cfg_key, entries)

    print(f"\n✅ Config ({client}: server '{SERVER_NAME}', no secrets):")
    for cfg_path in targets:
        print(f"   • {cfg_path}")
    crumb = write_breadcrumb(targets[0], entries, SERVE, HERE)
    print(f"✅ Install record → {crumb} (verify after restart, no secrets)")
    print(f"✅ Cabinet '{args.cabinet}' saved for: {'MoySklad' if token else '(nothing — token skipped)'}")
    print("\n👉 Restart Claude / Cowork. First launch auto-installs dependencies, then the tools appear.")
    print("   Add another account later: re-run with --cabinet account2, or in chat say "
          "'add a MoySklad cabinet' (ms_add_cabinet). Switch with ms_use_cabinet.")


if __name__ == "__main__":
    main()
