"""Closed alphabets and fixed policy for the GUI-facing ``toolkit`` facade.

The launch-mechanism table mirrors ``docs/spikes/toolkit-scopes.md`` (the
capability matrix) and ``docs/engine-contract.md`` section 9.2: a terminal scope
is granted only for a (kind, mechanism) pair the spike proved. A terminal request
for an item that already lives in project or user host config is not proven, so
it falls back to that host scope with a warning.
"""

from __future__ import annotations

from typing import Final

SCHEMA_VERSION: Final = 1

KINDS: Final = ("mcp", "skill", "plugin")
SCOPES: Final = ("terminal", "project", "user")
INSTALL_SCOPES: Final = ("project", "user")

MECHANISM_MCP_ADDITIVE: Final = "mcp_additive"
MECHANISM_MCP_EXCLUSIVE: Final = "mcp_exclusive"
MECHANISM_PLUGIN_DIR: Final = "plugin_dir"
MECHANISM_SETTINGS: Final = "settings"
MECHANISM_ADD_DIR: Final = "add_dir"

MECHANISMS: Final = (
    MECHANISM_MCP_ADDITIVE,
    MECHANISM_MCP_EXCLUSIVE,
    MECHANISM_PLUGIN_DIR,
    MECHANISM_SETTINGS,
    MECHANISM_ADD_DIR,
)

# kind -> launch mechanisms proven for a terminal-owned item (spikes B, C, E, I, N).
PROVEN_TERMINAL_MECHANISMS: Final[dict[str, tuple[str, ...]]] = {
    "mcp": (MECHANISM_MCP_ADDITIVE, MECHANISM_MCP_EXCLUSIVE),
    "skill": (MECHANISM_ADD_DIR,),
    "plugin": (MECHANISM_PLUGIN_DIR, MECHANISM_SETTINGS),
}

# Sources a toolkit install may name. The only scheme is ``github``, written as
# ``github:<owner>/<repo>[/<path>][@<ref>]``. ``<path>`` is the skill folder, the
# mcp ``.json`` file, or the plugin name, depending on kind. Local paths, URLs
# and shell strings are refused, so an install reads only from a pinned GitHub
# commit.
ALLOWED_SOURCE_SCHEMES: Final = ("github",)

# Repos Anthropic publishes as trusted marketplaces (same policy as the equip
# seed list). Installs from anything else still need --yes with the plan hash.
TRUSTED_REPOS: Final = frozenset(
    {
        "anthropics/claude-plugins-official",
        "anthropics/knowledge-work-plugins",
        "anthropics/skills",
        "anthropics/claude-code",
    }
)

STASH_FILE: Final = "disabled.json"
PROJECT_STASH_DIR: Final = (".context", "toolkit")
USER_STASH_DIR: Final = ("toolkit",)
BUNDLE_MANIFEST: Final = "toolkit.json"
BUNDLE_MCP_FILE: Final = "mcp.json"
BUNDLE_SETTINGS_FILE: Final = "settings.json"
BUNDLE_PLUGINS_DIR: Final = "plugins"
BUNDLE_SKILLS_DIR: Final = "skills-dir"

# Error codes that mean the request itself was malformed (exit 2). Every other
# code is an operational failure (exit 1).
USAGE_CODES: Final = frozenset(
    {
        "usage",
        "invalid_argument",
        "invalid_name",
        "invalid_terminal_id",
        "invalid_source",
        "unsupported_source",
        "unsupported_scope",
        "terminal_required",
        "out_dir_required",
    }
)
