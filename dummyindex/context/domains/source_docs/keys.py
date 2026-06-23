"""Harvest JSON keys for reference cross-checking.

`harvest_json_keys` walks JSON schemas + sample payloads and returns the
set of property/key names, so `find_broken_refs` can recognise refs that
match a schema rather than a Python symbol.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path


def harvest_json_keys(
    json_paths: Iterable[Path], *, limit: int = 5000
) -> frozenset[str]:
    """Pull every distinct JSON object key from ``json_paths``.

    Prose docs frequently cite schema field names (``feature_id``,
    ``broken_refs``, ``confidence``) that aren't Python/JS symbols but
    *are* real names. Without harvesting them, every doc that documents
    a JSON schema looks "stale" because all its backticked field-names
    fail the AST check.

    Capped at ``limit`` keys to keep startup latency bounded on repos
    with very large JSON corpora.
    """
    out: set[str] = set()

    def _walk(node: object) -> None:
        if len(out) >= limit:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and k:
                    out.add(k)
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    for p in json_paths:
        if len(out) >= limit:
            break
        try:
            payload = json.loads(Path(p).read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            continue
        _walk(payload)
    return frozenset(out)
