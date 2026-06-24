"""Manage the dummyindex section in CLAUDE.md.

Idempotent: re-running replaces the existing block in place, preserves
surrounding content, and raises on unbalanced or duplicate markers.
"""

from __future__ import annotations

from pathlib import Path

BEGIN_MARKER = (
    "<!-- dummyindex:begin (managed — do not hand-edit; "
    "regenerate with `dummyindex context bootstrap`) -->"
)
END_MARKER = "<!-- dummyindex:end -->"


class UnbalancedMarkersError(ValueError):
    """Raised when CLAUDE.md has malformed dummyindex markers."""


_V0_BLOCK_BODY = """\
## dummyIndex context engine

This repo has a generated context index at `.context/`. **Read `.context/HOW_TO_USE.md` before any non-trivial task** — it answers most "where / how / what" questions without grepping. The index does **not** refresh itself; a SessionStart hook only *reports* drift. It's updated explicitly along two paths: `dummyindex context rebuild --changed` refreshes the deterministic backbone (map/tree/symbols) and **preserves the curated feature docs** (never re-clusters); for content updates `dummyindex context reconcile` *reports* the delta (read-only — it writes nothing), then the `/dummyindex` skill's reconcile procedure (`.context/.../council/65-reconcile.md`) folds it in and `dummyindex context reconcile-stamp` advances the anchor. Treat the index as possibly-stale: when it disagrees with the code, the code wins — fix a stale deterministic artefact with `rebuild --changed`, fix a stale feature doc in-session or via the reconcile procedure. Stale *generated* docs (abandoned `proposals/`, done `audits/`) are retired by the context-hygiene GC — run `/dummyindex-gc` to sweep and **delete** (never archive) them, always user-confirmed. **When the user's explicit instruction contradicts a `.context/` spec or plan, the user wins** — note the divergence and proceed."""


def generate_managed_block() -> str:
    """Return the body of the managed block (without begin/end markers)."""
    return _V0_BLOCK_BODY


def bootstrap_claude_md(path: Path, *, block_body: str | None = None) -> str:
    """Write or update the managed block at `path`.

    Idempotent. Preserves surrounding content. Returns the final file content.
    """
    body = (block_body if block_body is not None else generate_managed_block()).rstrip()
    managed = f"{BEGIN_MARKER}\n{body}\n{END_MARKER}"

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        new_content = managed + "\n"
        _atomic_write(path, new_content)
        return new_content

    existing = path.read_text(encoding="utf-8")
    begin_count = existing.count(BEGIN_MARKER)
    end_count = existing.count(END_MARKER)

    if begin_count != end_count:
        raise UnbalancedMarkersError(
            f"{path} has {begin_count} begin marker(s) but {end_count} end "
            "marker(s). Resolve manually before re-running."
        )
    if begin_count > 1:
        raise UnbalancedMarkersError(
            f"{path} has {begin_count} dummyindex managed blocks; expected 0 or 1."
        )

    if begin_count == 0:
        new_content = _append_block(existing, managed)
    else:
        new_content = _replace_block(existing, managed)

    _atomic_write(path, new_content)
    return new_content


def _append_block(existing: str, managed: str) -> str:
    if not existing:
        return managed + "\n"
    if existing.endswith("\n\n"):
        return existing + managed + "\n"
    if existing.endswith("\n"):
        return existing + "\n" + managed + "\n"
    return existing + "\n\n" + managed + "\n"


def _replace_block(existing: str, managed: str) -> str:
    begin_idx = existing.index(BEGIN_MARKER)
    end_idx = existing.index(END_MARKER) + len(END_MARKER)
    return existing[:begin_idx] + managed + existing[end_idx:]


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
