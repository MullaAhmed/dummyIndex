"""Canonicalize tool calls to a signature, then group repeats into patterns.

**The bash/shell-only gate, and why it is extended differently here.**
headroom's ``loops.py`` strips pagination fragments (``| head -50``) and
collapses bare integers only for ``tc.name.lower() in ("bash", "shell")``
(``loops.py:97``), because that normalization is regex surgery on an opaque
shell-command *string* — safe only where the tool's whole input is free text
whose pagination syntax is a handful of known shell idioms. Blindly applying
the same regex to e.g. an ``Edit`` call's ``old_string``/``new_string`` would
risk collapsing a bare integer that is part of the *content being edited*,
silently merging two unrelated edits into one "loop".

dummyindex's tools pass **structured JSON inputs**, not opaque strings, so the
generalization here is schema-aware field-dropping instead of string regex:
a structured call's signature drops the named pagination fields
(``offset``, ``limit``, ``head_limit``) — the fields Read/Grep-shaped tools
use to widen a previous, too-narrow fetch — and keeps every other field
**verbatim**: not integer-collapsed, not case-folded, not whitespace-folded.
That handles the extension the spec's callout asks for ("a dummyindex miner
over Read/Grep/Edit calls would need that gate extended") for every tool
uniformly, without the bash-only string-regex risk, because the schema says
which fields are pagination rather than a regex guessing from text.
Bash/shell keeps the string-regex treatment — its command really is opaque
text — written independently below rather than copied.

**Attribution.** The two-level grouping and the measured-waste idea come from
headroom (Apache-2.0); see this package's ``__init__.py`` for the full notice
and an honest account of how close the resemblance runs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .enums import BYTES_PER_TOKEN, DEFAULT_MIN_OCCURRENCES, LoopKind
from .models import RepeatedSignature, ToolCallRecord

_SHELL_TOOL_NAMES = frozenset({"bash", "shell"})

# Structured-input fields that only ever widen/narrow a previous fetch —
# dropped from the signature so a re-run with a bigger window still groups
# with the original. Deliberately narrow: an audit found that including the
# bare names ``n`` and ``count`` silently merged genuinely different calls on
# unknown/MCP tools, where those names are usually semantic (a query's result
# count, a mint quantity) rather than a fetch window. Only the three names
# whose pagination meaning is unambiguous across this tool surface are here.
_PAGINATION_FIELDS = frozenset({"offset", "limit", "head_limit"})

# Shell-only pagination idioms. Same technique as headroom's `_PAGINATION_RE`,
# written independently and structured differently (named alternatives,
# verbose mode) so the resemblance is in the idea, not the text.
_SHELL_PAGINATION_RE = re.compile(
    r"""
      \| \s* (?: head | tail ) \s+ -?n? \s* \d+   # | head -50, | tail -n 50
    | --max-count [= ]? \d+                       # grep --max-count=50
    | \b head \s+ -\d+                            # head -50
    | -n \s* \d+                                  # -n 50
    """,
    re.IGNORECASE | re.VERBOSE,
)
_BARE_INT_RE = re.compile(r"\b\d+\b")
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def canonical_signature(tool_name: str, input_data: Mapping[str, Any]) -> str:
    """A signature stable across re-fetch/retry variants of the same call.

    Two branches, and the asymmetry is deliberate. A shell command is opaque
    free text, so it gets the lossy treatment: pagination idioms stripped,
    bare integers collapsed, whitespace folded, case folded. A structured
    input is not free text, so it gets none of that — only the named
    pagination fields are dropped, and the remaining JSON is serialized with
    sorted keys, which is already deterministic without folding anything.

    An audit caught the earlier version folding case and whitespace across the
    *whole* serialized JSON, which merged calls that genuinely differ: two
    Read calls whose paths differ only in case, an Edit whose ``old_string``
    differs only in spacing, ``git checkout <sha>`` against two shas. It also
    emitted lower-cased paths that do not exist on a case-sensitive
    filesystem. Structured fields are now preserved byte-for-byte.
    """
    lname = tool_name.strip().lower()
    if lname in _SHELL_TOOL_NAMES:
        command = str(input_data.get("command", ""))
        without_paging = _SHELL_PAGINATION_RE.sub(" ", command)
        without_counts = _BARE_INT_RE.sub("N", without_paging)
        folded = _WHITESPACE_RUN_RE.sub(" ", without_counts).strip().lower()
        return f"{lname}::{folded}"

    filtered = {
        key: value for key, value in input_data.items() if key not in _PAGINATION_FIELDS
    }
    # No `default=` fallback: every value reaching here came out of
    # `json.loads`, so it is already JSON-serializable. Coercing with `str`
    # would embed a memory address for anything else and break determinism.
    return f"{lname}::{json.dumps(filtered, sort_keys=True)}"


def _wasted_tokens(records: Sequence[ToolCallRecord], *, is_error_loop: bool) -> int:
    per_call = sorted(
        (r.output_bytes // BYTES_PER_TOKEN for r in records), reverse=True
    )
    # A failing call had no useful output to begin with, so the whole group
    # counts against us — there is no "first one was worth it" to subtract.
    # A re-fetch group is different: one of those calls did real work, and
    # charging only the remainder is the conservative reading.
    return sum(per_call) if is_error_loop else sum(per_call[1:])


def detect_repeated_signatures(
    records_by_session: Sequence[Sequence[ToolCallRecord]],
    *,
    min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
) -> tuple[RepeatedSignature, ...]:
    """Group records by canonical signature, within each session first.

    A signature must reach ``min_occurrences`` *within one transcript* to
    count as a pattern at all (a loop is a within-conversation phenomenon),
    but once it qualifies in any session its occurrences are pooled across
    every other qualifying session for the same signature — mirroring
    headroom's ``detect_loops`` two-level grouping (reimplemented, not
    copied).
    """
    pooled: dict[tuple[str, str], list[ToolCallRecord]] = {}
    for session_records in records_by_session:
        grouped: dict[tuple[str, str], list[ToolCallRecord]] = {}
        for record in session_records:
            grouped.setdefault((record.tool_name.lower(), record.signature), []).append(
                record
            )
        qualifying = (
            (key, calls)
            for key, calls in grouped.items()
            if len(calls) >= min_occurrences
        )
        for key, calls in qualifying:
            pooled.setdefault(key, []).extend(calls)

    results: list[RepeatedSignature] = []
    for (_tool_name, signature), calls in pooled.items():
        count = len(calls)
        failures = sum(1 for call in calls if call.is_error)
        # At-least-half, not strictly-more-than-half: a group split evenly
        # between failures and successes is still worth surfacing as a
        # failure pattern.
        is_error_loop = failures * 2 >= count
        kind = LoopKind.ERROR_REPEAT if is_error_loop else LoopKind.OUTPUT_REPEAT
        wasted = _wasted_tokens(calls, is_error_loop=is_error_loop)
        results.append(
            RepeatedSignature(
                tool_name=calls[0].tool_name,
                signature=signature,
                kind=kind,
                occurrences=count,
                estimated_wasted_tokens=wasted,
            )
        )

    # Deterministic order: highest measured waste first, ties broken by the
    # signature string so two runs over the same input always agree exactly.
    results.sort(key=lambda r: (-r.estimated_wasted_tokens, r.tool_name, r.signature))
    return tuple(results)
