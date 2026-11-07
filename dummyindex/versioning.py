"""Neutral dotted-integer version comparison shared across layers.

Moved verbatim from `installer/common.py` (`_parse_version` / `_compare_stamp`,
which stay there as aliases so the installer callers are untouched). It lives
top-level and imports nothing from `dummyindex.*`, so `context/` can compare
version stamps without importing `installer/` — that direction is forbidden.
"""

from __future__ import annotations

from enum import Enum


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

    # Render as the value ("older"), never the enum repr ("VersionOrder.OLDER"):
    # installer callers interpolate the result into user-facing f-strings
    # (`installer/repair.py:_decide_rewrite`, `installer/install/link_dispatch.py`
    # link gate), and 3.11+ `Enum.__format__` follows `__str__`. Same pin as
    # `dummyindex/context/enums.py:DocConfidence`.
    __str__ = str.__str__


def parse_version(value: str | None) -> tuple[int, ...] | None:
    """Parse a plain dotted-integer version (e.g. "0.33.0"); ``None`` otherwise.

    dummyindex has no runtime dependency on `packaging`, and every version
    this project has ever cut is dotted integers, so a tiny local parser —
    not a new dependency — is the right-sized fix. A stray `v` prefix, a
    pre-release suffix, `"unknown"`, empty, or missing all parse to `None`;
    callers treat that as unresolvable, never as "older".
    """
    if not value:
        return None
    try:
        return tuple(int(part) for part in value.strip().split("."))
    except ValueError:
        return None


def compare_versions(stamp: str | None, package_version: str | None) -> VersionOrder:
    """Order one stamp against the package version.

    Returns ``OLDER`` | ``EQUAL`` | ``NEWER``, or ``UNKNOWN`` when either side
    does not parse (see :func:`parse_version`).
    """
    parsed_stamp = parse_version(stamp)
    parsed_package = parse_version(package_version)
    if parsed_stamp is None or parsed_package is None:
        return VersionOrder.UNKNOWN
    if parsed_stamp < parsed_package:
        return VersionOrder.OLDER
    if parsed_stamp > parsed_package:
        return VersionOrder.NEWER
    return VersionOrder.EQUAL
