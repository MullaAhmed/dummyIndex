"""Family enumeration + crash-safe temp-artifact naming for the link package.

Obeys the package import law (``link/__init__.py``): stdlib + ``..common`` only.
"""

from __future__ import annotations

from pathlib import Path

from ..common import _SIBLING_SKILLS

# --- family enumeration

# Link-mode families: main + every `_SIBLING_SKILLS` label, in order. Never a
# `dummyindex*` glob: that would also match the equip-generated
# `dummyindex-verify` skill, which this family does not own.
_MAIN_FAMILY = "dummyindex"


def _family_names() -> tuple[str, ...]:
    return (_MAIN_FAMILY, *(label for _sub_name, label in _SIBLING_SKILLS))


# --- crash-safe temp-artifact naming

_TMP_LINK_SUFFIX = ".dummyindex-link.tmp"
_TMP_OLD_SUFFIX = ".dummyindex-old.tmp"
_PROBE_NAME = ".dummyindex-symlink-probe.tmp"

_CAPABILITY_HINT = (
    "on Windows, enable Developer Mode (or run as Administrator) so symlink "
    "creation is permitted, or run `git config core.symlinks true` and "
    "re-checkout so a fresh clone gets real symlinks"
)


def _dotfiles_hint(scope_root: Path) -> str:
    return (
        f" (if {scope_root}/.claude is itself a dotfiles symlink to a "
        "directory elsewhere — e.g. `~/.claude -> ~/dotfiles/claude` — the "
        "relative link cannot reach the real .agents/skills tree from "
        "there; use --copy for this scope)"
    )
