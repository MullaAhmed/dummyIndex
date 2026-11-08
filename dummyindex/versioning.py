"""Neutral dotted-integer version comparison shared across layers.

Top-level and importing nothing from `dummyindex.*`, so `context/` can compare
version stamps without importing `installer/` (that direction is forbidden).
`installer/common.py` keeps `_parse_version` / `_compare_stamp` as aliases.
"""

from __future__ import annotations

import re
from enum import Enum

# Release components plus an optional PEP 440 pre-release (`0.38.0b1`), the
# form scripts/release.py cuts from `development`.
_VERSION = re.compile(r"^(?P<release>\d+(?:\.\d+)*)(?:(?P<phase>a|b|rc)(?P<n>\d+))?$")
_PHASE_RANK = {"a": 0, "b": 1, "rc": 2}
_FINAL_RANK = 3


class VersionOrder(str, Enum):
    """Where a stamp sits relative to a package version.

    ``UNKNOWN`` means either side failed to parse; callers treat it as
    unresolvable, never as ``OLDER``. The str mixin keeps existing
    ``== "older"`` / ``in ("newer", "unknown")`` comparisons working.
    """

    OLDER = "older"
    EQUAL = "equal"
    NEWER = "newer"
    UNKNOWN = "unknown"

    # Render as the value ("older"), never the repr ("VersionOrder.OLDER"): installer
    # callers interpolate it into user-facing f-strings, and 3.11+
    # `Enum.__format__` follows `__str__`. Same pin as `context/enums.py:DocConfidence`.
    __str__ = str.__str__


def _sort_key(value: str | None) -> tuple[tuple[int, ...], tuple[int, int]] | None:
    """``(release, (phase rank, n))``; a final release ranks after its rc."""
    if not value:
        return None
    m = _VERSION.match(value.strip())
    if not m:
        return None
    release = tuple(int(part) for part in m.group("release").split("."))
    phase = m.group("phase")
    pre = (_PHASE_RANK[phase], int(m.group("n"))) if phase else (_FINAL_RANK, 0)
    return release, pre


def parse_version(value: str | None) -> tuple[int, ...] | None:
    """Release components of "0.33.0" or "0.38.0b1"; ``None`` otherwise.

    Local, to avoid a runtime dependency on `packaging`. A `v` prefix, `.devN`,
    `"unknown"`, empty or missing parse to `None`; callers treat that as
    unresolvable, never as "older". Order with :func:`compare_versions`, which
    also ranks the pre-release.
    """
    key = _sort_key(value)
    return key[0] if key else None


def compare_versions(stamp: str | None, package_version: str | None) -> VersionOrder:
    """Order one stamp against the package version.

    Returns ``OLDER`` | ``EQUAL`` | ``NEWER``, or ``UNKNOWN`` when either side
    does not parse (see :func:`parse_version`).
    """
    key_stamp = _sort_key(stamp)
    key_package = _sort_key(package_version)
    if key_stamp is None or key_package is None:
        return VersionOrder.UNKNOWN
    if key_stamp < key_package:
        return VersionOrder.OLDER
    if key_stamp > key_package:
        return VersionOrder.NEWER
    return VersionOrder.EQUAL
