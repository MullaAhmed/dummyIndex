"""Process-level stream hardening for the CLI.

Windows consoles default stdout/stderr to a legacy code page (cp1252), so a
``print`` of characters outside that page — the ``∪`` in help output, the
``→`` in build-wave output — crashed the CLI with ``UnicodeEncodeError``
(issue: Windows encoding can crash CLI output). Reconfiguring the streams to
UTF-8 with ``errors="replace"`` keeps every command usable there. Hosts that
already speak UTF-8 (every modern terminal, all of Linux/macOS) are
untouched, so this is a no-op for them.
"""

from __future__ import annotations

import sys
from typing import TextIO


def _reconfigure(stream: TextIO) -> None:
    encoding = getattr(stream, "encoding", None)
    if encoding is None or encoding.lower().replace("-", "").replace("_", "") == "utf8":
        return
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:  # StringIO and other non-real streams: leave alone
        return
    reconfigure(encoding="utf-8", errors="replace")


def ensure_utf8_streams() -> None:
    """Reconfigure ``sys.stdout``/``sys.stderr`` to UTF-8 if they are not.

    Idempotent and safe on any host: only streams whose declared encoding is
    not already UTF-8 and that expose ``reconfigure`` (real TextIOWrapper
    streams) are changed.
    """
    _reconfigure(sys.stdout)
    _reconfigure(sys.stderr)
