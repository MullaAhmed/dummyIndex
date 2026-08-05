"""Deterministic failure-miner: repeated tool-error/loop signatures, fed
into `.context/session-memory/`.

**Attribution.** The scan/canonicalize/group technique this package
implements is ported from `headroomlabs-ai/headroom`
(https://github.com/headroomlabs-ai/headroom, Apache License 2.0),
specifically ``headroom/learn/scanner.py``, ``loops.py``, ``writer.py``,
``base.py``, and ``_shared.py``. Per this proposal's plan
(``.context/proposals/repo-adoptions-ponytail-headroom/plan.md``, Attribution
section: "prefer reimplementation from the described technique over copied
code"), these modules were written against the described technique rather
than by copying files, and they diverge where dummyindex's inputs differ —
structured JSON tool calls get schema-aware field-dropping where headroom
applies string regexes to opaque shell commands.

**That is not the same as "nothing was copied", and an earlier version of
this docstring claimed it was.** An audit measuring maximal contiguous token
runs against ``headroom/learn/`` found short verbatim spans surviving in the
shell-normalization branch of ``signatures.py`` and the store-walk loop in
``scan.py``, plus several shared private identifiers. Those spans have since
been rewritten, but the resemblance is structural and close, and the honest
description is "derived from", not "independent of". dummyindex therefore
carries a top-level ``NOTICE`` reproducing headroom's attribution line, which
is what Apache-2.0 asks for and what this proposal's plan named as the
trigger. Arguing the requirement away on a §4 technicality — as the earlier
docstring did — was the wrong call twice over: the premise was false, and the
notice costs nothing.

`headroom/learn/analyzer.py` is explicitly OUT of scope — it is an LLM
digest-and-parse wrapper with no deterministic analysis path of its own (see
the proposal's spec, "Explicit SKIPs"). Nothing here calls a model, makes a
network request, or depends on subprocess-execing a CLI.
"""

from __future__ import annotations

from .enums import DEFAULT_MIN_OCCURRENCES, LoopKind
from .models import MinerReport, RepeatedSignature, ToolCallRecord
from .pipeline import mine_and_feed, scan_transcript_store
from .render import render_report, write_report
from .resolve import resolve_claude_config_dir, resolve_transcript_store
from .scan import discover_project_dirs, iter_transcript_files, parse_transcript
from .scope import project_dir_name, sanitize_signature
from .signatures import canonical_signature, detect_repeated_signatures

__all__ = [
    "DEFAULT_MIN_OCCURRENCES",
    "LoopKind",
    "MinerReport",
    "RepeatedSignature",
    "ToolCallRecord",
    "canonical_signature",
    "detect_repeated_signatures",
    "discover_project_dirs",
    "iter_transcript_files",
    "mine_and_feed",
    "parse_transcript",
    "project_dir_name",
    "render_report",
    "resolve_claude_config_dir",
    "resolve_transcript_store",
    "sanitize_signature",
    "scan_transcript_store",
    "write_report",
]
