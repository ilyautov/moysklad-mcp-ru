# Contributing

Спасибо за интерес. Это alpha и открытый код (MIT) — баги, методы каталога и
сценарии приветствуются.

## Dev setup

```bash
python3 serve.py ms --selfcheck      # сборка без сети и токена → "OK: ms ready, N tools"
python3 -m pytest tests/ -q          # 70 офлайн-тестов (без сети и токена)
pip install -e ".[dev]"              # опционально: pytest, pre-commit, pip-audit, detect-secrets
```

Требуется Python 3.10+. Зависимости рантайма (`mcp`, `httpx`, `pyyaml`) лаунчер
ставит сам в локальный `.venv`.

## Правила

- **`core/` не трогаем.** Это вендорный движок из
  [ilyautov/marketplaces-mcp-ru](https://github.com/ilyautov/marketplaces-mcp-ru)
  (MIT, см. `NOTICE`). Вся специфика МойСклад — в `moysklad_mcp/`, адаптируем в
  своём слое (как `_build_headers`, `GuardedClient`). Улучшения движка — апстримом
  Илье, не форком core.
- **Safety прежде всего.** Любой мутирующий метод в каталоге помечается `write` или
  `destructive`, никогда `read`. Это проверяет `tests/test_safety_catalog.py` в CI —
  сборка падает, если PUT/PATCH/DELETE/POST помечен `read`.
- **Деньги в копейках.** Не добавляйте денежные ключи в обход `money.py`
  (`WRITE_MONEY_KEYS`), иначе суммы уедут ×100.
- **Тесты без сети.** Юнит-тесты не должны ходить в сеть и не требуют токена.
  Живую выверку методов делайте локально на своём кабинете и отражайте в
  `endpoints.curated.yaml` (курированный слой побеждает сгенерированный).
- **Каталог растёт аддитивно.** Пересборка: `python3 scripts/ingest_moysklad.py
  --doc <клон api-remap-1.2-doc>`. Курированные `safety`/описания не перетираются.

## Pull requests

Маленькие, сфокусированные PR. В описании — что выверено боем, а что по доке
(уровень доверия). Перед PR: `pytest tests/ -q` зелёный + `serve.py ms --selfcheck`.

## Релиз

`python3 scripts/package_release.py` → `dist/moysklad-mcp-ru-v<версия>.zip`
(allowlist + denylist секретов). Версия — в `pyproject.toml`, история — в `CHANGELOG.md`.
