"""Guarded replacement of small managed convention rules inside authored docs."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from .evolve_gate import EvolveError, safe_file

_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\Z")
_BLOCK = re.compile(
    r"<!-- dummyindex:rule (\{[^\n]+\}) -->\r?\n(.*?)\r?\n<!-- dummyindex:rule:end ([a-z0-9_.-]+) -->",
    re.S,
)
MAX_RULE_BYTES = 4000
MAX_RULES = 40


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def durable_evidence(context_dir: Path, citations: tuple[str, ...]) -> dict[str, str]:
    """Resolve provenance before rejecting disposable/cache aliases and hashing."""
    root = context_dir.parent.resolve()
    snapshots = {}
    for citation in citations:
        if not isinstance(citation, str) or not citation:
            raise EvolveError("evidence citations must be non-empty relative paths")
        match = re.search(r":L?\d+(?:-L?\d+)?$", citation)
        head = citation[: match.start()] if match else citation
        suffix = match[0] if match else ""
        path = safe_file(root, head)
        canonical = path.resolve().relative_to(root).as_posix()
        parts = tuple(part.casefold() for part in PurePosixPath(canonical).parts)
        if parts[0] in {"proposals", "audits"} or (
            len(parts) > 1
            and parts[0] == ".context"
            and parts[1] in {"cache", "proposals", "audits"}
        ):
            raise EvolveError(
                "provenance must use durable evidence, not disposable workspaces or cache"
            )
        snapshots[canonical + suffix] = sha256(safe_file(root, canonical).read_bytes())
    return snapshots


def rules_in(text: str) -> list[dict]:
    rules = []
    ids = set()
    for match in _BLOCK.finditer(text):
        try:
            meta = json.loads(match[1])
            if (
                not isinstance(meta, dict)
                or meta.get("id") != match[3]
                or match[3] in ids
            ):
                raise ValueError("duplicate or mismatched rule ID")
        except ValueError as exc:
            raise EvolveError(f"invalid managed convention rule: {exc}") from exc
        ids.add(match[3])
        rules.append(
            {**meta, "body": match[2], "start": match.start(), "end": match.end()}
        )
    if text.count("<!-- dummyindex:rule ") != len(rules):
        raise EvolveError(
            "malformed managed rule markers; preserve and repair document"
        )
    return rules


def plan_rule(
    context_dir: Path,
    *,
    target: str,
    rule_id: str,
    body: str,
    expected_sha256: str,
    sources: tuple[str, ...],
    evidence: tuple[str, ...],
    supersedes: tuple[str, ...] = (),
) -> dict:
    """Return an existing-pipeline candidate and exact bytes; do not adopt them.

    Superseded wording is removed, rather than left as another active lesson.
    The expected whole-document hash protects owner-authored material as well.
    """
    if not _ID.fullmatch(rule_id) or any(not _ID.fullmatch(i) for i in supersedes):
        raise EvolveError("rule IDs must use lowercase letters, digits, _, . or -")
    if (
        not target.startswith(".context/conventions/")
        or not target.endswith(".md")
        or target.endswith("/naming.md")
    ):
        raise EvolveError("living rules target an authored convention markdown file")
    path = safe_file(context_dir.parent, target)
    current = path.read_bytes()
    if sha256(current) != expected_sha256:
        raise EvolveError(
            "convention changed since review; reread before replacing a rule"
        )
    if (
        not body.strip()
        or len(body.encode()) > MAX_RULE_BYTES
        or "<!-- dummyindex:" in body
    ):
        raise EvolveError(
            f"rule must contain 1–{MAX_RULE_BYTES} bytes without managed markers"
        )
    if not sources or not evidence:
        raise EvolveError("a managed rule needs source files and accepted evidence")
    fingerprints = durable_evidence(context_dir, sources)
    evidence_hashes = durable_evidence(context_dir, evidence)
    text = current.decode("utf-8")
    old = rules_in(text)
    found = {r["id"] for r in old}
    if set(supersedes) - found:
        raise EvolveError("cannot supersede a rule absent from the reviewed document")
    if rule_id in supersedes:
        raise EvolveError(
            "a rule cannot supersede itself; replace it under the same ID"
        )
    if len(found - set(supersedes) | {rule_id}) > MAX_RULES:
        raise EvolveError(f"at most {MAX_RULES} active managed rules per document")
    meta = {
        "id": rule_id,
        "sources": fingerprints,
        "evidence": list(evidence_hashes),
        "evidence_sha256": evidence_hashes,
        "supersedes": list(supersedes),
    }
    block = (
        "<!-- dummyindex:rule "
        + json.dumps(meta, sort_keys=True, separators=(",", ":"))
        + " -->\n"
        + body.strip()
        + f"\n<!-- dummyindex:rule:end {rule_id} -->"
    )
    replaced = False
    for rule in reversed(old):
        if rule["id"] == rule_id:
            text = text[: rule["start"]] + block + text[rule["end"] :]
            replaced = True
        elif rule["id"] in supersedes:
            text = text[: rule["start"]] + text[rule["end"] :]
    if not replaced:
        text = text + ("\n" if text.endswith("\n") else "\n\n") + block + "\n"
    candidate = {
        "target_file": target,
        "diagnosis": f"Update managed rule {rule_id} from accepted evidence",
        "evidence": list(evidence_hashes),
        "change_sketch": f"Replace {rule_id}; supersede {', '.join(supersedes) or 'none'}",
        "prediction": f"Rule {rule_id} remains valid against its cited source contracts",
    }
    return {
        "candidate": candidate,
        "content": text,
        "rule_id": rule_id,
        "baseline_sha256": expected_sha256,
    }


def rule_status(context_dir: Path) -> list[dict]:
    """Source digests make staleness visible even after same-line-count edits."""
    rows = []
    directory = context_dir / "conventions"
    for path in sorted(directory.glob("*.md")):
        safe_file(context_dir.parent, path.relative_to(context_dir.parent).as_posix())
        for rule in rules_in(path.read_text(encoding="utf-8")):
            sources = rule.get("sources")
            stale = []
            if not isinstance(sources, dict) or not sources:
                stale.append("unknown source basis")
            else:
                for source, expected in sources.items():
                    try:
                        actual = sha256(
                            safe_file(context_dir.parent, source).read_bytes()
                        )
                    except (EvolveError, OSError):
                        actual = None
                    if actual != expected:
                        stale.append(source)
            rows.append(
                {
                    "id": rule["id"],
                    "target": path.relative_to(context_dir.parent).as_posix(),
                    "state": "stale" if stale else "current",
                    "changed_sources": stale,
                }
            )
    return rows
