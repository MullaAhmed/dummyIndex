"""The CLI keeps help readable under legacy Windows stream encodings."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.paths import REPO_ROOT


@pytest.mark.integration
def test_help_survives_cp1252_stdout_with_unicode_usage(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = env["HOME"]
    env["CODEX_HOME"] = str(home / ".codex")
    env["PYTHONIOENCODING"] = "cp1252"

    result = subprocess.run(
        [sys.executable, "-m", "dummyindex", "context", "assign-files", "--help"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode("cp1252", errors="replace")
    assert b"files \\u222a new" in result.stdout
    assert b"UnicodeEncodeError" not in result.stderr
