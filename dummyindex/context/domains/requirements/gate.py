"""Hard gate for the required-setup manifest: decides one ``UserPromptSubmit``.

Fail-open by design. A broken gate must not lock a developer out of their
own prompt, so unknown, invalid or erroring states pass with a warning.
Only a row proven ``missing`` or ``version-mismatch`` blocks.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..atomic_io import write_text_atomic
from .check import CLI_FIX, SYNC_FIX, check_requirements
from .constants import BYPASS_ENV, BYPASS_REL, CONFIG_TOML_REL, OK_MARKER_REL
from .enums import RequirementStatus
from .errors import RequirementsError
from .models import RequirementRow
from .toml_io import read_requirements

_PASS_PREFIXES = ("/dummyindex", "/plugin", "/clear", "/exit")
_BLOCKING = frozenset({RequirementStatus.MISSING, RequirementStatus.VERSION_MISMATCH})
_SOFT = frozenset({RequirementStatus.UNKNOWN, RequirementStatus.INVALID})
_MAX_BYPASS_HOURS = 24
_BYPASS_HINT = (
    f"Bypass: `dummyindex context requirements bypass --hours N` (1-24), "
    f"or set {BYPASS_ENV}=1."
)


@dataclass(frozen=True)
class GateDecision:
    block: bool
    reason: str
    warning: str | None


def gate_decision(
    rows: tuple[RequirementRow, ...], *, prompt: str, bypass: bool
) -> GateDecision:
    if prompt.lstrip().startswith(_PASS_PREFIXES):
        return GateDecision(block=False, reason="", warning=None)
    if bypass:
        return GateDecision(
            block=False,
            reason="",
            warning="requirements bypass active: unmet setup is not enforced",
        )
    blocking = [row for row in rows if row.status in _BLOCKING]
    if blocking:
        return GateDecision(block=True, reason=_block_reason(blocking), warning=None)
    soft = [row for row in rows if row.status in _SOFT]
    if soft:
        return GateDecision(block=False, reason="", warning=_soft_warning(soft))
    return GateDecision(block=False, reason="", warning=None)


def read_bypass(project_root: Path, *, env: Mapping[str, str], now: datetime) -> bool:
    """True when the env var is ``1`` or a non-expired bypass file exists."""
    if env.get(BYPASS_ENV) == "1":
        return True
    try:
        data = json.loads((project_root / BYPASS_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    expires = _parse_utc(data.get("expires"))
    return expires is not None and expires > now


def write_bypass(project_root: Path, hours: int, *, now: datetime) -> Path:
    if isinstance(hours, bool) or not isinstance(hours, int):
        raise ValueError("bypass hours must be an integer")
    if not 1 <= hours <= _MAX_BYPASS_HOURS:
        raise ValueError(f"bypass hours must be 1-{_MAX_BYPASS_HOURS}, got {hours}")
    path = project_root / BYPASS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    expires = now.astimezone(timezone.utc) + timedelta(hours=hours)
    write_text_atomic(path, json.dumps({"expires": expires.isoformat()}) + "\n")
    return path


def write_ok_marker(project_root: Path) -> None:
    path = project_root / OK_MARKER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, "ok\n")


def run_gate(
    project_root: Path,
    stdin_text: str,
    *,
    claude_config_dir: Path,
    family_stamp: str | None,
    cli_version: str,
    env: Mapping[str, str],
    now: datetime | None = None,
) -> str:
    """Hook output for one prompt: block JSON, warning JSON, or ``""``."""
    config = project_root / CONFIG_TOML_REL
    if not config.exists():
        return ""
    moment = now or datetime.now(timezone.utc)
    try:
        requirements = read_requirements(config)
        if requirements is None:
            return ""
        rows = check_requirements(
            project_root,
            requirements,
            claude_config_dir=claude_config_dir,
            family_stamp=family_stamp,
            cli_version=cli_version,
        )
        if all(row.status is RequirementStatus.SATISFIED for row in rows):
            try:
                write_ok_marker(project_root)
            except OSError:
                # Read-only cache is not a setup gap; the marker is only a fast path.
                pass
            return ""
        decision = gate_decision(
            rows,
            prompt=_prompt_from(stdin_text),
            bypass=read_bypass(project_root, env=env, now=moment),
        )
    except RequirementsError as exc:
        return _context_json(f"requirements check skipped, config.toml invalid: {exc}")
    except Exception as exc:  # noqa: BLE001
        # Fail-open is the contract: any internal error passes the prompt with a warning.
        return _context_json(f"requirements gate error, prompt passed: {exc}")
    if decision.block:
        return json.dumps({"decision": "block", "reason": decision.reason})
    if decision.warning:
        return _context_json(decision.warning)
    return ""


def _prompt_from(stdin_text: str) -> str:
    try:
        data = json.loads(stdin_text)
    except ValueError:
        return ""
    prompt = data.get("prompt") if isinstance(data, dict) else None
    return prompt if isinstance(prompt, str) else ""


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _block_reason(rows: list[RequirementRow]) -> str:
    lines = ["Required dummyindex setup is not met (.context/config.toml):"]
    for row in rows:
        fix = row.fix or SYNC_FIX
        detail = f": {row.reason}" if row.reason else ""
        lines.append(f"- {row.kind.value} {row.name}{detail}. Fix: {fix}")
    lines.append(
        f"Run `{SYNC_FIX}` in another terminal, then resend. "
        f"If the CLI is outdated, install it: {CLI_FIX}."
    )
    lines.append(_BYPASS_HINT)
    return "\n".join(lines)


def _soft_warning(rows: list[RequirementRow]) -> str:
    items = "; ".join(
        f"{row.kind.value} {row.name} is {row.status.value}"
        + (f" ({row.reason})" if row.reason else "")
        for row in rows
    )
    return f"requirements not verified, prompt passed: {items}"


def _context_json(text: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": text,
            }
        }
    )
