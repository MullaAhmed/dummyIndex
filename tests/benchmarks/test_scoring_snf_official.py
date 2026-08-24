"""Official SNF grader port tests — sanitize, BLEU, best-match evaluation."""

from __future__ import annotations

import pytest

from benchmarks.scoring.snf_official import (
    HEADLINE_THRESHOLD,
    GraderError,
    compute_function_similarity,
    grade_snf_official,
    needle_evaluator,
    remove_comments,
    sanitize_output,
)


def make_repo_info() -> dict:
    """Two needles whose bodies are trivially distinguishable by BLEU."""
    return {
        "content": {
            "src/a.py": "\n".join(
                [
                    "def alpha(x):",
                    "    total = x + 1",
                    "    return total",
                    "",
                    "def beta(y):",
                    "    count = y * 7",
                    "    if count > 3:",
                    "        count = 0",
                    "    return count",
                ]
            )
        },
        "needles": [
            {"name": "alpha", "path": "src/a.py", "start_line": 0, "end_line": 3},
            {"name": "beta", "path": "src/a.py", "start_line": 4, "end_line": 9},
        ],
    }


ALPHA = "def alpha(x):\n    total = x + 1\n    return total"
BETA = (
    "def beta(y):\n    count = y * 7\n    if count > 3:\n"
    "        count = 0\n    return count"
)


class TestSanitizeOutput:
    def test_plain_text_passthrough(self) -> None:
        assert sanitize_output("def f():\n    pass", "python") == ("def f():\n    pass")

    def test_fenced_block_extracts_first_function(self) -> None:
        output = f"Here you go:\n```python\n{ALPHA}\n```\ndone"
        assert sanitize_output(output, "python").strip() == ALPHA

    def test_fenced_block_without_lang_tag(self) -> None:
        output = f"```\n{ALPHA}\n```"
        assert sanitize_output(output, "python").strip() == ALPHA

    def test_multiple_blocks_uses_first_with_function(self) -> None:
        output = f"```text\nnot code\n```\n```python\n{ALPHA}\n```"
        assert sanitize_output(output, "python").strip() == ALPHA


class TestRemoveComments:
    def test_strips_python_comment(self) -> None:
        src = "x = 1  # trailing\ny = 2\n"
        cleaned = remove_comments(src, "python")
        assert "# trailing" not in cleaned
        assert "y = 2" in cleaned

    def test_strips_docstring(self) -> None:
        src = 'def f():\n    """doc"""\n    return 1'
        cleaned = remove_comments(src, "python")
        assert "doc" not in cleaned
        assert "return 1" in cleaned


class TestSimilarity:
    def test_identical_text_scores_one(self) -> None:
        assert compute_function_similarity(ALPHA, ALPHA) == pytest.approx(1.0)

    def test_disjoint_text_scores_low(self) -> None:
        score = compute_function_similarity("zzzz qqqq", ALPHA)
        assert score < 0.1

    def test_close_text_scores_between(self) -> None:
        near = ALPHA.replace("total", "summed")
        score = compute_function_similarity(near, ALPHA)
        assert 0.05 < score <= 1.0


class TestNeedleEvaluator:
    def test_exact_needle_wins(self) -> None:
        target, similarity = needle_evaluator(BETA, "beta", make_repo_info(), "python")
        assert target == "beta"
        assert similarity >= HEADLINE_THRESHOLD

    def test_wrong_needle_detected(self) -> None:
        target, _ = needle_evaluator(ALPHA, "beta", make_repo_info(), "python")
        assert target == "alpha"

    def test_garbage_matches_nothing_confidently(self) -> None:
        target, similarity = needle_evaluator(
            "unrelated text entirely", "alpha", make_repo_info(), "python"
        )
        assert similarity < HEADLINE_THRESHOLD


class TestGradeSnfOfficial:
    def test_passes_at_headline_threshold(self) -> None:
        verdict = grade_snf_official(BETA, "beta", make_repo_info(), "python")
        assert verdict.passed_at()
        ladder = verdict.ladder()
        assert ladder[0.8] is True
        assert verdict.best_target == "beta"

    def test_fails_when_best_target_differs(self) -> None:
        verdict = grade_snf_official(ALPHA, "beta", make_repo_info(), "python")
        assert not verdict.passed_at()
        assert verdict.best_target == "alpha"

    def test_unsupported_language_raises_before_bleu(self) -> None:
        with pytest.raises(GraderError):
            needle_evaluator("x", "y", {"content": {}, "needles": []}, "cobol")


class TestMissingNltk:
    def test_helpful_error_when_nltk_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def block_nltk(name: str, *a, **k):  # type: ignore[no-untyped-def]
            if name.startswith("nltk"):
                raise ImportError("blocked in test")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", block_nltk)
        with pytest.raises(GraderError, match="uv pip install nltk"):
            compute_function_similarity("a b", "a b")
