"""Tests for the neutral version comparator in `dummyindex/versioning.py`."""

from __future__ import annotations

import pytest

from dummyindex.installer.common import _compare_stamp, _parse_version
from dummyindex.versioning import VersionOrder, compare_versions, parse_version

pytestmark = pytest.mark.unit

_PARITY_VALUES = [None, "", "v0.37.0", "0.38.0.dev1", "unknown", "0.37.0"]


@pytest.mark.parametrize("value", _PARITY_VALUES)
def test_parse_version_alias_parity(value: str | None) -> None:
    assert _parse_version(value) == parse_version(value)


@pytest.mark.parametrize("value", _PARITY_VALUES)
def test_compare_stamp_alias_parity(value: str | None) -> None:
    assert _compare_stamp(value, "0.37.0") is compare_versions(value, "0.37.0")
    assert _compare_stamp("0.37.0", value) is compare_versions("0.37.0", value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("v0.37.0", None),
        ("0.38.0.dev1", None),
        ("unknown", None),
        ("0.37.0", (0, 37, 0)),
        ("0.37.0.1", (0, 37, 0, 1)),
    ],
)
def test_parse_version(value: str | None, expected: tuple[int, ...] | None) -> None:
    assert parse_version(value) == expected


def test_older_compares_equal_to_plain_string_and_is_member() -> None:
    result = compare_versions("0.36.0", "0.37.0")
    assert result == "older"
    assert result is VersionOrder.OLDER


def test_equal_and_newer() -> None:
    assert compare_versions("0.37.0", "0.37.0") is VersionOrder.EQUAL
    assert compare_versions("0.37.0", "0.37.0") == "equal"
    assert compare_versions("0.38.0", "0.37.0") is VersionOrder.NEWER
    assert compare_versions("0.38.0", "0.37.0") == "newer"


def test_extra_component_orders_by_tuple_length() -> None:
    assert compare_versions("0.37.0", "0.37.0.1") is VersionOrder.OLDER
    assert compare_versions("0.37.0.1", "0.37.0") is VersionOrder.NEWER


@pytest.mark.parametrize(
    ("stamp", "package_version"),
    [
        (None, "0.37.0"),
        ("0.37.0", None),
        ("v0.37.0", "0.37.0"),
        ("0.38.0.dev1", "0.37.0"),
        ("unknown", "0.37.0"),
        ("", "0.37.0"),
    ],
)
def test_unparseable_side_is_unknown_never_older(
    stamp: str | None, package_version: str | None
) -> None:
    result = compare_versions(stamp, package_version)
    assert result is VersionOrder.UNKNOWN
    assert result != "older"
    # The installer callers' exact membership test (ownership.py, orchestrate.py).
    assert result in ("newer", "unknown")


def test_renders_as_value_in_str_and_fstrings() -> None:
    # repair.py and link_dispatch.py interpolate the result into user messages.
    assert str(VersionOrder.UNKNOWN) == "unknown"
    assert f"{VersionOrder.OLDER}" == "older"
    assert f"stamp is {compare_versions('0.38.0', '0.37.0')} vs" == "stamp is newer vs"
