"""GUI-facing toolkit facade: MCP servers, skills and plugins per scope.

Public surface: the ``toolkit_*`` entry points in :mod:`.facade`, the closed
alphabets in :mod:`.constants` (including ``ALLOWED_SOURCE_SCHEMES``), and
:class:`ToolkitError`. The CLI (``dummyindex/cli/toolkit.py``) only parses
arguments and prints the result.

Secrets: ``.context/toolkit/`` (project) and ``<claude>/toolkit/`` (user) hold the
disabled stash and host-file backups. Both can contain full MCP server definitions,
including tokens, so they must never be committed. The managed ``.context/.gitignore``
should list ``toolkit/``; that list is built in ``context/build/upgrade.py``, outside
this domain.
"""

from __future__ import annotations

from .constants import ALLOWED_SOURCE_SCHEMES, KINDS, SCOPES
from .errors import ToolkitError
from .facade import (
    resolve_root,
    toolkit_install,
    toolkit_list,
    toolkit_mutate,
    toolkit_show,
)

__all__ = [
    "ALLOWED_SOURCE_SCHEMES",
    "KINDS",
    "SCOPES",
    "ToolkitError",
    "resolve_root",
    "toolkit_install",
    "toolkit_list",
    "toolkit_mutate",
    "toolkit_show",
]
