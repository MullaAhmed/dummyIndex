"""Neutral dotted-integer version comparison shared across layers.

Top-level and importing nothing from `dummyindex.*`, so `context/` can compare
version stamps without importing `installer/` (that direction is forbidden).
`installer/common.py` keeps `_parse_version` / `_compare_stamp` as aliases.
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

    # Render as the value ("older"), never the repr ("VersionOrder.OLDER"): installer
    # callers interpolate it into user-facing f-strings, and 3.11+
    # `Enum.__format__` follows `__str__`. Same pin as `context/enums.py:DocConfidence`.
    __str__ = str.__str__


def parse_version(value: str | None) -> tuple[int, ...] | None:
    """Parse a plain dotted-integer version (e.g. "0.33.0"); ``None`` otherwise.

    Local, to avoid a runtime dependency on `packaging`: every version this project
    has cut is dotted integers. A `v` prefix, a pre-release suffix, `"unknown"`,
    empty or missing all parse to `None`; callers treat that as unresolvable,
    never as "older".
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
