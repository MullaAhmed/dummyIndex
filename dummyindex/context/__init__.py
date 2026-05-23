"""dummyIndex v2 .context/ context engine package.

See BRIEF.md and V0_SCOPE.md at the repo root for design intent.
"""
from __future__ import annotations

from dummyindex.context.meta import (
    SCHEMA_VERSION,
    Meta,
    new_meta,
    read_meta,
    write_meta,
)

__all__ = ["Meta", "SCHEMA_VERSION", "new_meta", "read_meta", "write_meta"]
