"""Canonicalization, the bash-only gate extension, grouping, and thresholds."""

from __future__ import annotations

import pytest

from dummyindex.context.domains.memory.miner import (
    LoopKind,
    ToolCallRecord,
    canonical_signature,
    detect_repeated_signatures,
)

pytestmark = pytest.mark.unit


# --- canonical_signature ----------------------------------------------------


def test_bash_pagination_and_ints_collapse_to_one_signature() -> None:
    a = canonical_signature("Bash", {"command": "grep foo bar.log | head -50"})
    b = canonical_signature("Bash", {"command": "grep foo bar.log | head -100"})
    assert a == b


def test_bash_different_commands_do_not_collapse() -> None:
    a = canonical_signature("Bash", {"command": "grep foo bar.log"})
    b = canonical_signature("Bash", {"command": "grep baz bar.log"})
    assert a != b


def test_read_offset_and_limit_are_pagination_fields_dropped() -> None:
    a = canonical_signature(
        "Read", {"file_path": "/repo/a.py", "offset": 0, "limit": 50}
    )
    b = canonical_signature(
        "Read", {"file_path": "/repo/a.py", "offset": 50, "limit": 200}
    )
    assert a == b


def test_read_different_file_path_does_not_collapse() -> None:
    a = canonical_signature("Read", {"file_path": "/repo/a.py", "offset": 0})
    b = canonical_signature("Read", {"file_path": "/repo/b.py", "offset": 0})
    assert a != b


def test_grep_head_limit_is_dropped_but_pattern_kept() -> None:
    a = canonical_signature("Grep", {"pattern": "TODO", "head_limit": 20})
    b = canonical_signature("Grep", {"pattern": "TODO", "head_limit": 100})
    assert a == b


def test_edit_bare_integers_in_content_are_never_collapsed() -> None:
    """The bash-only gate extension: Edit's old_string/new_string must never
    be integer-collapsed, or two unrelated edits that happen to share no
    digits with the same file would still be told apart, but two edits whose
    text differs only by a digit (a version bump, a line number) must NOT be
    merged into one signature — unlike bash commands, this text is the
    change itself, not incidental pagination syntax."""
    a = canonical_signature(
        "Edit", {"file_path": "/repo/a.py", "old_string": "v1", "new_string": "v2"}
    )
    b = canonical_signature(
        "Edit", {"file_path": "/repo/a.py", "old_string": "v3", "new_string": "v4"}
    )
    assert a != b


def test_signature_is_case_and_whitespace_insensitive() -> None:
    a = canonical_signature("Bash", {"command": "echo   hi"})
    b = canonical_signature("bash", {"command": "echo hi"})
    assert a == b


# --- detect_repeated_signatures ---------------------------------------------


def _rec(
    tool: str, sig: str, *, is_error: bool = False, output_bytes: int = 40
) -> ToolCallRecord:
    return ToolCallRecord(
        tool_name=tool, signature=sig, is_error=is_error, output_bytes=output_bytes
    )


def test_below_threshold_within_one_session_is_not_reported() -> None:
    session = [_rec("Bash", "bash::same") for _ in range(2)]
    result = detect_repeated_signatures([session], min_occurrences=3)
    assert result == ()


def test_meets_threshold_within_one_session_is_reported() -> None:
    session = [_rec("Bash", "bash::same") for _ in range(3)]
    result = detect_repeated_signatures([session], min_occurrences=3)
    assert len(result) == 1
    assert result[0].occurrences == 3


def test_qualifying_sessions_pool_their_occurrences() -> None:
    session_a = [_rec("Bash", "bash::same") for _ in range(3)]
    session_b = [_rec("Bash", "bash::same") for _ in range(4)]
    result = detect_repeated_signatures([session_a, session_b], min_occurrences=3)
    assert len(result) == 1
    assert result[0].occurrences == 7


def test_non_qualifying_session_does_not_contribute_to_pool() -> None:
    qualifies = [_rec("Bash", "bash::same") for _ in range(3)]
    below_threshold_elsewhere = [_rec("Bash", "bash::same") for _ in range(1)]
    result = detect_repeated_signatures(
        [qualifies, below_threshold_elsewhere], min_occurrences=3
    )
    assert result[0].occurrences == 3


def test_majority_errors_classified_as_error_repeat() -> None:
    session = [_rec("Read", "read::x", is_error=True) for _ in range(3)]
    result = detect_repeated_signatures([session], min_occurrences=3)
    assert result[0].kind == LoopKind.ERROR_REPEAT


def test_majority_success_classified_as_output_repeat() -> None:
    session = [_rec("Read", "read::x", is_error=False) for _ in range(3)]
    result = detect_repeated_signatures([session], min_occurrences=3)
    assert result[0].kind == LoopKind.OUTPUT_REPEAT


def test_error_repeat_wastes_every_call_tokens() -> None:
    session = [
        _rec("Read", "read::x", is_error=True, output_bytes=40) for _ in range(3)
    ]
    result = detect_repeated_signatures([session], min_occurrences=3)
    # BYTES_PER_TOKEN=4 -> 10 tokens/call * 3 calls = 30
    assert result[0].estimated_wasted_tokens == 30


def test_output_repeat_excludes_largest_call_as_legitimate() -> None:
    session = [
        _rec("Read", "read::x", output_bytes=400),
        _rec("Read", "read::x", output_bytes=40),
        _rec("Read", "read::x", output_bytes=40),
    ]
    result = detect_repeated_signatures([session], min_occurrences=3)
    # 400 bytes = 100 tokens (excluded as legitimate first call), 40+40 -> 10+10
    assert result[0].estimated_wasted_tokens == 20


def test_results_are_sorted_by_wasted_tokens_descending() -> None:
    small = [
        _rec("Read", "read::small", is_error=True, output_bytes=8) for _ in range(3)
    ]
    big = [_rec("Bash", "bash::big", is_error=True, output_bytes=800) for _ in range(3)]
    result = detect_repeated_signatures([small, big], min_occurrences=3)
    assert [r.signature for r in result] == ["bash::big", "read::small"]


def test_default_min_occurrences_is_three() -> None:
    session = [_rec("Bash", "bash::same") for _ in range(2)]
    assert detect_repeated_signatures([session]) == ()
    session3 = [_rec("Bash", "bash::same") for _ in range(3)]
    assert len(detect_repeated_signatures([session3])) == 1
