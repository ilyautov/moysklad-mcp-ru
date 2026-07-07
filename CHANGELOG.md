# Changelog

Все заметные изменения moysklad-mcp-ru. Формат — [Keep a Changelog](https://keepachangelog.com),
версии по [SemVer](https://semver.org).

## [0.1.1] — 2026-07-07

### Added
- Публикация в **MCP Registry**: маркер `mcp-name: io.github.ilyautov/moysklad-mcp-ru`
  в README для ownership-валидации реестра (PyPI-описание).

### Changed
- Версия синхронизирована во всех манифестах (pyproject, server.json, mcpb,
  gemini-extension, plugin, marketplace).

## [0.1.0] — 2026-06-26

Первый публичный срез: read-ядро + запись документов, выверенные на живом тестовом
кабинете, плюс дистрибуция в один клик.

### Added
- **Каталог** МойСклад JSON API 1.2: schema-driven (curated ядро + карта-разведка
  892 метода), поиск по-русски, generic мета-тулы (`search`/`describe`/`call`/
  `call_raw`/`fetch_all`) и тулы кабинетов — на вендорном движке `core`.
- **Типизированные read-тулы:** `ms_get_stock`/`products`/`orders`/`profit`/`money`/
  `turnover`/`counterparties`/`stores`/`documents` (7 типов), `ms_ping`. Копейки→рубли.
- **Запись (Фаза 2):** сборка тел документов, конверсия рубли→копейки, резолвер
  ссылок, **два гейта записи** (`MOYSKLAD_ALLOW_WRITE` + per-call `confirm_write`,
  для destructive — ещё `i_understand_this_modifies_data`).
  - Типизированный create для `purchaseorder` + дженерик `ms_build_document`/
    `ms_create_document` на все 7 ролевых типов; generic `ms_post_document`/
    `ms_delete_document` (проведение/удаление).
  - **Веер выверен боем** на тестовом кабинете: supply/demand/invoicein/
    invoiceout/purchasereturn/salesreturn — create→read-back→проведение→движение
    остатков→удаление→откат.
- **GuardedClient:** процессный write-guard теперь покрывает и сырые мета-тулы
  (`call_method`/`call_raw`), не только типизированные. `core` не патчен.
- **Дистрибуция:** `install.py` (claude-desktop/claude-code/codex/opencode),
  `install.command`/`.bat`/`.sh`, `install-skill/` (zero-terminal), плагин-манифесты
  (`.claude-plugin`/`.codex-plugin`/`.cursor-plugin`), `.mcp.json`.
- **70 офлайн-тестов**, selfcheck (32 тула), без сети и токена.

### Notes
- Построено на вендорном движке `core` из
  [ilyautov/marketplaces-mcp-ru](https://github.com/ilyautov/marketplaces-mcp-ru)
  (MIT) — см. `NOTICE`.
- **alpha.** Курированное ядро выверено живьём; импортированные из доки методы —
  карта для разведки (пути надёжны, тела write сверяйте по доке или `ms_call_raw`).
- Жёсткие факты: `Accept: application/json;charset=utf-8` ровно; лимит бакет 45/3с;
  деньги в копейках.
