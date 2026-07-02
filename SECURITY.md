# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.31.x  | Yes       |
| < 0.31  | No        |

## Reporting a vulnerability

Do not open a public GitHub issue for security vulnerabilities. Use GitHub's
private vulnerability reporting, or email the maintainer directly. Please
include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

Acknowledgement within 48 hours; fix targeted within 7 days for critical
issues.

## Threat model

dummyindex is a **local development tool**. It does not make network calls
during indexing — `dummyindex ingest` only reads files from the target
directory. The semantic enrichment step runs inside the user's Claude Code
session and uses whichever model that session is configured with; dummyindex
itself never sends source code to a remote service.

### Surface

| Vector | Mitigation |
|--------|-----------|
| Path traversal | `pipeline.io.detect` resolves the project root to an absolute path and uses POSIX-relative file paths everywhere; symlinks are followed only when the caller explicitly opts in via `follow_symlinks=True`. |
| XSS in the graph viewer (`graph.html`) | The viewer (`context/output/viewer.py`) renders client-side from `graph.json`: node/edge labels reach the SVG via D3 `.text()` (textContent — never parsed as HTML), and every detail-panel `innerHTML` interpolation is wrapped in an `escapeHtml()` helper, so no AST-derived string is inserted as raw HTML. (The old server-side `sanitize_label`/pyvis embed was removed in v0.6.) |
| Encoding crashes | All tree-sitter byte slices decoded with `errors="replace"` so non-UTF-8 files degrade gracefully. |
| Symlink traversal | `os.walk(..., followlinks=False)` by default throughout `pipeline.io.detect`. |
| Skill writes outside intended location | `dummyindex install` writes only to `<scope>/.claude/skills/dummyindex/SKILL.md` plus a sibling `.dummyindex_version` file, and (user scope only) appends to `~/.claude/CLAUDE.md`. Paths are computed from `Path.home()` or the explicit `--dir` argument — no string-concat path building. |
| Sensitive files in `.context/` | Indexing skips a built-in list of directories and respects `.dummyindexignore` / `.codeindexignore`. The cache lives at `.context/cache/` and is gitignored automatically by `dummyindex ingest`. |
| Third-party plugin code via `equip` | `dummyindex context equip discover` / `install` rank every candidate by its **blast radius** (which surfaces it declares, and whether any run code — hook / mcp / lsp / bin, as opposed to inert agent / skill / command markdown) and its **trust tier** (trusted vs untrusted source). `install` will not enable an untrusted plugin that runs code without an explicit `--yes`; `equip verify <plugin>@<marketplace>` is a read-only **supply-chain drift check** that re-resolves an installed plugin against its upstream and reports whether the pinned commit sha still matches. |
| GC deleting the wrong artefact | `dummyindex context gc delete` is a dry-run unless `--yes`; it refuses a sentinel / out-of-charset / path-escaping target (exit 2) and refuses an untracked target without `--allow-untracked`. It only ever removes one generated doc workspace under `proposals/` or `audits/` — never source code. |

The PreToolUse doc-guard (`dummyindex context guard-doc-write`) is a **hygiene** aid,
not a security boundary: it redirects internal planning docs to their managed
`.context/` homes. It is **fail-open by design** — it exits 0 on every path except
an explicit JSON deny, and is config-gated (`doc_guard_enabled`, default `true`;
`doc_guard_allow` exempts globs). Do not rely on it to block writes.

## Pre-commit checks

```bash
pytest -q
ruff check .
```
