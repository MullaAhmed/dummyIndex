"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture(autouse=True)
def _no_real_plugin_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let the production default-plugin path shell out to the real
    ``claude`` CLI during tests. Unit tests that inject a runner bypass this
    guard (see ``install_default_plugins``); everything else defers."""
    from dummyindex.context.default_plugins import SKIP_INSTALL_ENV

    monkeypatch.setenv(SKIP_INSTALL_ENV, "1")
