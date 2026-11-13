"""Statistical naming-convention inference for .context/conventions/.

Pure Python. Count casing styles per (language, kind) and emit a rule when the
dominant style hits the confidence threshold. No LLM in v0.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dummyindex.context.build.maps import FilesMap, SymbolsMap

SCHEMA_VERSION = 1

_MIN_CONFIDENCE = 0.80

# Convention docs authored by council subagents, not Python; the `/dummyindex` skill
# reads each description when prompting the agent. `naming` is absent on purpose: it
# is statistical (`analyze_naming`) and written deterministically.
CONVENTION_SECTIONS: dict[str, str] = {
    "folder-organization": (
        "How source is grouped into directories (by feature, by layer, by "
        "domain) and the rule a new file should follow when it's added."
    ),
    "coding-practices": (
        "Idiomatic patterns the project relies on — dependency injection "
        "style, error-handling discipline, sync vs async boundaries, "
        "validation surfaces, dataclass/Pydantic/Protocol use."
    ),
    "testing": (
        "Test framework, fixture style, mocking philosophy, what's unit vs "
        "integration vs e2e, coverage expectations, common anti-patterns."
    ),
    "data-access": (
        "Database access patterns — ORM vs raw, transaction handling, "
        "migration approach, query placement (repo vs service), index "
        "hygiene, common pitfalls."
    ),
}


class ConventionSectionError(ValueError):
    """Raised when `write_convention_section` can't safely place a section."""


@dataclass(frozen=True)
class NamingRule:
    language: str
    kind: str
    casing: str
    evidence_count: int
    total_observed: int
    confidence: float
    exceptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class NamingRules:
    schema_version: int
    rules: tuple[NamingRule, ...]


def classify_casing(name: str) -> str:
    """Bucket a single identifier into a casing style.

    Returns one of: PascalCase | camelCase | snake_case | SCREAMING_SNAKE |
    kebab-case | lowercase | mixed | unknown.
    """
    if not name:
        return "unknown"
    stripped = name.lstrip("_")
    if not stripped:
        return "lowercase"
    if "-" in stripped:
        return "kebab-case"
    if "_" in stripped:
        if stripped.isupper():
            return "SCREAMING_SNAKE"
        if stripped.islower():
            return "snake_case"
        return "mixed"
    if stripped.isupper() and len(stripped) > 1:
        return "SCREAMING_SNAKE"
    first = stripped[0]
    if first.isupper():
        return "PascalCase"
    if first.islower():
        return "camelCase" if any(c.isupper() for c in stripped) else "lowercase"
    return "mixed"


def analyze_naming(files_map: FilesMap, symbols_map: SymbolsMap) -> NamingRules:
    """Group symbols + file stems by (language, kind) and derive rules."""
    lang_by_path = {f.path: f.language for f in files_map.files}
    groups: dict[tuple[str, str], list[str]] = {}

    for sym in symbols_map.symbols:
        # Dunders don't reflect a project-level casing choice — skip.
        if sym.name.startswith("__") and sym.name.endswith("__"):
            continue
        language = lang_by_path.get(sym.path) or "unknown"
        groups.setdefault((language, sym.kind), []).append(sym.name)

    for f in files_map.files:
        if not f.language:
            continue
        stem = Path(f.path).stem
        groups.setdefault((f.language, "file"), []).append(stem)

    rules: list[NamingRule] = []
    for (language, kind), names in sorted(groups.items()):
        rule = _rule_from_names(language, kind, names)
        if rule is not None:
            rules.append(rule)
    return NamingRules(schema_version=SCHEMA_VERSION, rules=tuple(rules))


def _rule_from_names(language: str, kind: str, names: list[str]) -> NamingRule | None:
    if not names:
        return None
    counter = Counter(classify_casing(n) for n in names)
    total = len(names)
    most_common, count = counter.most_common(1)[0]
    confidence = count / total

    if total >= 2 and confidence < _MIN_CONFIDENCE:
        return None

    exceptions = tuple(sorted({n for n in names if classify_casing(n) != most_common}))
    return NamingRule(
        language=language,
        kind=kind,
        casing=most_common,
        evidence_count=count,
        total_observed=total,
        confidence=round(confidence, 4),
        exceptions=exceptions,
    )


# --- Writers


def write_naming_json(path: Path, rules: NamingRules) -> None:
    _atomic_write_json(
        path,
        {
            "schema_version": rules.schema_version,
            "rules": [_rule_to_json(r) for r in rules.rules],
        },
    )


def write_naming_md(
    path: Path,
    rules: NamingRules,
    *,
    generated_at: str | None = None,
) -> None:
    lines: list[str] = ["# Naming conventions (derived)", ""]
    if generated_at:
        lines.extend([f"_Generated {generated_at}_", ""])
    if not rules.rules:
        lines.append(
            "No conventions inferred. The codebase may be too small or too "
            "inconsistent for statistical inference."
        )
    else:
        by_lang: dict[str, list[NamingRule]] = {}
        for r in rules.rules:
            by_lang.setdefault(r.language, []).append(r)
        for language in sorted(by_lang):
            lines.append(f"## {language}")
            lines.append("")
            for r in by_lang[language]:
                pct = int(round(r.confidence * 100))
                exc = (
                    f" — {len(r.exceptions)} exceptions. See [naming.json](naming.json)"
                    if r.exceptions
                    else ""
                )
                lines.append(
                    f"- **{r.kind}** → `{r.casing}` "
                    f"({r.evidence_count}/{r.total_observed}, {pct}%){exc}"
                )
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def write_convention_section(
    context_dir: Path,
    *,
    section: str,
    source_file: Path,
) -> Path:
    """Atomically place agent-authored markdown at ``<context_dir>/conventions/<section>.md``.

    The `/dummyindex` skill calls this after a council subagent writes a
    folder-organization / coding-practices / testing / data-access doc. Raises
    :class:`ConventionSectionError` for a section outside `CONVENTION_SECTIONS` (naming.md
    has its own writer, `write_naming_md`) or a missing ``source_file``.
    """
    if section not in CONVENTION_SECTIONS:
        valid = ", ".join(sorted(CONVENTION_SECTIONS))
        raise ConventionSectionError(
            f"unknown convention section {section!r}; valid: {valid}"
        )
    if not source_file.exists():
        raise ConventionSectionError(f"source file not found: {source_file}")

    target = context_dir / "conventions" / f"{section}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    content = source_file.read_text(encoding="utf-8")
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)
    return target


def _rule_to_json(r: NamingRule) -> dict[str, Any]:
    return {
        "language": r.language,
        "kind": r.kind,
        "casing": r.casing,
        "evidence_count": r.evidence_count,
        "total_observed": r.total_observed,
        "confidence": r.confidence,
        "exceptions": list(r.exceptions),
    }


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
