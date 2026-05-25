"""Read a previously written catalog from disk."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from .models import DocCatalog


def read_catalog(context_dir: Path) -> Optional[DocCatalog]:
    path = context_dir / "source-docs" / "INDEX.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return DocCatalog.from_dict(payload)
