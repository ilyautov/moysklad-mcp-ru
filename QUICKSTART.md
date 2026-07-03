# QUICKSTART — установка moysklad-mcp за несколько минут

Цель: подключить ваш аккаунт МойСклад к ИИ-клиенту (Claude Desktop, Claude Code,
Codex, OpenCode, Cursor, Cowork) без ручного редактирования JSON и без `pip install`.
Зависимости ставит сам `serve.py` при первом запуске.

## 0. Что понадобится

- **Python 3.10+** (`python3 --version`; Windows: `py -3 --version`). Нет — поставьте
  с [python.org](https://python.org) (Windows: отметьте «Add python.exe to PATH»).
- **Токен МойСклад:** Настройки → Пользователи → Токены доступа → создать Bearer-токен.

## 1. Получить код

Папка проекта уже на машине (или подключена в Cowork). Проверьте, что внутри есть
`install.py` и `serve.py`.

## 2. Установить под вашего клиента

Из папки проекта:

| Клиент | Команда |
|---|---|
| **Claude Desktop** (по умолчанию) | `python3 install.py --client claude-desktop` |
| **Claude Code** (CLI) | `python3 install.py --client claude-code` → выполнить напечатанную `claude mcp add …` |
| **Codex** (CLI) | `python3 install.py --client codex` → выполнить напечатанную `codex mcp add …` |
| **OpenCode** | `python3 install.py --client opencode` |
| **Cursor** | подключите `python3 serve.py ms` как MCP-сервер в настройках Cursor |

Без терминала (macOS/Windows): двойной клик `install.command` / `install.bat`.
Только посмотреть блок конфига: `python3 install.py --print`.

`install.py` копирует приложение в стабильную папку `~/.moysklad-mcp/app` и
указывает конфиг туда — можно потом переносить исходную папку, MCP не сломается.
Старый конфиг бэкапится. Повторный запуск безопасен.

## 3. Токен

Интерактивно (спросит токен): `python3 install.py`
Или флагом (не эхайте реальное значение в публичный чат): `python3 install.py --token <TOKEN>`
Несколько аккаунтов: добавьте `--cabinet account2`. Из чата после подключения:
`ms_add_cabinet`, переключение `ms_use_cabinet`, список `ms_list_cabinets`.

## 4. Перезапуск и проверка

Перезапустите клиент (конфиг читается при старте). Первый запуск создаёт venv и
ставит зависимости (несколько секунд).

- Селфчек (токен не нужен): `python3 serve.py ms --selfcheck` → «OK: ms ready, N tools».
- Из чата: `ms_check_auth` (активный кабинет, секрет не эхает) → `ms_ping` (HTTP 200)
  → `ms_get_products` или `ms_get_stock`. Вернулись реальные данные — готово.

## 5. Запись документов (опционально)

По умолчанию запись ВЫКЛючена. Чтобы агент мог создавать/проводить/удалять документы,
выставьте в окружении сервера `MOYSKLAD_ALLOW_WRITE=1` — и **только на тестовом
кабинете**, не на боевом учёте. Создание делает черновик; проведение — отдельный шаг
с подтверждением.

## Troubleshooting

- **`command not found: python3`** → поставьте Python 3.10+; Windows — галочка «Add
  to PATH», новый терминал.
- **«token malformed» / 401, хотя токен верный** → активный кабинет в
  `~/.moysklad-mcp/cabinets.json` пустой/кривой и затеняет env. Пересохраните токен
  (`install.py` или `ms_add_cabinet`) или удалите кривой кабинет (`ms_remove_cabinet`).
- **Тулы не появились** → перезапустите клиент; для Claude Code/Codex проверьте, что
  ВЫПОЛНИЛИ напечатанные `* mcp add` команды; запустите `serve.py ms --selfcheck` и
  прочитайте stderr.
- **Запись «forbidden»** → норма: выставьте `MOYSKLAD_ALLOW_WRITE=1` (тестовый кабинет).
