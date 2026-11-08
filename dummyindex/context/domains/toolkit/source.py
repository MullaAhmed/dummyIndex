"""Parse the ``--source`` argument of ``toolkit install``.

Grammar: ``github:<owner>/<repo>[/<path>][@<git-ref>]``. The scheme must be on
``constants.ALLOWED_SOURCE_SCHEMES``. ``<path>`` is a skill folder, an MCP ``.json``
file, or a plugin name, depending on kind. The git ref is the text after the last
``@`` and is resolved to a commit SHA by :mod:`.install` before anything is shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import ToolkitError
from .paths import validate_source_scheme

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


@dataclass(frozen=True)
class ParsedSource:
    ref: str
    scheme: str
    repo: str
    subpath: str
    git_ref: str | None


def _bad(ref: str, why: str) -> ToolkitError:
    return ToolkitError("invalid_source", f"source {ref!r}: {why}")


def parse_source(ref: str) -> ParsedSource:
    if not isinstance(ref, str) or not ref.strip():
        raise _bad(str(ref), "source is empty")
    scheme = validate_source_scheme(ref)
    body = ref.split(":", 1)[1]
    git_ref: str | None = None
    if "@" in body:
        body, _, git_ref = body.rpartition("@")
        if not _REF_RE.match(git_ref) or ".." in git_ref or git_ref.startswith("/"):
            raise _bad(
                ref, "git ref must be letters, digits, '._/-' and not contain '..'"
            )
    segments = body.split("/")
    if len(segments) < 2:
        raise _bad(ref, "expected github:<owner>/<repo>[/<path>][@<ref>]")
    repo = "/".join(segments[:2])
    if not _REPO_RE.match(repo):
        raise _bad(ref, f"repo {repo!r} is not <owner>/<name>")
    sub = segments[2:]
    for seg in sub:
        if seg in ("", ".", "..") or any(c in seg for c in "\\:@"):
            raise _bad(ref, f"path segment {seg!r} is not allowed")
    return ParsedSource(
        ref=ref,
        scheme=scheme,
        repo=repo,
        subpath="/".join(sub),
        git_ref=git_ref,
    )
