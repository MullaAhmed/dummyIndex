"""Render usage buckets to display strings.

Pure functions: frozen data in, formatted `str` out. Printing happens at the
CLI boundary (`__main__`), never here.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from .aggregate import grand_total
from .models import Block, ChatReport, PeriodBucket, SessionBucket, Totals


def _c(value: int) -> str:
    """Thousands-separated integer."""
    return f"{value:,}"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """A simple fixed-width table: first column left-aligned, rest right.

    Column widths are the max cell width in each column, so it stays aligned
    whatever the magnitudes.
    """
    columns = [headers, *rows]
    widths = [max(len(row[i]) for row in columns) for i in range(len(headers))]

    def _fmt(row: Sequence[str]) -> str:
        cells = [row[0].ljust(widths[0])]
        cells += [row[i].rjust(widths[i]) for i in range(1, len(headers))]
        return "  ".join(cells).rstrip()

    lines = [_fmt(headers), "  ".join("-" * w for w in widths)]
    lines += [_fmt(row) for row in rows]
    return "\n".join(lines)


def _totals_row(label: str, totals: Totals) -> list[str]:
    return [
        label,
        _c(totals.input_tokens),
        _c(totals.cache_creation_tokens),
        _c(totals.cache_read_tokens),
        _c(totals.output_tokens),
        _c(grand_total(totals)),
    ]


def _fmt_limit(n: int) -> str:
    """A context tier as a short label: 200000 -> 200K, 1000000 -> 1M.

    Only ever called with the round `CONTEXT_TIERS` values, so two branches
    cover it: whole millions render as `M`, everything else as `K`.
    """
    return f"{n // 1_000_000}M" if n % 1_000_000 == 0 else f"{n // 1_000}K"


def _fmt_duration(delta: timedelta) -> str:
    """A compact span: 47s, 5m, 2h18m, 1d03h."""
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    mins, _ = divmod(secs, 60)
    hours, mins = divmod(mins, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d{hours:02d}h"
    if hours:
        return f"{hours}h{mins:02d}m"
    return f"{mins}m"


def _fmt_timing(started: datetime | None, last: datetime | None) -> str:
    if started is None or last is None:
        return ""
    return f"started {started.strftime('%Y-%m-%d %H:%M UTC')} · {_fmt_duration(last - started)}"


def render_chat(report: ChatReport) -> str:
    """The `/tokens` view: window-now (with %), then per-model cumulative."""
    headers = ("", "input", "cache_w", "cache_r", "output", "total")
    rows = [_totals_row(usage.model, usage.totals) for usage in report.by_model]
    rows.append(_totals_row("TOTAL", report.total))

    pct = (
        round(report.window_now / report.context_limit * 100)
        if report.context_limit
        else 0
    )
    window_line = (
        f"  Context window now   {_c(report.window_now)} tokens   "
        f"(≈{pct}% of {_fmt_limit(report.context_limit)} · main thread · matches /context)"
    )

    header_line = (
        f"  session {report.session_id[:8]} · {_c(report.main_turns)} main turns"
    )
    if report.subagent_turns:
        header_line += f" (+{_c(report.subagent_turns)} subagent)"
    timing = _fmt_timing(report.started, report.last)
    if timing:
        header_line += f" · {timing}"

    sub_note = (
        f"  subagents: {report.subagent_count} transcript(s) · "
        f"{_c(report.subagent_turns)} turns · {_c(grand_total(report.subagents))} "
        "tokens (included above)"
        if report.subagent_count
        else "  subagents: none"
    )

    return "\n".join(
        [
            "",
            "Token usage - current chat",
            header_line,
            "",
            window_line,
            "",
            "  Session cumulative — by model (deduplicated; cache re-reads "
            "counted each turn)",
            _indent(_table(headers, rows), "  "),
            sub_note,
            "",
        ]
    )


def render_periods(
    buckets: Sequence[PeriodBucket], *, title: str, key_header: str
) -> str:
    """Daily or monthly table."""
    if not buckets:
        return f"{title}: no usage found.\n"
    headers = (key_header, "input", "cache_w", "cache_r", "output", "total", "turns")
    rows = [
        [
            bucket.key,
            _c(bucket.totals.input_tokens),
            _c(bucket.totals.cache_creation_tokens),
            _c(bucket.totals.cache_read_tokens),
            _c(bucket.totals.output_tokens),
            _c(grand_total(bucket.totals)),
            _c(bucket.turns),
        ]
        for bucket in buckets
    ]
    rows.append(_period_total_row(buckets))
    return f"\n{title} (UTC)\n\n{_table(headers, rows)}\n"


def _period_total_row(buckets: Sequence[PeriodBucket]) -> list[str]:
    inp = sum(b.totals.input_tokens for b in buckets)
    cw = sum(b.totals.cache_creation_tokens for b in buckets)
    cr = sum(b.totals.cache_read_tokens for b in buckets)
    out = sum(b.totals.output_tokens for b in buckets)
    turns = sum(b.turns for b in buckets)
    return [
        "TOTAL",
        _c(inp),
        _c(cw),
        _c(cr),
        _c(out),
        _c(inp + cw + cr + out),
        _c(turns),
    ]


def render_sessions(buckets: Sequence[SessionBucket]) -> str:
    """One row per session, newest activity first."""
    if not buckets:
        return "sessions: no usage found.\n"
    headers = ("session", "project", "last (UTC)", "total", "turns")
    rows = [
        [
            bucket.session_id[:8],
            _shorten(bucket.project, 28),
            bucket.last.strftime("%Y-%m-%d %H:%M"),
            _c(grand_total(bucket.totals)),
            _c(bucket.turns),
        ]
        for bucket in buckets
    ]
    return f"\nsessions ({len(buckets)})\n\n{_table(headers, rows)}\n"


def render_blocks(blocks: Sequence[Block]) -> str:
    """5-hour billing-style windows, oldest first; the live one is marked."""
    if not blocks:
        return "blocks: no usage found.\n"
    headers = ("window start (UTC)", "", "total", "turns")
    rows = [
        [
            block.start.strftime("%Y-%m-%d %H:%M"),
            "ACTIVE" if block.is_active else "",
            _c(grand_total(block.totals)),
            _c(block.turns),
        ]
        for block in blocks
    ]
    return f"\n5-hour blocks ({len(blocks)})\n\n{_table(headers, rows)}\n"


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else line for line in text.split("\n"))


def _shorten(text: str, width: int) -> str:
    return text if len(text) <= width else "…" + text[-(width - 1) :]
