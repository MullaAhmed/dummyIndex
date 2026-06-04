"""Render a :class:`PreflightReport` as a human-readable markdown summary.

The summary is what the running ``/dummyindex`` session shows the user before
writing anything: the three files dummyindex manages, everything it leaves
untouched, and any warnings (an unparseable settings file, a dirty tree).
"""
from __future__ import annotations

from .models import PreflightReport

# Exactly the paths the PR1-4 flow writes. Kept in one place so the promise
# the report makes matches what install/ingest actually touch.
_MANAGED_PATHS = (
    ".context/**",
    ".claude/CLAUDE.md  (managed block only — surrounding content preserved)",
    ".claude/settings.json  (one additive SessionStart hook)",
)


def render_preflight_md(report: PreflightReport) -> str:
    """Return the preflight summary as markdown."""
    lines: list[str] = []
    lines.append("# dummyindex preflight")
    lines.append("")
    lines.append(f"Inventory of `{report.project_root}` before any write.")
    lines.append("")

    lines.append("## Will write / manage")
    for path in _MANAGED_PATHS:
        lines.append(f"- `{path}`")
    lines.append("")

    lines.append("## Will leave untouched")
    lines.append(_leave_line("rule files in `.claude/rules/`", report.rule_files))
    lines.append(_leave_line("project agents in `.claude/agents/`", report.project_agents))
    if report.settings.user_hook_events:
        lines.append(
            f"- your hooks under: {_join(report.settings.user_hook_events)} "
            "(only dummyindex's own entry is added/refreshed)"
        )
    else:
        lines.append("- your hooks: none found")
    lines.append("- every source file and prose doc in the repo")
    lines.append("")

    warnings = _warnings(report)
    if warnings:
        lines.append("## ⚠ Warnings")
        lines.extend(f"- {w}" for w in warnings)
        lines.append("")

    lines.append("## State")
    lines.append(f"- CLAUDE.md: {_claude_md_state(report)}")
    lines.append(f"- settings.json: {_settings_state(report)}")
    lines.append(f"- git: {_git_state(report)}")

    return "\n".join(lines)


def _warnings(report: PreflightReport) -> list[str]:
    out: list[str] = []
    if report.settings.exists and not report.settings.parseable:
        out.append(
            "`.claude/settings.json` is not valid JSON — dummyindex will refuse "
            "to touch it. Fix it by hand first."
        )
    if report.git_clean is False:
        out.append(
            "working tree has uncommitted changes — commit or stash first so "
            "dummyindex's writes stay reversible."
        )
    if report.git_clean is None:
        if report.is_git_repo:
            out.append(
                "git status could not be determined — reversibility of writes "
                "is unknown."
            )
        else:
            out.append("not a git repo — writes won't be reversible via git.")
    return out


def _leave_line(label: str, items: tuple[str, ...]) -> str:
    if not items:
        return f"- {label}: none found"
    return f"- {label}: {len(items)} ({_join(items)})"


def _join(items: tuple[str, ...]) -> str:
    shown = ", ".join(items[:8])
    if len(items) > 8:
        shown += f", +{len(items) - 8} more"
    return shown


def _claude_md_state(report: PreflightReport) -> str:
    if not report.claude_md_exists:
        return "absent — a new one with a managed block will be created"
    if report.claude_md_has_managed_block:
        return "present, already has a dummyindex managed block (refreshed in place)"
    return "present — a managed block will be appended; your content is preserved"


def _settings_state(report: PreflightReport) -> str:
    s = report.settings
    if not s.exists:
        return "absent — a new one with the SessionStart hook will be created"
    if not s.parseable:
        return "present but unparseable — left untouched"
    if s.dummyindex_hook_present:
        return "present, dummyindex hook already installed (refreshed in place)"
    return "present — the SessionStart hook will be added alongside your entries"


def _git_state(report: PreflightReport) -> str:
    if not report.is_git_repo:
        return "not a git repo"
    if report.git_clean is None:
        return "unknown (git query failed)"
    return "clean" if report.git_clean else "dirty (uncommitted changes)"
