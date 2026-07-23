"""Manage the dummyindex section in CLAUDE.md.

Idempotent: re-running replaces the existing block in place, preserves
surrounding content, and raises on unbalanced or duplicate markers.
"""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

BEGIN_MARKER = (
    "<!-- dummyindex:begin (managed — do not hand-edit; "
    "regenerate with `dummyindex context bootstrap`) -->"
)
END_MARKER = "<!-- dummyindex:end -->"
_UTF8_BOM = "\ufeff"


class UnbalancedMarkersError(ValueError):
    """Raised when CLAUDE.md has malformed dummyindex markers."""


ALWAYS_ON_OUTPUT_POLICY = (
    "Use the combined `caveman`/`i-have-adhd` behavior for every reply without "
    "waiting for an invocation: lead with the outcome or next action, keep prose "
    "compact, number multi-step work, suppress tangents, restate the current "
    "state, and preserve technical and safety detail. Explicit user formatting "
    "requests and safety requirements win."
)


_V0_BLOCK_BODY = f"""\
## dummyIndex context engine

This repo has a generated context index at `.context/`. **Read `.context/HOW_TO_USE.md` before any non-trivial task** — it answers most "where / how / what" questions without grepping. The index does **not** refresh itself; a SessionStart hook only *reports* drift. It's updated explicitly along two paths: `dummyindex context rebuild --changed` refreshes the deterministic backbone (map/tree/symbols) and **preserves the curated feature docs** (never re-clusters); for content updates `dummyindex context reconcile` *reports* the delta (read-only — it writes nothing), then invoke `/dummyindex --recouncil` so the installed skill folds it in, and `dummyindex context reconcile-stamp` advances the anchor. Treat the index as possibly-stale: when it disagrees with the code, the code wins — fix a stale deterministic artefact with `rebuild --changed`, fix a stale feature doc in-session or via the reconcile procedure. Stale *generated* docs (abandoned `proposals/`, done `audits/`) are retired by the context-hygiene GC — run `/dummyindex-gc` to sweep and **delete** (never archive) them, always user-confirmed. **When the user's explicit instruction contradicts a `.context/` spec or plan, the user wins** — note the divergence and proceed.

{ALWAYS_ON_OUTPUT_POLICY}"""


def generate_managed_block() -> str:
    """Return the body of the managed block (without begin/end markers)."""
    return _V0_BLOCK_BODY


def ensure_guidance_target_in_scope(project_root: Path, path: Path) -> None:
    """Reject a project-guidance path that resolves outside ``project_root``.

    Project repositories control both the guidance leaf and its parent
    directories.  Resolve the complete path even when it does not exist yet so
    a symlinked ``.claude`` directory (or ``CLAUDE.md`` leaf) cannot redirect a
    context command into another tree.  Intentional symlinks whose targets stay
    inside the project remain supported.
    """
    try:
        root = project_root.resolve(strict=False)
        target = path.resolve(strict=False)
        target.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(
            f"refusing to write Claude guidance outside project root through {path}"
        ) from exc


def preflight_claude_md(path: Path) -> None:
    """Validate an existing bootstrap target without changing it."""
    # Mirror ``bootstrap_claude_md``: a missing target (including a dangling
    # symlink whose in-scope target is absent) is a valid create operation.
    if not path.exists():
        return
    existing = _read_text_exact(path)
    _managed_block_span(
        existing,
        path=path,
        begin_marker=BEGIN_MARKER,
        end_marker=END_MARKER,
    )


def bootstrap_claude_md(
    path: Path,
    *,
    block_body: str | None = None,
    begin_marker: str = BEGIN_MARKER,
    end_marker: str = END_MARKER,
    place_first: bool = False,
) -> str:
    """Write or update the managed block at `path`.

    Idempotent. Preserves surrounding content. Returns the final file content.
    ``place_first`` moves the managed block ahead of user content; Codex
    guidance uses this so its block stays inside the configured instruction
    byte budget. Claude guidance keeps the historical append/in-place policy.
    """
    body = (block_body if block_body is not None else generate_managed_block()).rstrip()
    managed = f"{begin_marker}\n{body}\n{end_marker}"

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        new_content = managed + "\n"
        _atomic_write(path, new_content)
        return new_content

    existing = _read_text_exact(path)
    span = _managed_block_span(
        existing,
        path=path,
        begin_marker=begin_marker,
        end_marker=end_marker,
    )

    if place_first:
        if span is None:
            remaining = existing
        else:
            remaining = existing[: span.start] + existing[span.remove_end :]
            if span.start == _content_prefix_len(existing):
                remaining = _strip_one_line_break_after_prefix(remaining)
        new_content = _prepend_block(remaining, managed)
    elif span is None:
        new_content = _append_block(existing, managed)
    else:
        new_content = _replace_block(
            existing,
            managed,
            span=span,
        )

    _atomic_write(path, new_content)
    return new_content


def remove_managed_block(
    path: Path,
    *,
    begin_marker: str = BEGIN_MARKER,
    end_marker: str = END_MARKER,
    placed_first: bool = False,
) -> bool:
    """Remove one validated managed block from ``path``.

    Only markers that occupy a complete line are structural.  User prose that
    quotes a marker inline is left byte-for-byte intact.  Malformed, duplicate,
    or reversed standalone markers raise before the file is changed.  When the
    block was a regular file's only non-whitespace content, the file itself is
    removed; a symlink is retained and its target cleared.  Otherwise all
    surrounding user content is preserved.

    Returns ``True`` when a block was removed and ``False`` when the path was
    absent or contained no managed block.
    """
    if not path.exists() and not path.is_symlink():
        return False

    existing = _read_text_exact(path)
    span = _managed_block_span(
        existing,
        path=path,
        begin_marker=begin_marker,
        end_marker=end_marker,
    )
    if span is None:
        return False

    new_content = existing[: span.start] + existing[span.remove_end :]
    if placed_first and span.start == _content_prefix_len(existing):
        new_content = _strip_one_line_break_after_prefix(new_content)
    if not _without_content_prefix(new_content).strip():
        if path.is_symlink():
            # Removing the link would leave its target (and therefore any
            # other link to it) carrying stale managed guidance.  Keep the
            # configured link intact and clear the target instead.
            _atomic_write(path, "")
        else:
            path.unlink()
    else:
        _atomic_write(path, new_content)
    return True


def _append_block(existing: str, managed: str) -> str:
    if not existing:
        return managed + "\n"
    if existing.endswith("\n\n"):
        return existing + managed + "\n"
    if existing.endswith("\n"):
        return existing + "\n" + managed + "\n"
    return existing + "\n\n" + managed + "\n"


def _prepend_block(existing: str, managed: str) -> str:
    """Place ``managed`` first while preserving every byte of user content."""
    prefix, content = _split_content_prefix(existing)
    if not content:
        return prefix + managed + "\n"
    return prefix + managed + "\n\n" + content


def _strip_one_line_break(text: str) -> str:
    """Remove exactly the separator inserted after a place-first block."""
    if text.startswith("\r\n"):
        return text[2:]
    if text.startswith(("\n", "\r")):
        return text[1:]
    return text


def _strip_one_line_break_after_prefix(text: str) -> str:
    prefix, content = _split_content_prefix(text)
    return prefix + _strip_one_line_break(content)


def _split_content_prefix(text: str) -> tuple[str, str]:
    if text.startswith(_UTF8_BOM):
        return _UTF8_BOM, text[len(_UTF8_BOM) :]
    return "", text


def _without_content_prefix(text: str) -> str:
    return _split_content_prefix(text)[1]


def _content_prefix_len(text: str) -> int:
    return len(_split_content_prefix(text)[0])


def _replace_block(
    existing: str,
    managed: str,
    *,
    span: _ManagedBlockSpan,
) -> str:
    return existing[: span.start] + managed + existing[span.content_end :]


class _ManagedBlockSpan:
    """Character offsets for a validated standalone marker pair."""

    __slots__ = ("start", "content_end", "remove_end")

    def __init__(self, start: int, content_end: int, remove_end: int) -> None:
        self.start = start
        self.content_end = content_end
        self.remove_end = remove_end


class _MarkerLine:
    """Character offsets for one standalone marker line."""

    __slots__ = ("start", "content_end", "line_end")

    def __init__(self, start: int, content_end: int, line_end: int) -> None:
        self.start = start
        self.content_end = content_end
        self.line_end = line_end


def _managed_block_span(
    existing: str,
    *,
    path: Path,
    begin_marker: str,
    end_marker: str,
) -> _ManagedBlockSpan | None:
    """Return the one valid BEGIN-to-END span, or reject malformed markers.

    A marker is recognised only when it is the line's complete non-whitespace
    content.  This is intentionally stricter than substring counting: examples
    in prose and quoted diagnostics are user content, not control syntax.
    """
    begins = _standalone_marker_lines(existing, begin_marker)
    ends = _standalone_marker_lines(existing, end_marker)

    if not begins and not ends:
        return None
    if len(begins) > 1 or len(ends) > 1:
        raise UnbalancedMarkersError(
            f"{path} has duplicate dummyindex managed blocks or marker lines; "
            "expected 0 or 1. Resolve manually before re-running."
        )
    if begins and not ends:
        raise UnbalancedMarkersError(
            f"{path} has a begin marker without a matching end marker. "
            "Resolve manually before re-running."
        )
    if ends and not begins:
        raise UnbalancedMarkersError(
            f"{path} has an end marker without a matching begin marker. "
            "Resolve manually before re-running."
        )

    begin = begins[0]
    end = ends[0]
    if end.start < begin.start:
        raise UnbalancedMarkersError(
            f"{path} has an end marker before its begin marker. "
            "Resolve manually before re-running."
        )

    return _ManagedBlockSpan(
        start=begin.start,
        content_end=end.content_end,
        remove_end=end.line_end,
    )


def _managed_block_spans(
    existing: str,
    *,
    path: Path,
    begin_marker: str,
    end_marker: str,
) -> tuple[_ManagedBlockSpan, ...]:
    """Return every sequential, complete managed block in ``existing``.

    Unlike :func:`_managed_block_span`, this helper deliberately permits more
    than one *complete* block so the legacy CLAUDE.md reconciler can repair old
    duplicate installations.  It still rejects reversed, nested, interleaved,
    or dangling standalone markers before any caller writes.
    """
    begins = _standalone_marker_lines(existing, begin_marker)
    ends = _standalone_marker_lines(existing, end_marker)
    events = sorted(
        (
            *((line.start, "begin", line) for line in begins),
            *((line.start, "end", line) for line in ends),
        ),
        key=lambda event: event[0],
    )
    if not events:
        return ()

    spans: list[_ManagedBlockSpan] = []
    open_begin: _MarkerLine | None = None
    for _offset, kind, line in events:
        if kind == "begin":
            if open_begin is not None:
                raise UnbalancedMarkersError(
                    f"{path} has nested or interleaved dummyindex begin markers. "
                    "Resolve manually before re-running."
                )
            open_begin = line
            continue

        if open_begin is None:
            message = (
                "an end marker without a matching begin marker"
                if not begins
                else "an end marker before its begin marker"
            )
            raise UnbalancedMarkersError(
                f"{path} has {message}. Resolve manually before re-running."
            )
        spans.append(
            _ManagedBlockSpan(
                start=open_begin.start,
                content_end=line.content_end,
                remove_end=line.line_end,
            )
        )
        open_begin = None

    if open_begin is not None:
        raise UnbalancedMarkersError(
            f"{path} has a begin marker without a matching end marker. "
            "Resolve manually before re-running."
        )
    return tuple(spans)


def _standalone_marker_lines(text: str, marker: str) -> list[_MarkerLine]:
    """Locate whole-line ``marker`` occurrences with character offsets."""
    found: list[_MarkerLine] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        marker_offset = 0
        candidate = content
        if offset == 0 and candidate.startswith(_UTF8_BOM):
            marker_offset = len(_UTF8_BOM)
            candidate = candidate[marker_offset:]
        if candidate.strip() == marker:
            found.append(
                _MarkerLine(
                    start=offset + marker_offset,
                    content_end=offset + len(content),
                    line_end=offset + len(line),
                )
            )
        offset += len(line)
    return found


def _atomic_write(path: Path, content: str) -> None:
    # Replacing a symlink path would silently turn it into a regular file.
    # Resolve only when the leaf itself is a symlink, then atomically replace
    # its target so the link survives.  Preserve an existing target's mode too;
    # a default-mode temp file otherwise changes executable/read-only policy.
    target = path.resolve(strict=False) if path.is_symlink() else path
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else None
    fd, tmp = _open_atomic_temp(target)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        if mode is not None:
            tmp.chmod(mode)
        tmp.replace(target)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _read_text_exact(path: Path) -> str:
    """Read UTF-8 without universal-newline translation.

    Managed-block edits promise to preserve user bytes outside the block;
    keeping CRLF and mixed line endings intact is part of that contract.
    """
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _open_atomic_temp(target: Path) -> tuple[int, Path]:
    """Create a unique sibling temp with normal new-file mode semantics.

    ``mkstemp`` forces mode ``0600``.  That is appropriate for secrets but
    surprising for host guidance, whose new-file mode should be ``0666``
    filtered through the caller's umask, just like ``Path.write_text``.
    """
    for _attempt in range(100):
        tmp = target.parent / f".{target.name}.{secrets.token_hex(8)}.tmp"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except FileExistsError:
            continue
        return fd, tmp
    raise FileExistsError(f"could not allocate an atomic temp file for {target}")
