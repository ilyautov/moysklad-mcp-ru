#!/usr/bin/env python3
"""Ingest the official MoySklad doc repo -> endpoints.yaml (the API map).

MoySklad has NO machine-readable OpenAPI. The official docs live as templated
Markdown in github.com/moysklad/api-remap-1.2-doc. This parser is the MoySklad
analogue of Ilya's ingest_specs.py (which reads OpenAPI and does not fit us).

Approach — curl-anchored, NOT grep-by-path (paths also appear in response
bodies, href links and filter examples; a naive grep yields garbage like
'entity//store' or truncated ids). For each '### <title>' section we read the
first fenced shell block, take method+URL straight from the `curl -X <M> "<URL>"`
request line, normalise the path (drop host/query, uuid -> {name_id}), and for
GET collections read the first JSON example to derive items_path (exactly one
array -> that path; root array -> ""), porting the single-array-evidence rule
from Ilya's fix_items_path_from_examples.py.

Safety is auto-classified from the verb (GET=read, POST/PUT/PATCH=write,
DELETE=destructive) and a path-suffix override (.../delete via POST is a bulk
delete -> destructive). The curated hot core (endpoints.curated.yaml) wins on
(method, path): live-verified records are never overwritten by the generated map.

Pure offline. Output is a "reconnaissance map": paths and verbs are reliable;
bodies and rare verbs must be confirmed against the doc or called via ms_call_raw.

Usage:
    python3 scripts/ingest_moysklad.py --doc /path/to/api-remap-1.2-doc \
        [--curated moysklad_mcp/endpoints.curated.yaml] \
        [--out moysklad_mcp/endpoints.yaml] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import yaml

HOST = "api.moysklad.ru"
DOC_BASE = "https://github.com/moysklad/api-remap-1.2-doc/blob/master"
API_PREFIX = "/api/remap/1.2"

# Accept full uuids AND doc typos: truncated last group (…188b1) is still an id.
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                     r"[0-9a-fA-F]{4}-[0-9a-fA-F]{6,12}$")
URL_RE = re.compile(r'https?://(?:online|api)\.moysklad\.ru'
                    r'(/api/remap/1\.2/[^\s"\'?`]+)')
METHOD_RE = re.compile(r'-X\s+(GET|POST|PUT|PATCH|DELETE)')
FENCE_RE = re.compile(r'```([a-zA-Z]*)\n(.*?)```', re.S)

# Verbs in the H3 title that mark a real operation (filters out attribute/field
# description headings that merely embed an example curl).
OP_VERB_RE = re.compile(r'^(Получить|Получение|Создать|Создание|Изменить|'
                        r'Изменение|Удалить|Удаление|Массов|Добавить|Запросить|'
                        r'Переместить|Список|Запросы)')

# Title words dropped from search keywords (too generic to disambiguate).
STOP_WORDS = {"получить", "получение", "создать", "создание", "изменить",
              "изменение", "удалить", "удаление", "список", "массовое",
              "массовая", "и", "в", "на", "по", "с", "доп", "отдельное",
              "поле", "запросы", "шаблон"}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def normalise_path(raw_path: str) -> str:
    """Drop trailing slash; replace uuid segments with {<parent>_id} placeholders.

    /api/remap/1.2/entity/customerorder/<uuid>/positions/<uuid>
        -> /api/remap/1.2/entity/customerorder/{customerorder_id}/positions/{positions_id}
    """
    # Drop empty segments first (doc typo 'entity//store' -> 'entity/store').
    segs = [s for s in raw_path.rstrip("/").split("/") if s != ""]
    out: list[str] = []
    used: dict[str, int] = {}
    last_real = "item"          # name placeholders after the nearest LITERAL parent
    for seg in segs:
        if UUID_RE.match(seg):
            name = f"{last_real}_id"
            if name in used:                      # second {x_id} in the same path
                used[name] += 1
                name = f"{last_real}_id{used[name]}"
            else:
                used[name] = 1
            out.append("{" + name + "}")
        else:
            last_real = seg
            out.append(seg)
    return "/" + "/".join(out)


def is_collection(method: str, norm_path: str) -> bool:
    """A GET whose last segment is a literal name (not a {placeholder}) returns a
    list — a collection. A path ending in {id} returns a single object."""
    if method != "GET":
        return False
    last = norm_path.rstrip("/").split("/")[-1]
    return not (last.startswith("{") and last.endswith("}"))


def find_arrays(obj, prefix="", depth=0, out=None):
    """(dotted_path, length) for every list reachable through dicts, depth<=3."""
    if out is None:
        out = []
    if depth > 3 or not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        p = prefix + k
        if isinstance(v, list):
            out.append((p, len(v)))
        elif isinstance(v, dict):
            find_arrays(v, p + ".", depth + 1, out)
    return out


def derive_items_path(blocks: list[tuple[str, str]]) -> str | None:
    """items_path from the first parseable JSON example. Returns:
    "" for a root array, the dotted path for exactly one array, else None
    (ambiguous/none — a wrong items_path is worse than absent)."""
    for lang, content in blocks:
        if lang != "json":
            continue
        try:
            obj = json.loads(content)
        except Exception:
            continue
        if isinstance(obj, list):
            return ""
        arrays = find_arrays(obj)
        if len(arrays) == 1:
            return arrays[0][0]
        return None       # 0 or >1 arrays in the first example -> inconclusive
    return None


def split_sections(text: str) -> list[tuple[str, str]]:
    parts = re.split(r'(?m)^### ', text)
    out = []
    for seg in parts[1:]:
        title, _, body = seg.partition("\n")
        out.append((title.strip(), body))
    return out


def parse_file(path: Path, section: str, rel: str) -> list[dict]:
    records = []
    for title, body in split_sections(path.read_text(encoding="utf-8")):
        blocks = FENCE_RE.findall(body)
        # method + path from the first shell block that contains a curl request
        method = raw_path = None
        for lang, content in blocks:
            if lang in ("shell", "bash", "") and "curl" in content:
                m = METHOD_RE.search(content)
                u = URL_RE.search(content)
                if m and u:
                    method, raw_path = m.group(1), u.group(1)
                    break
        if not (method and raw_path):
            continue
        norm = normalise_path(raw_path)
        coll = is_collection(method, norm)
        ip = derive_items_path(blocks) if coll else None
        records.append({
            "title": title,
            "method": method,
            "path": norm,
            "section": section,
            "is_collection": coll,
            "items_path": ip,
            "has_op_verb": bool(OP_VERB_RE.match(title)),
            "doc": f"{DOC_BASE}/{rel}",
        })
    return records


def classify_safety(method: str, path: str) -> str:
    if method == "GET":
        return "read"
    if method == "DELETE":
        return "destructive"
    if method == "POST" and path.rstrip("/").endswith("/delete"):
        return "destructive"          # bulk delete is POST .../delete
    return "write"                    # POST/PUT/PATCH create/update


def entity_key(path: str) -> str:
    """First segment after /entity/ or /report/ — the business object."""
    tail = path[len(API_PREFIX):].lstrip("/").split("/")
    if tail and tail[0] in ("entity", "report") and len(tail) > 1:
        return tail[1]
    return tail[0] if tail else "other"


def make_operation_id(method: str, path: str) -> str:
    """Predictable, unique-ish id: ms_<verb>_<path letters>, placeholders -> by_x."""
    tail = path[len(API_PREFIX):].lstrip("/").split("/")
    tail = [t for t in tail if t not in ("entity",)]   # drop noise, keep 'report'
    parts = []
    for seg in tail:
        if seg.startswith("{") and seg.endswith("}"):
            parts.append("by_" + seg[1:-1].replace("_id", ""))
        else:
            parts.append(seg)
    verb = {"GET": "get", "POST": "post", "PUT": "put",
            "PATCH": "patch", "DELETE": "delete"}[method]
    return slug("ms_" + verb + "_" + "_".join(parts))


def keywords_from(title: str, ekey: str) -> list[str]:
    words = re.split(r"[^а-яёa-z0-9]+", title.lower())
    kw = [w for w in words if len(w) > 2 and w not in STOP_WORDS]
    if ekey and ekey not in kw:
        kw.append(ekey)
    # dedupe, keep order
    seen, out = set(), []
    for w in kw:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[:8]


def build_generated(doc_dir: Path) -> list[dict]:
    raw: list[dict] = []
    for md in sorted(doc_dir.glob("md/**/*.md")):
        rel = md.relative_to(doc_dir).as_posix()
        section = md.parent.name if md.parent != doc_dir / "md" else "general"
        raw.extend(parse_file(md, section, rel))

    # Dedupe by (method, normalised path). Prefer a record whose title is a real
    # operation verb and which carries a derived items_path.
    best: dict[tuple[str, str], dict] = {}
    for r in raw:
        key = (r["method"], r["path"])
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        score_new = (r["has_op_verb"], r["items_path"] is not None)
        score_cur = (cur["has_op_verb"], cur["items_path"] is not None)
        if score_new > score_cur:
            best[key] = r

    specs, used_ids = [], set()
    for (method, path), r in sorted(best.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        ekey = entity_key(path)
        op_id = make_operation_id(method, path)
        if op_id in used_ids:                 # guarantee uniqueness
            n = 2
            while f"{op_id}_{n}" in used_ids:
                n += 1
            op_id = f"{op_id}_{n}"
        used_ids.add(op_id)
        coll = r["is_collection"]
        # items_path: from example; for an /entity/ collection without a
        # conclusive example fall back to MoySklad's MetaArray invariant "rows".
        if coll:
            ip = r["items_path"]
            if ip is None:
                ip = "rows" if "/entity/" in path else ""
            pagination = "offset"
        else:
            ip, pagination = "", "none"
        specs.append({
            "operation_id": op_id,
            "section": r["section"],
            "method": method,
            "host": HOST,
            "path": path,
            "scope": "",
            "safety": classify_safety(method, path),
            "summary": r["title"],
            "pagination": pagination,
            "items_path": ip,
            "rate_limit": "",
            "doc": r["doc"],
            "keywords": keywords_from(r["title"], ekey),
        })
    return specs


def merge_curated(generated: list[dict], curated_path: Path) -> tuple[list[dict], int]:
    """Curated records win on (method, path). Curated first, then generated
    records whose (method, path) is not already curated."""
    if not curated_path.exists():
        return generated, 0
    cur = yaml.safe_load(curated_path.read_text(encoding="utf-8")) or {}
    curated = cur.get("endpoints", [])
    cur_keys = {(c["method"].upper(), c["path"]) for c in curated}
    merged = list(curated)
    for g in generated:
        if (g["method"], g["path"]) not in cur_keys:
            merged.append(g)
    return merged, len(curated)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True, help="path to api-remap-1.2-doc clone")
    here = Path(__file__).resolve().parent.parent / "moysklad_mcp"
    ap.add_argument("--curated", default=str(here / "endpoints.curated.yaml"))
    ap.add_argument("--out", default=str(here / "endpoints.yaml"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    doc_dir = Path(a.doc)
    if not (doc_dir / "md").is_dir():
        raise SystemExit(f"No md/ under {doc_dir} — is this the doc repo clone?")

    generated = build_generated(doc_dir)
    merged, n_curated = merge_curated(generated, Path(a.curated))

    safety_dist = Counter(s["safety"] for s in merged)
    method_dist = Counter(s["method"] for s in merged)
    section_dist = Counter(s["section"] for s in merged)
    print(f"generated={len(generated)}  curated={n_curated}  merged={len(merged)}")
    print(f"by method : {dict(method_dist)}")
    print(f"by safety : {dict(safety_dist)}")
    print(f"sections  : {dict(sorted(section_dist.items()))}")

    out = {
        "default_host": HOST,
        "_generated_note": ("Reconnaissance map parsed from the official doc repo "
                            "(api-remap-1.2-doc). Paths/verbs reliable; bodies and "
                            "rare verbs confirm via doc or ms_call_raw. Curated "
                            "records (live-verified) override on (method, path)."),
        "endpoints": [{k: v for k, v in s.items() if k != "_generated_note"}
                      for s in merged],
    }
    if a.dry_run:
        print("(dry-run — nothing written)")
        return
    Path(a.out).write_text(
        yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8")
    print(f"WROTE {a.out}  ({len(merged)} endpoints)")


if __name__ == "__main__":
    main()
