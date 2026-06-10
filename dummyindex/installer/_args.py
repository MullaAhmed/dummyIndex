"""Flag parsing shared by `dummyindex install` / `uninstall`."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


def _parse_install_args(
    args: list[str],
) -> tuple[str, Optional[Path], bool, bool, bool]:
    scope = "user"
    project_dir: Optional[Path] = None
    skill_only = False
    no_onboarding = False
    defaults = False
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
    return scope, project_dir, skill_only, no_onboarding, defaults
