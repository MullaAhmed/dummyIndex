"""Content hashing for origin-hash baselines (Hermes-derived evolution).

Every generated artifact records the sha256 of its rendered bytes at write time
(:func:`content_hash`). A later lifecycle run re-hashes the file on disk and
compares: equal ⇒ pristine (safe to refresh), different ⇒ user-modified (skip
forever). The ``sha256:`` prefix mirrors the manifest's stored form so a stored
hash and a freshly computed one compare as plain strings.
"""

from __future__ import annotations

import hashlib

_PREFIX = "sha256:"


def content_hash(text: str) -> str:
    """Return ``"sha256:<hexdigest>"`` for ``text`` (UTF-8 encoded)."""
    return _PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()
