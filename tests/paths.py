"""Filesystem anchors shared across the test tree.

Import these instead of chaining ``Path(__file__).parent.parent`` — the
anchors stay correct no matter how deep a test module sits.
"""

from __future__ import annotations

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
SAMPLE_REPO = FIXTURES_DIR / "sample_repo"
