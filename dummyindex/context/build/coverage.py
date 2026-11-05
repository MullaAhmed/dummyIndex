"""Explicit file/symbol coverage, including currently unowned source."""

from __future__ import annotations

import json
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic

from .maps import FilesMap, SymbolsMap


def write_coverage(
    context_dir: Path,
    files_map: FilesMap,
    symbols_map: SymbolsMap,
    *,
    detection: dict | None = None,
    extraction: dict | None = None,
) -> None:
    from .reconcile import _file_owners

    owners = _file_owners(context_dir)
    counts: dict[str, int] = {}
    for symbol in symbols_map.symbols:
        counts[symbol.path] = counts.get(symbol.path, 0) + 1
    files = []
    statuses = (extraction or {}).get("file_status", {})
    for entry in files_map.files:
        symbols = counts.get(entry.path, 0)
        status = statuses.get(str(context_dir.parent / entry.path), {})
        state = status.get("state")
        files.append(
            dict(
                path=entry.path,
                language=entry.language,
                symbols=symbols,
                owners=list(owners.get(entry.path, ())),
                state=state
                if state in {"pending", "unsupported"}
                else ("indexed" if symbols else "file-only"),
                reason=status.get("reason")
                or (
                    ""
                    if symbols
                    else "No AST symbols extracted; file navigation is available."
                ),
            )
        )
    payload = dict(
        schema_version=1,
        files=files,
        source_count=len(files),
        symbol_count=len(symbols_map.symbols),
        unassigned=[f["path"] for f in files if not f["owners"]],
        excluded=(detection or {}).get("excluded", []),
        pending=[f["path"] for f in files if f["state"] == "pending"],
    )
    write_text_atomic(
        context_dir / "coverage.json", json.dumps(payload, indent=2) + "\n"
    )
