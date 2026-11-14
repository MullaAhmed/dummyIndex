"""Read, render and line-edit ``.context/config.toml``.

Writes edit only the lines they change, so hand-written comments survive.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

from dummyindex.shared.atomic_io import write_text_atomic

from ....versioning import parse_version
from .constants import SCHEMA_VERSION
from .enums import SkillOrigin
from .errors import RequirementsError
from .models import PluginRequirement, Requirements, SkillRequirement

_BOM = "\ufeff"
_HEADER_COMMENT = "# Required setup for every dev on this repo. Extras are allowed."
_CONSTRAINT = re.compile(r"^(?:>=|==)(?P<ver>.+)$")
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_TABLE_HEADER = re.compile(r"^\s*\[")
_VERSION_KEY = re.compile(r"^\s*version\s*=")
_VERSION_LINE = re.compile(
    r'^(?P<pre>\s*version\s*=\s*)"[^"\r\n]*"(?P<post>[ \t]*(?:#[^\r\n]*)?)(?P<eol>\r?\n)?$'
)
_KNOWN_TOP = frozenset(
    {"schema_version", "dummyindex", "plugins", "skills", "equipment"}
)
_KNOWN_DI = frozenset({"min_version"})
_KNOWN_PLUGIN = frozenset({"id", "version"})
_KNOWN_SKILL = frozenset({"name", "from"})
_KNOWN_EQUIP = frozenset({"require_native_adapters"})


def _toml_loads(text: str) -> dict[str, Any]:
    # Looked up per call so tests can block tomllib and reach the tomli branch.
    try:
        import tomllib
    except ImportError:  # Python 3.10
        import tomli as tomllib
    return tomllib.loads(text)


def is_valid_constraint(value: object) -> bool:
    """``>=X`` or ``==X`` with ``X`` a parseable version. ``~=`` is invalid."""
    if not isinstance(value, str):
        return False
    match = _CONSTRAINT.match(value)
    return match is not None and parse_version(match.group("ver")) is not None


def parse_skill_from(value: object) -> tuple[SkillOrigin, str | None]:
    """Split a ``from`` value into its origin and, for plugins, the plugin id."""
    if value in ("dummyindex", "project"):
        return SkillOrigin(value), None
    if isinstance(value, str) and value.startswith("plugin:") and len(value) > 7:
        return SkillOrigin.PLUGIN, value[7:]
    raise RequirementsError(
        f"skill from must be dummyindex, plugin:<id> or project, got {value!r}"
    )


def _extra(raw: dict[str, Any], known: frozenset[str]) -> tuple[tuple[str, Any], ...]:
    return tuple((k, v) for k, v in raw.items() if k not in known)


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise RequirementsError(f"[{key}] must be a table")
    return value


def _entries(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(e, dict) for e in value):
        raise RequirementsError(f"[[{key}]] must be an array of tables")
    return value


def parse_requirements_text(text: str, *, source: str = "config.toml") -> Requirements:
    """Parse and validate ``config.toml`` text. The BOM must already be removed."""
    try:
        data = _toml_loads(text)
    except ValueError as exc:
        raise RequirementsError(f"{source}: invalid TOML: {exc}") from exc
    schema = data.get("schema_version", SCHEMA_VERSION)
    if type(schema) is not int or schema < 1:
        raise RequirementsError("schema_version must be a positive integer")
    if schema > SCHEMA_VERSION:
        raise RequirementsError(
            f"schema_version {schema} is newer than supported {SCHEMA_VERSION}"
        )
    di = _table(data, "dummyindex")
    min_version = di.get("min_version")
    if min_version is not None and (
        not isinstance(min_version, str) or parse_version(min_version) is None
    ):
        raise RequirementsError(f"min_version {min_version!r} is not a version")
    plugins: list[PluginRequirement] = []
    seen_ids: set[str] = set()
    for raw in _entries(data, "plugins"):
        pid = raw.get("id")
        if not isinstance(pid, str) or not pid:
            raise RequirementsError("[[plugins]] entry needs a non-empty id")
        if pid in seen_ids:
            raise RequirementsError(f"duplicate plugin id: {pid}")
        seen_ids.add(pid)
        version = raw.get("version")
        if version is not None and not is_valid_constraint(version):
            raise RequirementsError(f"plugin {pid}: bad version constraint {version!r}")
        plugins.append(
            PluginRequirement(id=pid, version=version, extra=_extra(raw, _KNOWN_PLUGIN))
        )
    skills: list[SkillRequirement] = []
    seen_names: set[str] = set()
    for raw in _entries(data, "skills"):
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise RequirementsError("[[skills]] entry needs a non-empty name")
        if name in seen_names:
            raise RequirementsError(f"duplicate skill name: {name}")
        seen_names.add(name)
        origin = raw.get("from", "dummyindex")
        parse_skill_from(origin)
        skills.append(
            SkillRequirement(name=name, from_=origin, extra=_extra(raw, _KNOWN_SKILL))
        )
    equip = _table(data, "equipment")
    native = equip.get("require_native_adapters", False)
    if not isinstance(native, bool):
        raise RequirementsError("require_native_adapters must be true or false")
    return Requirements(
        schema_version=schema,
        min_version=min_version,
        plugins=tuple(plugins),
        skills=tuple(skills),
        require_native_adapters=native,
        extra=_extra(data, _KNOWN_TOP),
        dummyindex_extra=_extra(di, _KNOWN_DI),
        equipment_extra=_extra(equip, _KNOWN_EQUIP),
    )


def _decode(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RequirementsError(f"{path}: cannot read: {exc}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RequirementsError(f"{path}: not valid UTF-8") from exc


def read_requirements(path: Path) -> Requirements | None:
    """Return the parsed file, or ``None`` when it does not exist."""
    if not path.exists():
        return None
    text = _decode(path)
    return parse_requirements_text(
        text[1:] if text.startswith(_BOM) else text, source=str(path)
    )


def _str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _key(key: str) -> str:
    return key if _BARE_KEY.fullmatch(key) else _str(key)


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _str(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = ", ".join(f"{_key(k)} = {_value(v)}" for k, v in value.items())
        return "{ " + inner + " }"
    raise RequirementsError(f"cannot render value of type {type(value).__name__}")


def _kv_lines(extra: tuple[tuple[str, Any], ...]) -> list[str]:
    return [f"{_key(k)} = {_value(v)}" for k, v in extra]


def _plugin_block(p: PluginRequirement) -> list[str]:
    lines = ["[[plugins]]", f"id = {_str(p.id)}"]
    if p.version is not None:
        lines.append(f"version = {_str(p.version)}")
    return lines + _kv_lines(p.extra)


def _skill_block(s: SkillRequirement) -> list[str]:
    head = ["[[skills]]", f"name = {_str(s.name)}", f"from = {_str(s.from_)}"]
    return head + _kv_lines(s.extra)


def render_requirements(req: Requirements) -> str:
    """Deterministic full rendering; ``parse(render(r)) == r``."""
    out = [_HEADER_COMMENT, f"schema_version = {req.schema_version}"]
    out += _kv_lines(req.extra)
    out += ["", "[dummyindex]"]
    if req.min_version is not None:
        out.append(f"min_version = {_str(req.min_version)}")
    out += _kv_lines(req.dummyindex_extra)
    for plugin in req.plugins:
        out += [""] + _plugin_block(plugin)
    for skill in req.skills:
        out += [""] + _skill_block(skill)
    out += [
        "",
        "[equipment]",
        f"require_native_adapters = {_value(req.require_native_adapters)}",
    ]
    out += _kv_lines(req.equipment_extra)
    return "\n".join(out) + "\n"


# --- line-level editing -----------------------------------------------------


def _split_lines(text: str) -> list[str]:
    return re.findall(r"[^\n]*\n|[^\n]+$", text)


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _ensure_eol(lines: list[str], nl: str) -> list[str]:
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += nl
    return lines


def _header_key(line: str) -> str:
    return line.split("#", 1)[0].strip()


def _spans(lines: list[str], header: str) -> list[tuple[int, int]]:
    """``[start, end)`` of each block whose header line is ``header``."""
    spans = []
    for i, line in enumerate(lines):
        if _header_key(line) == header:
            end = next(
                (j for j in range(i + 1, len(lines)) if _TABLE_HEADER.match(lines[j])),
                len(lines),
            )
            spans.append((i, end))
    return spans


def _block_ident(block: list[str], table: str, field: str) -> Any:
    try:
        data = _toml_loads("".join(block))
    except ValueError as exc:
        raise RequirementsError(f"cannot parse [[{table}]] block: {exc}") from exc
    entries = data.get(table, [])
    if len(entries) != 1:
        raise RequirementsError(f"cannot identify [[{table}]] block")
    return entries[0].get(field)


def _join(bom: bool, lines: list[str]) -> str:
    return (_BOM if bom else "") + "".join(lines)


def set_min_version_line(text: str, version: str | None) -> str:
    """Set or remove ``min_version`` in ``[dummyindex]``; other bytes stay put."""
    literal = None if version is None else _str(version)
    return _set_table_key(text, "dummyindex", "min_version", literal)


def _set_table_key(text: str, table: str, key: str, literal: str | None) -> str:
    bom = text.startswith(_BOM)
    body = text[1:] if bom else text
    nl = _newline(body)
    lines = _split_lines(body)
    key_re = re.compile(
        rf"^(?P<pre>\s*{key}\s*=\s*)[^#\r\n]*?(?P<post>[ \t]*(?:#[^\r\n]*)?)(?P<eol>\r?\n)?$"
    )
    spans = _spans(lines, f"[{table}]")
    if spans:
        start, end = spans[0]
        for k in range(start + 1, end):
            match = key_re.match(lines[k])
            if match:
                if literal is None:
                    del lines[k]
                else:
                    eol = match.group("eol") or ""
                    lines[k] = match.group("pre") + literal + match.group("post") + eol
                return _join(bom, lines)
        if literal is None:
            return text
        _ensure_eol(lines, nl)
        lines.insert(start + 1, f"{key} = {literal}{nl}")
        return _join(bom, lines)
    if literal is None:
        return text
    _ensure_eol(lines, nl)
    lines += [nl, f"[{table}]{nl}", f"{key} = {literal}{nl}"]
    return _join(bom, lines)


def _delete_blocks(text: str, table: str, field: str, idents: set[str]) -> str:
    bom = text.startswith(_BOM)
    lines = _split_lines(text[1:] if bom else text)
    for start, end in reversed(_spans(lines, f"[[{table}]]")):
        if _block_ident(lines[start:end], table, field) not in idents:
            continue
        # Keep comments and blank lines that sit above the next block.
        while end > start + 1 and _is_blank_or_comment(lines[end - 1]):
            end -= 1
        del lines[start:end]
    return _join(bom, lines)


def _is_blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped == "" or stripped.startswith("#")


def _edit_block_version(text: str, ident: str, version: str | None) -> str:
    bom = text.startswith(_BOM)
    body = text[1:] if bom else text
    nl = _newline(body)
    lines = _split_lines(body)
    for start, end in _spans(lines, "[[plugins]]"):
        if _block_ident(lines[start:end], "plugins", "id") != ident:
            continue
        for k in range(start + 1, end):
            if not _VERSION_KEY.match(lines[k]):
                continue
            match = _VERSION_LINE.match(lines[k])
            if match is None:
                raise RequirementsError(f"cannot edit version line of plugin {ident}")
            if version is None:
                del lines[k]
            else:
                eol = match.group("eol") or ""
                lines[k] = (
                    match.group("pre") + _str(version) + match.group("post") + eol
                )
            return _join(bom, lines)
        if version is not None:
            _ensure_eol(lines, nl)
            lines.insert(start + 1, f"version = {_str(version)}{nl}")
        return _join(bom, lines)
    raise RequirementsError(f"plugin {ident} not found in file")


def _append_blocks(text: str, blocks: list[list[str]]) -> str:
    bom = text.startswith(_BOM)
    body = text[1:] if bom else text
    nl = _newline(body)
    lines = _ensure_eol(_split_lines(body), nl)
    for block in blocks:
        if lines:
            lines.append(nl)
        lines += [line + nl for line in block]
    return _join(bom, lines)


def _apply_changes(text: str, cur: Requirements, new: Requirements) -> str:
    if cur.schema_version != new.schema_version:
        raise RequirementsError("schema_version cannot change in place")
    if (cur.extra, cur.dummyindex_extra, cur.equipment_extra) != (
        new.extra,
        new.dummyindex_extra,
        new.equipment_extra,
    ):
        raise RequirementsError("unknown-key changes cannot be applied in place")
    if cur.min_version != new.min_version:
        text = set_min_version_line(text, new.min_version)
    if cur.require_native_adapters != new.require_native_adapters:
        text = _set_table_key(
            text,
            "equipment",
            "require_native_adapters",
            _value(new.require_native_adapters),
        )
    cur_plugins = {p.id: p for p in cur.plugins}
    new_plugins = {p.id: p for p in new.plugins}
    for pid, old in cur_plugins.items():
        if pid not in new_plugins:
            continue
        if old.extra != new_plugins[pid].extra:
            raise RequirementsError(f"plugin {pid}: extra keys cannot change in place")
        if old.version != new_plugins[pid].version:
            text = _edit_block_version(text, pid, new_plugins[pid].version)
    removed = {pid for pid in cur_plugins if pid not in new_plugins}
    if removed:
        text = _delete_blocks(text, "plugins", "id", removed)
    added = [p for pid, p in new_plugins.items() if pid not in cur_plugins]
    if added:
        text = _append_blocks(text, [_plugin_block(p) for p in added])
    cur_skills = {s.name: s for s in cur.skills}
    new_skills = {s.name: s for s in new.skills}
    for name, old in cur_skills.items():
        if name in new_skills and (
            old.from_ != new_skills[name].from_ or old.extra != new_skills[name].extra
        ):
            raise RequirementsError(f"skill {name}: from/extra cannot change in place")
    removed_skills = {name for name in cur_skills if name not in new_skills}
    if removed_skills:
        text = _delete_blocks(text, "skills", "name", removed_skills)
    added_skills = [s for name, s in new_skills.items() if name not in cur_skills]
    if added_skills:
        text = _append_blocks(text, [_skill_block(s) for s in added_skills])
    return text


def write_requirements(path: Path, req: Requirements) -> None:
    """Create the file in full, or edit the existing one line by line."""
    text = _decode(path) if path.exists() else ""
    body = text[1:] if text.startswith(_BOM) else text
    if not body.strip():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, render_requirements(req))
        return
    current = parse_requirements_text(body, source=str(path))
    edited = _apply_changes(text, current, req)
    # Refuse to write unless the edited text really yields the requested state.
    actual = parse_requirements_text(
        edited[1:] if edited.startswith(_BOM) else edited, source=str(path)
    )
    if not _same_state(actual, req):
        raise RequirementsError(
            "in-place edit would not yield the requested state; nothing written"
        )
    write_text_atomic(path, edited)


def _same_state(actual: Requirements, want: Requirements) -> bool:
    return (
        actual.schema_version == want.schema_version
        and actual.min_version == want.min_version
        and actual.require_native_adapters == want.require_native_adapters
        and {p.id: p for p in actual.plugins} == {p.id: p for p in want.plugins}
        and {s.name: s for s in actual.skills} == {s.name: s for s in want.skills}
    )
