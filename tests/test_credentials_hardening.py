"""Hardening for the cabinet credential store — all offline.

Ported from marketplaces-mcp-ru. This repo's core/credentials.py is an earlier
snapshot that predates the corrupt-file backup, atomic temp+replace, 0700-dir
and non-dict-root guards, so those ref cases were DROPPED (they assert behavior
this core does not yet have — and production must not be weakened/changed to
satisfy a sibling's test). The cases below pin behavior this store DOES honor:
the secrets file is written 0600, a direct write leaves no stray temp files, and
sequential writes from two instances preserve both cabinets.
"""
from __future__ import annotations

import json
import os
import stat

import pytest

from core.credentials import CredentialStore


def _store(tmp_path):
    return CredentialStore(path=tmp_path / "sub" / "cabinets.json")


# POSIX file modes don't translate to Windows (chmod is a near-no-op there).
posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX file modes only")


@posix_only
def test_saved_file_is_0600(tmp_path):
    s = _store(tmp_path)
    s.add_cabinet("ozon", "main", {"client_id": "1", "api_key": "k"})
    mode = stat.S_IMODE(os.stat(s.path).st_mode)
    assert mode == 0o600, f"secrets file must be 0600, got {oct(mode)}"


def test_write_leaves_no_leftover_temp(tmp_path):
    s = _store(tmp_path)
    s.add_cabinet("ozon", "main", {"client_id": "1", "api_key": "k"})
    s.add_cabinet("wb", "shop", {"token": "t"})
    leftovers = [p.name for p in s.path.parent.iterdir()
                 if p.name != "cabinets.json"
                 and not p.name.startswith("cabinets.json.lock")]
    assert leftovers == [], f"no temp files should remain: {leftovers}"
    data = json.loads(s.path.read_text(encoding="utf-8"))
    assert data["ozon"]["cabinets"]["main"]["client_id"] == "1"
    assert data["wb"]["cabinets"]["shop"]["token"] == "t"


def test_sequential_writes_from_two_instances_preserve_both(tmp_path):
    p = tmp_path / "cabinets.json"
    a = CredentialStore(path=p)
    b = CredentialStore(path=p)
    a.add_cabinet("ozon", "one", {"client_id": "1", "api_key": "k"})
    b.add_cabinet("ozon", "two", {"client_id": "2", "api_key": "k2"})
    # b must have re-read a's write before saving, not clobbered it.
    names = CredentialStore(path=p).list_cabinets("ozon")["cabinets"]
    assert names == ["one", "two"]
