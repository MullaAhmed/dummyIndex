"""Default config resolution must stay inside pytest's temporary directories."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dummyindex.codex_guidance import codex_home
from dummyindex.context.domains.memory.miner.resolve import resolve_claude_config_dir


@pytest.mark.unit
def test_default_user_config_is_temporary(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    test_home = Path.home()
    assert test_home.is_relative_to(tmp_path_factory.getbasetemp())
    assert os.environ["HOME"] == os.environ["USERPROFILE"] == str(test_home)
    assert "CODEX_HOME" not in os.environ
    assert "CLAUDE_CONFIG_DIR" not in os.environ
    assert codex_home() == test_home / ".codex"
    assert resolve_claude_config_dir() == test_home / ".claude"


@pytest.mark.unit
def test_child_process_inherits_only_temporary_user_config() -> None:
    code = (
        "import json; from pathlib import Path; "
        "from dummyindex.codex_guidance import codex_home; "
        "from dummyindex.context.domains.memory.miner.resolve import resolve_claude_config_dir; "
        "print(json.dumps([str(Path.home()),str(codex_home()),str(resolve_claude_config_dir())]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    paths = [Path(path) for path in json.loads(result.stdout)]
    assert paths == [Path.home(), Path.home() / ".codex", Path.home() / ".claude"]
