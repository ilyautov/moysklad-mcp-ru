#!/bin/bash
# macOS double-click installer. Finder runs .command files in Terminal.
# Wires the MoySklad MCP server into Claude Desktop and saves your token locally.
cd "$(dirname "$0")" || exit 1
echo "MoySklad MCP — установка…"
python3 install.py
echo
echo "Готово. Можно закрыть окно (Enter)."
read -r _
