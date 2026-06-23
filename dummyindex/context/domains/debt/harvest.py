"""Harvest technical-debt markers from a repo's Python source.

``harvest_debt(project_root)`` enumerates **only** Python ``.py`` files (via
``detect()`` filtered under ``files["code"]``), scans each for ``# TODO:`` /
``# FIXME:`` / ``# HACK:`` / ``# DEBT:`` markers on *true comment lines*, parses
the structured ``# DEBT: <ceiling>; upgrade: <trigger>`` form, and returns a
deterministic :class:`DebtLedger`.

Scope (v1): Python only — these markers are Python ``#``-comment syntax. TS and
other languages are explicitly out of scope here (the file enumeration inherits
``detect()``'s ignore/sensitive exclusions by design). The harvester is **pure**:
read-only over source, no writes; the CLI that renders/persists the ledger is a
separate module.

Determinism: rows are sorted by ``(rel_path, line)`` and every path is
repo-relative POSIX (mirroring ``drift._rel_or_none``), so re-running on an
unchanged tree yields a byte-identical ledger that never leaks a home directory.
"""

from __future__ import annotations

from pathlib import Path

from dummyindex.context.drift import _rel_or_none
from dummyindex.pipeline.extract.python_rationale import DEBT_PREFIXES
from dummyindex.pipeline.io.detect import detect

from .models import DebtLedger, DebtRow

# Splits a structured marker's ceiling from its upgrade trigger. We split on the
# FIRST occurrence so a trigger that itself contains the substring is preserved.
_UPGRADE_SEP = "; upgrade:"


def harvest_debt(project_root: Path) -> DebtLedger:
    """Return the debt ledger for ``project_root`` (Python ``.py`` files only)."""
    project_root = project_root.resolve()
    detection = detect(project_root)
    code_paths = (detection.get("files", {}) or {}).get("code", []) or []

    rows: list[DebtRow] = []
    for raw in code_paths:
        if not raw.endswith(".py"):
            continue
        path = Path(raw)
        rel = _rel_or_none(path, project_root)
        if rel is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Unreadable / non-UTF-8 (e.g. a binary blob with a .py suffix):
            # skip without raising — a debt scan must never crash the caller.
            continue
        rows.extend(_rows_for_file(rel, text))

    rows.sort(key=lambda row: (row.rel_path, row.line))
    return DebtLedger(rows=tuple(rows))


def _rows_for_file(rel_path: str, text: str) -> list[DebtRow]:
    """Parse every true-comment debt marker in one file's raw text."""
    found: list[DebtRow] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        prefix = _matching_prefix(stripped)
        if prefix is None:
            continue
        found.append(_parse_marker(rel_path, lineno, stripped, prefix))
    return found


def _matching_prefix(stripped: str) -> str | None:
    """Return the ``DEBT_PREFIXES`` entry this stripped comment line begins with.

    A marker counts only when the stripped line is a *true comment* — i.e. it
    starts with the prefix (which itself begins with ``#``). A ``# TODO:`` token
    living inside a string-continuation line never starts the stripped line, so
    it is correctly ignored.
    """
    for prefix in DEBT_PREFIXES:
        if stripped.startswith(prefix):
            return prefix
    return None


def _parse_marker(rel_path: str, line: int, stripped: str, prefix: str) -> DebtRow:
    """Build a :class:`DebtRow` from one matched comment line (never raises).

    ``prefix`` is the matched ``DEBT_PREFIXES`` entry (e.g. ``# DEBT:``); the
    bare marker token is derived from it. Only ``# DEBT:`` carries the structured
    ``; upgrade:`` trigger clause; the other markers are always ``no_trigger``.
    A malformed/empty marker degrades to ``no_trigger`` with an empty ceiling.
    """
    marker = prefix.strip("# :").upper()
    body = stripped[len(prefix) :].strip()

    if marker == "DEBT" and _UPGRADE_SEP in body:
        ceiling_part, _, trigger_part = body.partition(_UPGRADE_SEP)
        ceiling = ceiling_part.strip()
        trigger = trigger_part.strip()
        if trigger:
            return DebtRow(
                rel_path=rel_path,
                line=line,
                marker=marker,
                ceiling=ceiling,
                trigger=trigger,
                no_trigger=False,
            )
        # "; upgrade:" present but empty -> degrade to no-trigger.
        return _no_trigger_row(rel_path, line, marker, ceiling)

    # Plain marker, or a # DEBT: with no upgrade clause -> no trigger.
    return _no_trigger_row(rel_path, line, marker, body)


def _no_trigger_row(rel_path: str, line: int, marker: str, ceiling: str) -> DebtRow:
    return DebtRow(
        rel_path=rel_path,
        line=line,
        marker=marker,
        ceiling=ceiling,
        trigger=None,
        no_trigger=True,
    )
