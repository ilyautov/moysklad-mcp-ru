"""moysklad_mcp — MCP server for the MoySklad JSON API 1.2 (PoC thin slice).

Built on the service-agnostic `core` engine vendored from
ilyautov/marketplaces-mcp-ru (MIT). MoySklad specifics (Bearer/Basic auth,
kopecks, single host, curated read catalog) live in this package.
"""

from importlib.metadata import PackageNotFoundError, version as _dist_version

try:
    # Версия живёт в pyproject.toml и приезжает из метаданных дистрибутива.
    # Вторая копия числа в коде неизбежно отстаёт, и все шесть пакетов отстали.
    __version__ = _dist_version("moysklad-mcp-ru")
except PackageNotFoundError:  # запуск из исходников без установки
    __version__ = "0+unknown"
