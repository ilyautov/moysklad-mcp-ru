#!/usr/bin/env bash
# Linux/macOS installer (terminal). Wires the MoySklad MCP server into your
# client and saves your token to the local cabinet store.
cd "$(dirname "$0")" || exit 1
exec python3 install.py "$@"
