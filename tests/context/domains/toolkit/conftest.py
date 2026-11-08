"""Shared fixtures for the toolkit facade tests.

``root`` is a project folder with a ``.context/`` directory, ``home`` is a user
home, and ``out_dir`` is the terminal bundle folder. All three sit under
``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / ".context").mkdir(parents=True)
    return project


@pytest.fixture
def home(tmp_path: Path) -> Path:
    user_home = tmp_path / "home"
    user_home.mkdir()
    return user_home


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "app-data" / "toolkit"
    folder.mkdir(parents=True)
    return folder
