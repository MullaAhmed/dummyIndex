"""Detect a co-installed `remember` plugin so we can stand down."""

from __future__ import annotations

from pathlib import Path


def remember_plugin_present(root: Path) -> bool:
    """True when the `remember` plugin's store exists at the repo root.

    The plugin writes its tiered history into ``<root>/.remember/``. When
    that directory exists the plugin is active, and dummyindex suppresses
    its own SessionStart memory block to avoid two competing injections.
    """
    return (root / ".remember").is_dir()
