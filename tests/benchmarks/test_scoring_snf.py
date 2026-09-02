"""SNF grader tests — the official RepoQA substring rule."""

from __future__ import annotations

from benchmarks.scoring.snf import grade_snf


class TestOfficialRule:
    def test_exact_name_passes(self) -> None:
        assert grade_snf("authenticate_user", "authenticate_user").passed

    def test_case_insensitive(self) -> None:
        assert grade_snf("The function is AUTHENTICATE_user.", "authenticate_user")

    def test_substring_inside_larger_text(self) -> None:
        assert grade_snf(
            "found it: def authenticate_user(...) in auth.py",
            "authenticate_user",
        ).passed

    def test_wrong_function_fails(self) -> None:
        assert not grade_snf("verify_token", "authenticate_user").passed

    def test_empty_response_fails(self) -> None:
        assert not grade_snf("", "anything").passed

    def test_partial_name_is_not_enough(self) -> None:
        assert not grade_snf("authenticate", "authenticate_user").passed

    def test_verdict_carries_needle(self) -> None:
        verdict = grade_snf("nope", "needle_x")
        assert verdict.needle == "needle_x"
