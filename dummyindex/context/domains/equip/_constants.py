"""Package-private constants for `context/equip/`.

Kept out of `enums.py` because schema version is a tunable,
not a closed-alphabet enum.
"""
from __future__ import annotations

SCHEMA_VERSION = 2

# Sentinel embedded in equip's PostToolUse format-hook command string, so
# install/refresh/uninstall can recognise our settings.json entry among the
# user's other hooks. Distinct from the auto-refresh hook's
# ``DUMMYINDEX_AUTO_REFRESH`` so the two coexist and uninstall independently.
EQUIP_SENTINEL = "DUMMYINDEX_EQUIP"
