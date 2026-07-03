# moysklad-mcp-ru: AI access to MoySklad for Claude Code, Cursor, Codex and Cowork

> 🇷🇺 [Русская версия](README.md)
>
> **You run your accounting in MoySklad — give your AI direct access to it.** One
> MCP server over the MoySklad JSON API 1.2: stock, products, orders,
> counterparties, reports (profit, turnover, cash) and **document writes**
> (supplies, shipments, orders, invoices, returns) — straight over the API, no
> browser. Numbers come from the **real API**, not made up by the model. A
> **two-stage write gate** prevents accidentally creating or posting a document in
> your live books. Auto-pagination, multi-cabinet, Russian-language search.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-0.1.0-B5491F)
![Tools](https://img.shields.io/badge/tools-32-2D7D4F)
![Tests](https://img.shields.io/badge/tests-70-2D7D4F)

> ⚠️ **alpha.** A tool, not a replacement for an accountant. The curated core and
> the write slice are battle-verified on a test cabinet; methods imported from the
> docs are a recon map (paths are reliable, confirm write bodies against the docs
> or call them via `ms_call_raw`).

## What's inside

**Not "one tool per endpoint", but 8 generic meta-tools over a catalog** — full
API coverage with a small surface: `ms_search_methods`, `ms_describe_method`,
`ms_call_method`, `ms_call_raw`, `ms_fetch_all`, `ms_map` + cabinet tools.

**Typed read tools:** `ms_get_stock/products/orders/profit/money/turnover/
counterparties/stores/documents` (7 doc types), `ms_ping`. Kopecks are converted
to rubles automatically.

**Write tools (behind two gates):** `ms_build_document` (preview, no write),
`ms_create_document` (any role type as a DRAFT), `ms_post_document` (post —
destructive), `ms_delete_document` (delete — destructive), plus typed
purchaseorder tools. 7 role types: purchaseorder, supply, demand, invoicein,
invoiceout, salesreturn, purchasereturn.

**Catalog:** schema-driven from the official MoySklad docs (892 methods; curated
core verified live, the rest is a recon map). `ms_call_raw` reaches anything not
yet in the catalog.

## Safety model

Each method is classified **read** / **write** / **destructive**. Reads run
immediately; a write (create draft) needs `confirm_write=true` AND
`MOYSKLAD_ALLOW_WRITE=1`; a destructive op (post/delete) also needs
`i_understand_this_modifies_data=true`. Two independent layers: a process-level
guard (writes off by default, optional cabinet pin) that also covers the raw
meta-tools, plus a per-call gate. **0 mutations marked as read** — enforced by a
CI test. Creating always makes a DRAFT; posting is a separate step.

## Install

See **[QUICKSTART.md](QUICKSTART.md)**. Three paths, one result:

1. **Easiest — ask your AI (no terminal).** Tell Claude / Cowork: *"install
   MoySklad MCP"* — the agent walks the bundled `install-skill/`.
2. **Download & click.** Grab the release zip, unzip, double-click
   `install.command` (macOS) / `install.bat` (Windows), paste your token.
3. **Technical.** `python3 install.py --client <claude-desktop|claude-code|codex|opencode>`.

No `pip install`, no JSON editing — deps self-install on first launch. **Token:**
MoySklad → Settings → Users → Access tokens. Stored in
`~/.moysklad-mcp/cabinets.json` (local, chmod 600, never in the repo or chat).

Verify: `python3 serve.py ms --selfcheck` → "OK: ms ready, N tools".

## Money

All API amounts are in kopecks. Read tools return rubles; on writes,
`convert_money_to_kopecks` turns rubles into kopecks. Raw meta-tools work in
kopecks as-is.

## License

MIT. The vendored `core/` is under Ilya Utov's MIT — see [`NOTICE`](NOTICE).
Architecture reuses the strongest ideas from
[marketplaces-mcp-ru](https://github.com/ilyautov/marketplaces-mcp-ru).
This is alpha and open source — install it, verify on your own data, experiment.
