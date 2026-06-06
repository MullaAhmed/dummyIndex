# Contributing to dummyindex

dummyindex is a Python CLI tool and Claude Code skill. Contributions are welcome — read this file before opening a PR.

---

## Repo layout

| Path | What lives here |
|------|-----------------|
| `dummyindex/cli/` | `dummyindex context <subcommand>` dispatch — arg parsing + call domain + print + exit |
| `dummyindex/context/` | `.context/` domain logic: builder, domains, output renderers, hooks |
| `dummyindex/pipeline/` | Deterministic backbone: tree-sitter extraction, graph build, export |
| `dummyindex/analysis/` | Graph analytics (Leiden community detection) |
| `dummyindex/export/` | Render graph → on-disk JSON |
| `dummyindex/usage/` | `dummyindex usage` — Claude Code transcript token reporting |
| `dummyindex/skills/` | Bundled markdown for `/dummyindex` and sibling slash commands |
| `tests/` | Mirrors `dummyindex/` layout; pytest markers: `unit`, `integration` |
| `docs/guide/` | Public conceptual docs (01–12, read in order) |
| `docs/reference/` | Canonical conventions reference |
| `docs/internal/` | Build-phase artifacts (specs, plans, audits) — frozen, not user docs |

The canonical conventions doc is **[docs/reference/01-conventions.md](docs/reference/01-conventions.md)** — it covers folder organisation, layering rules, naming, data-class rules, CLI shape, error handling, and where a new module goes. Read it before adding code.

---

## Dev setup

```bash
pip install -e ".[dev]"       # or: uv pip install -e ".[dev]"
uv run pytest -q              # all tests
uv run pytest -q tests/context/test_source_docs.py   # doc-discovery tests
uv run ruff check dummyindex tests    # linting
uv run ruff format --check dummyindex tests           # formatting
```

Releases publish to PyPI on GitHub Release via OIDC trusted publishing (`.github/workflows/publish.yml`). The smoke test in `.github/workflows/tests.yml` installs in project scope, ingests the repo itself, and verifies expected files exist.

---

## Commit messages

Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `ci:`.

---

## Where does a new module go?

See the **"Where does a new module go?"** table in [docs/reference/01-conventions.md](docs/reference/01-conventions.md#3-where-does-a-new-module-go) — it maps every kind of code to its home directory. When in doubt: domain logic → `context/<domain>/`, CLI wire-up → `context/cli/<subcommand>.py`, cross-cutting stdlib-only helpers → `runtime/<file>.py`.
