"""Parse opencode session telemetry into comparable per-run metrics.

Two ingestion paths, one metric shape:

- **Stream** — ``opencode run --format json`` emits raw JSON events on
  stdout, line by line. :func:`metrics_from_stream` consumes those lines.
- **Export** — ``opencode export <sessionID>`` prints the whole session as
  JSON. :func:`metrics_from_export` consumes that document.

The exact event schema is treated as an implementation detail of the CLI:
both paths funnel into a tolerant recursive harvest that recognizes known
key shapes and never crashes on unknown ones. Assumptions that must be
re-validated against a real capture during the smoke stage (they are pinned
by unit fixtures here so any drift fails loudly):

- Token observations are **per-message totals**; multiple events may repeat
  or refine the same message's usage, so usage is deduped by message id
  (last observation wins). When no message id is available, the largest
  single observation is kept instead of summing (summing would double-count
  cumulative reporters).
- Cost, when reported, is cumulative for the run: max observation wins.
- Tool calls are counted by tool name across all tool-type parts.
- Assistant text parts are concatenated in arrival order as the response.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunMetrics:
    """Normalized telemetry for exactly one agent run."""

    session_id: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    tool_calls: dict[str, int] = field(default_factory=dict)
    response_text: str = ""
    event_count: int = 0

    @property
    def total_tool_calls(self) -> int:
        return sum(self.tool_calls.values())

    def to_row(self) -> dict[str, object]:
        """JSONL-safe row (no nested dicts beyond tool_calls, sorted)."""
        return {
            "session_id": self.session_id,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": self.cost_usd,
            "tool_calls": dict(sorted(self.tool_calls.items())),
            "total_tool_calls": self.total_tool_calls,
            "response_text": self.response_text,
            "event_count": self.event_count,
        }


def _iter_json_objects(lines: Iterable[str]) -> Iterator[object]:
    """Yield parsed JSON objects; blank/unparseable lines are skipped but
    counted by callers via event_count only when parseable."""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            yield json.loads(stripped)
        except json.JSONDecodeError:
            continue


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


class _Harvester:
    """Recursive walk collecting recognized telemetry keys."""

    def __init__(self) -> None:
        self.session_id: str | None = None
        self.model: str | None = None
        self.cost_usd: float = 0.0
        self.tool_counts: dict[str, int] = {}
        self.text_parts: list[str] = []
        # message-id -> (input, output, cache_read, cache_write)
        self.usage_by_msg: dict[str, tuple[int, int, int, int]] = {}
        # anonymous best single observation, used when ids are absent
        self.anon_usage: tuple[int, int, int, int] | None = None

    # -- token plumbing ----------------------------------------------------

    @staticmethod
    def _extract_usage(node: dict) -> tuple[int, int, int, int] | None:
        tokens = node.get("tokens")
        usage = node.get("usage") if not isinstance(tokens, dict) else tokens
        if not isinstance(usage, dict):
            return None
        inp = _as_int(usage.get("input"))
        out = _as_int(usage.get("output"))
        cache = usage.get("cache")
        c_read = c_write = 0
        if isinstance(cache, dict):
            c_read = _as_int(cache.get("read")) or 0
            c_write = _as_int(cache.get("write")) or 0
        else:
            c_read = _as_int(usage.get("cache_read")) or 0
            c_write = _as_int(usage.get("cache_write")) or 0
        if inp is None and out is None:
            return None
        return (
            inp or 0,
            out or 0,
            c_read,
            c_write,
        )

    def _record_usage(self, node: dict, usage: tuple[int, int, int, int]) -> None:
        msg_id = ""
        info = node.get("info")
        candidates = [node, info if isinstance(info, dict) else {}]
        for cand in candidates:
            raw = cand.get("id") or cand.get("messageID") or cand.get("messageId")
            if isinstance(raw, str) and raw:
                msg_id = raw
                break
        if msg_id:
            self.usage_by_msg[msg_id] = usage
        else:
            if self.anon_usage is None or sum(usage) > sum(self.anon_usage):
                self.anon_usage = usage

    # -- recursive walk ------------------------------------------------------

    def walk(self, node: object) -> None:
        if isinstance(node, dict):
            sid = node.get("sessionID")
            if isinstance(sid, str) and sid:
                self.session_id = sid
            model = node.get("modelID") or node.get("model")
            if isinstance(model, str) and model and self.model is None:
                self.model = model
            cost = node.get("cost") or node.get("totalCost")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                self.cost_usd = max(self.cost_usd, float(cost))
            part_type = node.get("type")
            if part_type == "text" and isinstance(node.get("text"), str):
                self.text_parts.append(node["text"])
            elif part_type in ("tool", "tool-use", "tool_use"):
                # Real streams wrap tool calls: {"type":"tool_use",
                # "part":{"type":"tool","tool":"grep",...}}. Count only
                # nodes that actually carry a tool name — counting the
                # unnamed wrapper too would double-report every call.
                name = node.get("tool") or node.get("toolName") or node.get("tool_name")
                if isinstance(name, str) and name:
                    self.tool_counts[name] = self.tool_counts.get(name, 0) + 1
            usage = self._extract_usage(node)
            if usage is not None:
                self._record_usage(node, usage)
            for child in node.values():
                self.walk(child)
        elif isinstance(node, list):
            for child in node:
                self.walk(child)

    # -- finalize -------------------------------------------------------------

    def finalize(self, event_count: int) -> RunMetrics:
        if self.usage_by_msg:
            inputs = [u[0] for u in self.usage_by_msg.values()]
            outputs = [u[1] for u in self.usage_by_msg.values()]
            reads = [u[2] for u in self.usage_by_msg.values()]
            writes = [u[3] for u in self.usage_by_msg.values()]
            inp, out, cr, cw = (
                sum(inputs),
                sum(outputs),
                sum(reads),
                sum(writes),
            )
        else:
            inp, out, cr, cw = self.anon_usage or (0, 0, 0, 0)
        return RunMetrics(
            session_id=self.session_id,
            model=self.model,
            input_tokens=inp,
            output_tokens=out,
            cache_read_tokens=cr,
            cache_write_tokens=cw,
            cost_usd=self.cost_usd,
            tool_calls=dict(self.tool_counts),
            response_text="".join(self.text_parts),
            event_count=event_count,
        )


def metrics_from_stream(lines: Iterable[str]) -> RunMetrics:
    """Parse ``opencode run --format json`` stdout lines into metrics."""
    harvester = _Harvester()
    count = 0
    for obj in _iter_json_objects(lines):
        count += 1
        harvester.walk(obj)
    return harvester.finalize(event_count=count)


def metrics_from_export(export: object) -> RunMetrics:
    """Parse an ``opencode export <sessionID>`` JSON document."""
    harvester = _Harvester()
    if isinstance(export, str):
        try:
            export = json.loads(export)
        except json.JSONDecodeError as exc:
            raise TelemetryError(f"export is not valid JSON: {exc}") from exc
    harvester.walk(export)
    return harvester.finalize(event_count=1)


class TelemetryError(Exception):
    """Raised when telemetry cannot be extracted at all."""
