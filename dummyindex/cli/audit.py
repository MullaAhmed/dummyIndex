"""`dummyindex context audit` + `audit-log` — the argue-and-audit panel CLI.

Wire-only: parse flags, resolve the ``.context/`` root, hand off to the
``context.audit`` domain (``ensure_audit`` / ``read_audit`` / ``append_log``),
print, and return an exit code. The panel selection + rebuttal debate live in
``skills/audit/SKILL.md`` — this module never runs an agent.

``audit`` takes its own flag alphabet (``--describe``/``--scope``/``--mode``/…)
that the shared ``_common`` helpers don't know, so it parses its own arguments
like ``propose`` does.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from .common import resolve_context_root


_AUDIT_USAGE = "usage: dummyindex context audit start|show ..."


def run(args: list[str]) -> int:
    """`dummyindex context audit start|show ...`."""
    if args[:1] in (["-h"], ["--help"]):
        print(_AUDIT_USAGE)
        return 0
    if not args:
        print(f"error: {_AUDIT_USAGE}", file=sys.stderr)
        return 2
    verb, rest = args[0], args[1:]
    if verb == "start":
        return _audit_start(rest)
    if verb == "show":
        return _audit_show(rest)
    print(
        f"error: unknown audit verb {verb!r} (expected start|show)",
        file=sys.stderr,
    )
    return 2


def _audit_start(args: list[str]) -> int:
    from dummyindex.context.domains.audit import (
        AuditError,
        AuditExistsError,
        ModelRequiredError,
        audit_dir,
        ensure_audit,
        resolve_mode,
        resolve_model,
    )

    values, repeated, flags, err = _parse_flags(
        args,
        value_keys={"describe", "mode", "model", "slug", "root"},
        repeatable_keys={"scope"},
        bool_keys={"force", "json"},
    )
    if err is not None:
        print(f"error: {err} (for `audit start`)", file=sys.stderr)
        return 2

    describe = values.get("describe")
    if not describe:
        print("error: --describe <text> is required", file=sys.stderr)
        return 2

    context_dir = _context_dir(values.get("root"))
    try:
        model = resolve_model(context_dir, values.get("model"))
        mode = resolve_mode(context_dir, values.get("mode"))
        start = ensure_audit(
            context_dir,
            description=describe,
            mode=mode,
            model=model,
            scope=tuple(repeated.get("scope", ())),
            slug=values.get("slug"),
            force="force" in flags,
        )
    except ModelRequiredError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except AuditExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except AuditError as exc:  # slug error, invalid model/mode, empty describe
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if "json" in flags:
        print(json.dumps(start.to_dict(), indent=2))
    else:
        target = audit_dir(context_dir, start.slug)
        personas = ", ".join(c.persona_id for c in start.catalog) or "(none)"
        print(f"context audit: {target} ({len(start.written)} files)")
        print(
            f"  mode={start.config.mode.value} model={start.config.model.value} "
            f"max_rounds={start.config.max_rounds}"
        )
        print(f"  catalog: {personas}")
    return 0


def _audit_show(args: list[str]) -> int:
    from dummyindex.context.domains.audit import (
        AUDITS_REL,
        AuditError,
        AuditNotFoundError,
        audit_dir,
        completed_rounds,
        read_audit,
    )

    values, repeated, flags, err = _parse_flags(
        args,
        value_keys={"slug", "root"},
        repeatable_keys=set(),
        bool_keys={"json"},
    )
    if err is not None:
        print(f"error: {err} (for `audit show`)", file=sys.stderr)
        return 2

    slug = values.get("slug")
    if not slug:
        print("error: --slug <slug> is required", file=sys.stderr)
        return 2

    context_dir = _context_dir(values.get("root"))
    try:
        cfg = read_audit(context_dir, slug)
    except AuditNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except AuditError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    workspace = audit_dir(context_dir, cfg.slug)
    done = completed_rounds(workspace)
    report_written = (workspace / "report.md").exists()

    if "json" in flags:
        print(
            json.dumps(
                {
                    "slug": cfg.slug,
                    "mode": cfg.mode.value,
                    "model": cfg.model.value,
                    "max_rounds": cfg.max_rounds,
                    "scope": list(cfg.scope),
                    "completed_rounds": list(done),
                    "report": (
                        f"{AUDITS_REL}/{cfg.slug}/report.md" if report_written else None
                    ),
                },
                indent=2,
            )
        )
    else:
        print(f"context audit: {cfg.slug}")
        print(
            f"  mode={cfg.mode.value} model={cfg.model.value} "
            f"max_rounds={cfg.max_rounds}"
        )
        print(f"  completed rounds: {', '.join(map(str, done)) or '(none)'}")
        print(f"  report: {'written' if report_written else 'not yet'}")
    return 0


def run_log(args: list[str]) -> int:
    """`dummyindex context audit-log --slug S --round N --persona P --status STATE`."""
    from dummyindex.context.domains.audit import (
        AuditError,
        append_log,
        audit_dir,
    )

    values, repeated, flags, err = _parse_flags(
        args,
        value_keys={"slug", "round", "persona", "status", "note", "root"},
        repeatable_keys=set(),
        bool_keys=set(),
    )
    if err is not None:
        print(f"error: {err} (for `audit-log`)", file=sys.stderr)
        return 2

    slug = values.get("slug")
    round_raw = values.get("round")
    persona = values.get("persona")
    status = values.get("status")
    if not all((slug, round_raw, persona, status)):
        print(
            "error: --slug <S>, --round <N>, --persona <P>, --status <STATE> "
            "are all required",
            file=sys.stderr,
        )
        return 2

    try:
        round_int = int(round_raw)  # type: ignore[arg-type]
    except ValueError:
        print(f"error: --round must be an integer, got {round_raw!r}", file=sys.stderr)
        return 2

    context_dir = _context_dir(values.get("root"))
    try:
        workspace = audit_dir(context_dir, slug)  # type: ignore[arg-type]
        entry = append_log(
            workspace,
            round_num=round_int,
            persona=persona,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            note=values.get("note"),
        )
    except AuditError as exc:  # AuditLogError + AuditSlugError
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"context audit-log: {slug} round={entry.round} "
        f"persona={entry.persona} status={entry.status}"
    )
    return 0


# ----- helpers --------------------------------------------------------------


def _context_dir(root: Optional[str]) -> Path:
    explicit_root = Path(root) if root else None
    return resolve_context_root(Path("."), explicit_root=explicit_root) / ".context"


def _parse_flags(
    args: list[str],
    *,
    value_keys: set[str],
    repeatable_keys: set[str],
    bool_keys: set[str],
) -> tuple[dict[str, str], dict[str, list[str]], set[str], Optional[str]]:
    """Parse ``--key value`` / ``--key=value`` / ``--flag`` arguments.

    Returns ``(values, repeated, flags, error)``. ``repeated`` collects every
    occurrence of a repeatable flag; ``values`` holds the last value of a
    single-value flag; ``flags`` is the set of present boolean flags. ``error``
    is a message on a malformed/unknown argument, else None.
    """
    values: dict[str, str] = {}
    repeated: dict[str, list[str]] = {key: [] for key in repeatable_keys}
    flags: set[str] = set()
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            return values, repeated, flags, f"unexpected argument: {token!r}"
        if "=" in token:
            name, inline_value = token[2:].split("=", 1)
            has_inline = True
        else:
            name, inline_value = token[2:], None
            has_inline = False

        if name in bool_keys:
            if has_inline:
                return values, repeated, flags, f"--{name} takes no value"
            flags.add(name)
            i += 1
            continue

        if name in value_keys or name in repeatable_keys:
            if has_inline:
                value = inline_value or ""
                i += 1
            else:
                if i + 1 >= len(args):
                    return values, repeated, flags, f"--{name} requires a value"
                value = args[i + 1]
                i += 2
            if name in repeatable_keys:
                repeated[name].append(value)
            else:
                values[name] = value
            continue

        return values, repeated, flags, f"unknown argument: --{name}"
    return values, repeated, flags, None
