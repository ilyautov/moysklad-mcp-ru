"""MoySklad-required headers. Regression guard for the live-found 400 code 1062.

No network, no token: we only check the header dict build_headers produces.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moysklad_mcp.server import _build_headers  # noqa: E402


def test_accept_is_exact_charset_form():
    # Engine default 'application/json' is rejected by MoySklad with 400/1062.
    h = _build_headers({"token": "X"})
    assert h["Accept"] == "application/json;charset=utf-8"


def test_gzip_always_present():
    # A request without gzip is rejected with 415.
    assert _build_headers({"token": "X"})["Accept-Encoding"] == "gzip"


def test_bearer_when_token():
    assert _build_headers({"token": "abc"})["Authorization"] == "Bearer abc"


def test_basic_when_login_password():
    h = _build_headers({"login": "u", "password": "p"})
    # base64("u:p") == "dTpw"
    assert h["Authorization"] == "Basic dTpw"


def test_no_auth_header_when_no_creds():
    assert "Authorization" not in _build_headers({})
