# Distribution & release runbook

How `moysklad-mcp-ru` reaches users, and the exact steps to cut a release.
Four channels, one server:

| Channel | Who | Artifact | How it's built |
| --- | --- | --- | --- |
| **`.mcpb` bundle** | Non-technical users on Claude Desktop | `dist/*.mcpb` | `scripts/package_mcpb.py`, attached to the GitHub Release |
| **GitHub zip** | Users who prefer download-and-click installers | `dist/*.zip` | `scripts/package_release.py`, attached to the Release |
| **PyPI / `uvx`** | Developers & agencies | `moysklad-mcp-ru` on PyPI | `publish-pypi.yml` on every `v*` tag (OIDC Trusted Publishing) |
| **MCP Registry** | Discovery inside MCP clients | `server.json` metadata | `mcp-publisher` (manual, one command) |

All four run the single MoySklad server (`moysklad_mcp.server`). `uvx moysklad-mcp-ru`
and the `.mcpb` both launch it via `serve.py ms`; the `ms-mcp` console script is
also available.

---

## One-time setup (do these once, before the first release)

### 1. PyPI Trusted Publishing (pending publisher)

The `publish-pypi.yml` workflow uses OIDC — no token is stored anywhere. PyPI
must be told to trust it. Because the package does not exist yet, register a
**pending publisher**:

1. Log in to <https://pypi.org> → account menu → **Publishing**.
2. **Add a pending publisher** with exactly:
   - PyPI Project Name: `moysklad-mcp-ru`
   - Owner: `ilyautov`
   - Repository name: `moysklad-mcp-ru`
   - Workflow name: `publish-pypi.yml`
   - Environment name: `pypi`
3. Save. On the first `v*` tag the workflow publishes and the pending publisher
   becomes permanent.

The `pypi` GitHub environment is created automatically on the first workflow run
— no need to pre-create it.

### 2. GitHub Pages (landing site)

1. Repo → **Settings → Pages** → Source: **Deploy from a branch** → Branch
   `main`, folder `/docs` → Save.
2. In the DNS panel for `aifrontier.tech`, add a **CNAME** record:
   `moysklad-mcp-ru` → `ilyautov.github.io`.
3. `docs/CNAME` (already committed) pins the custom domain
   `moysklad-mcp-ru.aifrontier.tech`. After DNS propagates, enable **Enforce
   HTTPS** in Settings → Pages.

---

## Cutting a release

1. Bump the version in **all** manifests (keep them identical):
   - `pyproject.toml` → `[project] version`
   - `server.json` → top-level `version` **and** `packages[0].version`
   - `mcpb/manifest.json` → `version`
   - `gemini-extension.json` → `version`
   - `.claude-plugin/plugin.json` → `version`
   - `.claude-plugin/marketplace.json` → `plugins[0].version`
2. Update `CHANGELOG.md`.
3. Commit, then tag and push:
   ```bash
   git commit -am "release: vX.Y.Z"
   git tag vX.Y.Z
   git push && git push --tags
   ```
4. The tag fires two workflows:
   - **`release.yml`** — builds `dist/*.zip` (`package_release.py`) and
     `dist/*.mcpb` (`package_mcpb.py`) and attaches both to the GitHub Release.
   - **`publish-pypi.yml`** — builds sdist+wheel and publishes to PyPI via OIDC.

### MCP Registry (manual, optional per release)

After the PyPI package is live, publish/refresh the registry entry from
`server.json`:
```bash
mcp-publisher publish   # uses server.json in the repo root
```

---

## Local dry-run before tagging

```bash
python3 serve.py ms --selfcheck          # server loads, prints tool count
python3 -m pytest tests/ -q              # offline suite green
pre-commit run --all-files               # guardrails clean
python3 scripts/package_release.py       # dist/*.zip
python3 scripts/package_mcpb.py          # dist/*.mcpb
python3 -m build                         # dist/*.whl + *.tar.gz (PyPI artifacts)
```
