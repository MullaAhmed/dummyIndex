# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.5.x   | Yes       |
| < 0.5   | No        |

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
| Path traversal | `pipeline.structure` resolves the project root to an absolute path and uses POSIX-relative file paths everywhere; symlinks are followed only when the caller explicitly opts in via `follow_symlinks=True`. |
| XSS in `graph.html` | `runtime.security.sanitize_label` strips control characters, caps at 256 chars, and HTML-escapes every node label and edge title before pyvis embeds it. |
| Encoding crashes | All tree-sitter byte slices decoded with `errors="replace"` so non-UTF-8 files degrade gracefully. |
| Symlink traversal | `os.walk(..., followlinks=False)` by default throughout `pipeline.detect`. |
| Skill writes outside intended location | `dummyindex install` writes only to `<scope>/.claude/skills/dummyindex/SKILL.md` plus a sibling `.dummyindex_version` file, and (user scope only) appends to `~/.claude/CLAUDE.md`. Paths are computed from `Path.home()` or the explicit `--dir` argument — no string-concat path building. |
| Sensitive files in `.context/` | Indexing skips a built-in list of directories and respects `.dummyindexignore` / `.codeindexignore`. The cache lives at `.context/cache/` and is gitignored automatically by `dummyindex ingest`. |

## Pre-commit checks

```bash
pytest -q
ruff check .
```
