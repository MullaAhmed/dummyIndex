"""Flag parsing shared by `dummyindex install` / `uninstall`."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


_INSTALL_USAGE = """\
usage: dummyindex install [options]

Copy the dummyindex skill family into Claude Code's skills dir, then — when
run from (or pointed at) a git repo — auto-init the project: build `.context/`,
write a managed CLAUDE.md block, and install the SessionStart drift hook. On an
existing curated index the auto-init is non-destructive (deterministic refresh
only; the council taxonomy is preserved).

options:
  --scope user|project   where to install the skill (default: user)
  --dir PATH             project dir to install into / auto-init (default: cwd)
  --skill-only           install the skill only; skip project auto-init
  --no-onboarding        non-interactive: write .context/config.json defaults
  --defaults             alias for --no-onboarding
  --no-superpowers       don't enable the superpowers plugin on init
  -h, --help             show this help and exit
"""


def _print_install_usage() -> None:
    """Print the install/uninstall usage block to stdout.

    Kept here (not in __main__) so probing ``install --help`` never has to
    construct the installer or touch the filesystem.
    """
    print(_INSTALL_USAGE, end="")


def parse_install_args(
    args: list[str],
) -> tuple[str, Optional[Path], bool, bool, bool, bool]:
    # Help is handled first so probing `install --help` / `-h` prints usage and
    # exits cleanly — it must NEVER fall through to running a real install
    # ("probing the command IS running it" was the trap).
    if "-h" in args or "--help" in args:
        _print_install_usage()
        sys.exit(0)

    scope = "user"
    project_dir: Optional[Path] = None
    skill_only = False
    no_onboarding = False
    defaults = False
    no_superpowers = False
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--scope="):
            scope = a.split("=", 1)[1]
            i += 1
        elif a == "--scope" and i + 1 < len(args):
            scope = args[i + 1]
            i += 2
        elif a.startswith("--dir="):
            project_dir = Path(a.split("=", 1)[1])
            i += 1
        elif a == "--dir" and i + 1 < len(args):
            project_dir = Path(args[i + 1])
            i += 2
        elif a == "--skill-only":
            skill_only = True
            i += 1
        elif a == "--no-onboarding":
            no_onboarding = True
            i += 1
        elif a == "--defaults":
            defaults = True
            i += 1
        elif a == "--no-superpowers":
            no_superpowers = True
            i += 1
        elif a in ("--platform", "--platform=claude") or a.startswith("--platform="):
            # Legacy v1 flag — the multi-platform installers are gone.
            # Skip silently so old `dummyindex install --platform claude`
            # docs continue to "just work" instead of erroring.
            if a == "--platform" and i + 1 < len(args):
                i += 2
            else:
                i += 1
        else:
            print(f"error: unknown install argument {a!r}", file=sys.stderr)
            sys.exit(2)
    return scope, project_dir, skill_only, no_onboarding, defaults, no_superpowers
