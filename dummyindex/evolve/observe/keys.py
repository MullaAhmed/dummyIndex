from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

KEY_REL = ".dummyindex/evidence.key"
KEY_BYTES = 32
DISABLE_ENV = "DUMMYINDEX_EVOLUTION"
DISABLE_VALUES = frozenset({"0", "off", "false"})
RETENTION_DEFAULT = 30


def canonical(value: object) -> bytes:
    """Canonical JSON bytes for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def evidence_key(home: Path | None = None) -> bytes:
    """Return the local HMAC key, creating it once with 0600 mode."""
    path = (home or Path.home()) / KEY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError:
        key = path.read_bytes()
    else:
        key = secrets.token_bytes(KEY_BYTES)
        with os.fdopen(fd, "wb") as handle:
            handle.write(key)
        if os.name != "nt":
            os.chmod(path, 0o600)
    if len(key) != KEY_BYTES:
        raise ValueError("unusable evidence key")
    return key


def keyed_id(*parts: object, key: bytes | None = None) -> str:
    """Hex HMAC-SHA256 over the canonical JSON of parts."""
    secret = key if key is not None else evidence_key()
    return hmac.new(secret, canonical(list(parts)), hashlib.sha256).hexdigest()


def session_key(session_id: str, key: bytes | None = None) -> str:
    """Keyed identifier for a raw session ID."""
    return keyed_id("session", session_id, key=key)


def evolution_enabled(home: Path | None = None) -> bool:
    """False when the kill switch is set or the evidence key is unusable."""
    if os.environ.get(DISABLE_ENV, "").strip().lower() in DISABLE_VALUES:
        return False
    try:
        evidence_key(home)
    except (OSError, ValueError):
        return False
    return True


def retention_days(home: Path | None = None) -> int:
    """Retention window in days from cleanupPeriodDays, capped at 30."""
    try:
        path = (home or Path.home()) / ".claude" / "settings.json"
        value = json.loads(path.read_text(encoding="utf-8")).get("cleanupPeriodDays")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return min(RETENTION_DEFAULT, value)
    except Exception:
        return RETENTION_DEFAULT
    return RETENTION_DEFAULT
