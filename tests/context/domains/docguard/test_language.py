"""Tests for ``domains/docguard/language.py``."""

from __future__ import annotations

import pytest

from dummyindex.context.domains.docguard.language import (
    MIN_CHARS,
    WARN_BELOW,
    cjk_share,
    needs_warning,
)


@pytest.mark.unit
def test_min_chars_boundary():
    assert MIN_CHARS == 200
    assert cjk_share("中" * 199) is None
    assert cjk_share("中" * 200) is not None


@pytest.mark.unit
def test_warning_boundary_at_half_and_below():
    assert WARN_BELOW == 0.5
    share_half = cjk_share("中" * 100 + " " + " ".join(["word"] * 100))
    assert share_half == pytest.approx(0.5)
    assert needs_warning(share_half) is False

    share_049 = cjk_share("中" * 49 + " " + " ".join(["word"] * 51) + " " + "1" * 200)
    assert share_049 == pytest.approx(0.49)
    assert needs_warning(share_049) is True


@pytest.mark.unit
def test_needs_warning_none_is_false():
    assert needs_warning(None) is False


@pytest.mark.unit
def test_pure_code_prompt_is_none():
    code_words = " ".join(["print"] * 100)
    text = (
        f"```python\n{code_words}\n```\n"
        "use `x = 1` here see https://example.com/docs/page and "
        "dummyindex/cli/check.py foo.py"
    )
    assert cjk_share(text) is None


@pytest.mark.unit
def test_pure_chinese_near_one():
    assert cjk_share("中文写作说明" * 50) == pytest.approx(1.0)


@pytest.mark.unit
def test_pure_english_zero_and_warns():
    share = cjk_share(" ".join(["hello"] * 100))
    assert share == pytest.approx(0.0)
    assert needs_warning(share) is True


@pytest.mark.unit
def test_paths_and_filenames_not_counted():
    text = "中" * 200 + " dummyindex/cli/check.py foo.py"
    assert cjk_share(text) == pytest.approx(1.0)


@pytest.mark.unit
def test_paths_inside_unspaced_chinese_keep_cjk():
    text = "先读dummyindex/cli/check.py再改foo.py然后跑测试并汇报结果。" * 20
    assert cjk_share(text) == pytest.approx(1.0)
