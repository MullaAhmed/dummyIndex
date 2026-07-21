"""Flag parsing for `dummyindex install` and `dummyindex uninstall`."""

from __future__ import annotations

import sys
from pathlib import Path

_INSTALL_USAGE = """\
usage: dummyindex install [options]

Copy the dummyindex skill family into Claude Code, Codex, or both, then — when
run from (or pointed at) a git repo — auto-init the project: build `.context/`
and write the selected host guidance. Claude installs its managed hooks;
Codex writes the active project instruction file (`AGENTS.override.md`,
`AGENTS.md`, or a configured fallback). On an existing
curated index the auto-init is non-destructive (deterministic refresh only; the
council taxonomy is preserved).

options:
  --platform claude|codex|both
                         target host (default: claude, for backward compatibility)
  --scope user|project   where to install the skill (default: user)
  --dir PATH             project dir to install into / auto-init (default: cwd)
  --skill-only           install the skill only; skip project auto-init
  --no-onboarding        non-interactive: write .context/config.json defaults
  --defaults             alias for --no-onboarding
  --no-superpowers       don't enable the superpowers plugin on init
  -h, --help             show this help and exit
"""

_UNINSTALL_USAGE = """\
usage: dummyindex uninstall [options]

Remove the selected dummyindex skill family. Claude removal also removes its
slash-command aliases but leaves project guidance and hooks intact. Codex
removes its managed guidance at the selected scope; user scope also removes a
current/--dir project block only when it is stamped as that user's auto-init.

options:
  --platform claude|codex|both
                         target host (default: claude)
  --scope user|project   scope to remove (default: user)
  --dir PATH             project associated with the removal (default: cwd)
  -h, --help             show this help and exit
"""


def _print_install_usage() -> None:
    """Print install usage to stdout.

    Kept here (not in __main__) so probing ``install --help`` never has to
    construct the installer or touch the filesystem.
    """
    print(_INSTALL_USAGE, end="")


def _print_uninstall_usage() -> None:
    """Print uninstall usage to stdout."""
    print(_UNINSTALL_USAGE, end="")


def parse_install_args(
    args: list[str],
) -> tuple[str, Path | None, bool, bool, bool, bool, str]:
    # Help is handled first so probing `install --help` / `-h` prints usage and
    # exits cleanly — it must NEVER fall through to running a real install
    # ("probing the command IS running it" was the trap).
    if "-h" in args or "--help" in args:
        _print_install_usage()
        sys.exit(0)

    scope = "user"
    project_dir: Path | None = None
    skill_only = False
    no_onboarding = False
    defaults = False
    no_superpowers = False
    platform = "claude"
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--scope="):
            scope = a.split("=", 1)[1]
            i += 1
        elif a == "--scope" and i + 1 < len(args) and not args[i + 1].startswith("--"):
            scope = args[i + 1]
            i += 2
        elif a == "--scope":
            print("error: --scope requires user|project", file=sys.stderr)
            sys.exit(2)
        elif a.startswith("--dir="):
            project_dir = Path(a.split("=", 1)[1])
            i += 1
        elif a == "--dir" and i + 1 < len(args) and not args[i + 1].startswith("--"):
            project_dir = Path(args[i + 1])
            i += 2
        elif a == "--dir":
            print("error: --dir requires PATH", file=sys.stderr)
            sys.exit(2)
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
        elif a.startswith("--platform="):
            platform = a.split("=", 1)[1]
            i += 1
        elif (
            a == "--platform" and i + 1 < len(args) and not args[i + 1].startswith("--")
        ):
            platform = args[i + 1]
            i += 2
        elif a == "--platform":
            print("error: --platform requires claude|codex|both", file=sys.stderr)
            sys.exit(2)
        else:
            print(f"error: unknown install argument {a!r}", file=sys.stderr)
            sys.exit(2)
    if platform not in ("claude", "codex", "both"):
        print(
            f"error: --platform must be claude|codex|both, got {platform!r}",
            file=sys.stderr,
        )
        sys.exit(2)
    if scope not in ("user", "project"):
        print(
            f"error: --scope must be user|project, got {scope!r}",
            file=sys.stderr,
        )
        sys.exit(2)
    return (
        scope,
        project_dir,
        skill_only,
        no_onboarding,
        defaults,
        no_superpowers,
        platform,
    )


def parse_uninstall_args(args: list[str]) -> tuple[str, Path | None, str]:
    """Parse only the flags meaningful to uninstall.

    Install-only options are rejected instead of being silently accepted and
    discarded by the uninstall dispatcher.
    """
    if "-h" in args or "--help" in args:
        _print_uninstall_usage()
        sys.exit(0)

    scope = "user"
    project_dir: Path | None = None
    platform = "claude"
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--scope="):
            scope = arg.split("=", 1)[1]
            i += 1
        elif (
            arg == "--scope" and i + 1 < len(args) and not args[i + 1].startswith("--")
        ):
            scope = args[i + 1]
            i += 2
        elif arg == "--scope":
            print("error: --scope requires user|project", file=sys.stderr)
            sys.exit(2)
        elif arg.startswith("--dir="):
            project_dir = Path(arg.split("=", 1)[1])
            i += 1
        elif arg == "--dir" and i + 1 < len(args) and not args[i + 1].startswith("--"):
            project_dir = Path(args[i + 1])
            i += 2
        elif arg == "--dir":
            print("error: --dir requires PATH", file=sys.stderr)
            sys.exit(2)
        elif arg.startswith("--platform="):
            platform = arg.split("=", 1)[1]
            i += 1
        elif (
            arg == "--platform"
            and i + 1 < len(args)
            and not args[i + 1].startswith("--")
        ):
            platform = args[i + 1]
            i += 2
        elif arg == "--platform":
            print("error: --platform requires claude|codex|both", file=sys.stderr)
            sys.exit(2)
        else:
            print(f"error: unknown uninstall argument {arg!r}", file=sys.stderr)
            sys.exit(2)

    if scope not in ("user", "project"):
        print(
            f"error: --scope must be user|project, got {scope!r}",
            file=sys.stderr,
        )
        sys.exit(2)
    if platform not in ("claude", "codex", "both"):
        print(
            f"error: --platform must be claude|codex|both, got {platform!r}",
            file=sys.stderr,
        )
        sys.exit(2)
    return scope, project_dir, platform
