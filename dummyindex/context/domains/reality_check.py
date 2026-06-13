"""Post-synthesis reality checker.

After the chairman writes a feature's canonical docs (spec.md, plan.md,
concerns.md), this module re-reads the line-checkable ones and verifies
each *concrete claim* against the AST extraction + the symbol graph +
actual source files. ``spec.md`` is intent-level (what the feature does)
and is deliberately NOT line-checked; ``plan.md`` + ``concerns.md`` carry
the concrete grounding claims. The legacy essay docs (``architecture.md``,
``implementation.md``, ``data-model.md``, ``security.md``, ``product.md``)
are also still scanned during the v0.14 transition window, so a pre-reshape
``.context/`` keeps getting checked until it's re-councilled.

What counts as a claim:

- **Calls.**  `` `X` calls `Y` `` / `` `X.foo()` calls `Y.bar()` `` —
  check that the call relation actually exists in
  ``features/symbol-graph.json``.
- **File:line.**  `` `path/to/file.py:42` `` or
  ``"on line 42 of file.py"`` — check the file exists and has ≥ N lines.
- **Symbol existence.**  Bare-name claims like
  `` `Calculator.add` `` resolved against ``map/symbols.json``.

What we deliberately don't try to verify:

- Semantic / behavioral claims (``X is faster than Y``, ``Z is
  thread-safe``). The reality checker is a fact-check on grounding, not
  on judgment.
- Claims that aren't structured (free prose without an extractable
  subject/object).
- References rooted *outside* the repo (``os.environ.setdefault``,
  ``requests.get``): absence from ``map/symbols.json`` is not proof of
  falsehood, so these are reported ``ambiguous``, never ``contradicted``.

File:line citations resolve in this order: exact ``map/files.json`` entry →
the literal path on disk under the repo root (manifests/docs the index
doesn't track) → the feature's own docs (``spec.md:12`` cited from
``concerns.md``) → basename match over the index, disambiguated against the
feature's own ``files`` list. A basename that matches several files with no
unique feature-scoped hit is ``ambiguous`` (fully qualify the citation),
never an arbitrary pick.

Output is a JSON report at ``features/<id>/_reality-check.json`` plus a
human summary at ``features/<id>/_reality-check.md``. Claims with status
``contradicted`` flip the feature's ``confidence`` to ``AMBIGUOUS`` (the
prior value is stashed as ``confidence_demoted_from``) — the council can
re-run with the report in hand to fix them, and a clean re-run restores
the stashed confidence via :func:`promote_feature_on_clean`.
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dummyindex.context.domains.dev_pick import read_feature_files

SCHEMA_VERSION = 1

# Sections we re-read. Order matters only for stable output ordering.
_CANONICAL_DOCS: tuple[str, ...] = (
    "plan.md",
    "concerns.md",
    "architecture.md",
    "implementation.md",
    "data-model.md",
    "security.md",
    "product.md",
)

# Claim patterns. Each yields a dict of named groups via re.finditer.
_CALL_RE = re.compile(
    r"`([A-Za-z_][\w.]*)(?:\(\))?`\s+calls?\s+`([A-Za-z_][\w.]*)(?:\(\))?`",
    re.IGNORECASE,
)
_USES_RE = re.compile(
    r"`([A-Za-z_][\w.]*)(?:\(\))?`\s+uses\s+`([A-Za-z_][\w.]*)(?:\(\))?`",
    re.IGNORECASE,
)
_FILE_LINE_RE = re.compile(
    r"`([\w./\-]+\.[A-Za-z0-9]{1,6}):(\d+)`"
)
_HAS_METHOD_RE = re.compile(
    r"(?:class\s+)?`([A-Za-z_][\w]*)`\s+has\s+(?:a\s+)?(?:method|function)\s+`([A-Za-z_][\w]*)(?:\(\))?`",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Claim:
    text: str
    source_file: str               # which canonical doc the claim came from
    kind: str                      # calls / uses / file:line / has_method
    subject: str
    object: str                    # for file:line claims, this is the line number as a string
    status: str                    # verified / contradicted / ambiguous
    reason: Optional[str] = None   # human-readable note when not verified

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source_file": self.source_file,
            "kind": self.kind,
            "subject": self.subject,
            "object": self.object,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RealityReport:
    schema_version: int
    feature_id: str
    claims_total: int
    verified: int
    contradicted: int
    ambiguous: int
    claims: tuple[Claim, ...]

    @property
    def has_contradictions(self) -> bool:
        return self.contradicted > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "feature_id": self.feature_id,
            "claims_total": self.claims_total,
            "verified": self.verified,
            "contradicted": self.contradicted,
            "ambiguous": self.ambiguous,
            "claims": [c.to_dict() for c in self.claims],
        }


def reality_check_feature(
    context_dir: Path,
    feature_id: str,
) -> RealityReport:
    """Read a feature's canonical docs, extract claims, verify against AST.

    Raises ``FileNotFoundError`` if the feature folder doesn't exist.
    """
    context_dir = context_dir.resolve()
    feat_dir = context_dir / "features" / feature_id
    if not feat_dir.is_dir():
        raise FileNotFoundError(feat_dir)

    symbol_names, symbol_paths = _load_symbols(context_dir)
    call_edges = _load_call_edges(context_dir, symbol_names)
    file_paths = _load_file_paths(context_dir)
    feature_files = _load_feature_files(context_dir, feature_id)
    repo_modules = _repo_module_names(file_paths)

    claims: list[Claim] = []
    for doc_name in _CANONICAL_DOCS:
        path = feat_dir / doc_name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        claims.extend(_extract_claims(text, doc_name))

    verified_claims: list[Claim] = []
    for c in claims:
        verified_claims.append(
            _verify_claim(
                c,
                symbol_names=symbol_names,
                symbol_paths=symbol_paths,
                call_edges=call_edges,
                file_paths=file_paths,
                feature_files=feature_files,
                repo_modules=repo_modules,
                feat_dir=feat_dir,
                repo_root=Path(_repo_root_from_meta(context_dir) or context_dir.parent),
            )
        )

    return _summarize(feature_id, verified_claims)


def _extract_claims(text: str, source_file: str) -> list[Claim]:
    """Pull every regex-matchable claim from ``text``."""
    out: list[Claim] = []
    seen: set[tuple[str, str, str]] = set()

    def _push(kind: str, subject: str, obj: str, raw: str) -> None:
        key = (kind, subject.lower(), obj.lower())
        if key in seen:
            return
        seen.add(key)
        out.append(Claim(
            text=raw.strip(),
            source_file=source_file,
            kind=kind,
            subject=subject,
            object=obj,
            status="ambiguous",
            reason=None,
        ))

    for m in _CALL_RE.finditer(text):
        _push("calls", m.group(1), m.group(2), m.group(0))
    for m in _USES_RE.finditer(text):
        _push("uses", m.group(1), m.group(2), m.group(0))
    for m in _HAS_METHOD_RE.finditer(text):
        _push("has_method", m.group(1), m.group(2), m.group(0))
    for m in _FILE_LINE_RE.finditer(text):
        _push("file:line", m.group(1), m.group(2), m.group(0))

    return out


def _verify_claim(
    claim: Claim,
    *,
    symbol_names: frozenset[str],
    symbol_paths: dict[str, str],
    call_edges: frozenset[tuple[str, str]],
    file_paths: frozenset[str],
    feature_files: frozenset[str],
    repo_modules: frozenset[str],
    feat_dir: Path,
    repo_root: Path,
) -> Claim:
    """Replace the placeholder ``status`` on ``claim`` based on AST evidence."""
    if claim.kind in ("calls", "uses"):
        subj = _bare_name(claim.subject)
        obj = _bare_name(claim.object)
        # Subject + object must both exist as symbols. A token rooted outside
        # the repo (stdlib / third-party / attribute chain on an import) is
        # merely unverifiable — never proof of falsehood.
        for raw, bare, label in (
            (claim.subject, subj, "subject"),
            (claim.object, obj, "object"),
        ):
            if bare in symbol_names:
                continue
            if _is_external_reference(
                raw, symbol_names=symbol_names, repo_modules=repo_modules
            ):
                return _with_status(
                    claim, "ambiguous",
                    f"symbol {label} `{raw}` not in repo map — external/stdlib "
                    f"reference or alias; not verifiable",
                )
            return _with_status(
                claim, "contradicted",
                f"symbol {label} not found in map/symbols.json",
            )
        if (subj, obj) in call_edges:
            return _with_status(claim, "verified", None)
        # Symbols exist but no call edge — could be indirect; ambiguous.
        return _with_status(
            claim, "ambiguous",
            "both symbols exist but no direct call edge in symbol-graph"
        )

    if claim.kind == "has_method":
        method = _bare_name(claim.object)
        cls = _bare_name(claim.subject)
        if method in symbol_names and cls in symbol_names:
            return _with_status(claim, "verified", None)
        return _with_status(
            claim, "contradicted",
            f"{'method' if method not in symbol_names else 'class'} not in symbols"
        )

    if claim.kind == "file:line":
        path_str = claim.subject
        try:
            line_n = int(claim.object)
        except ValueError:
            return _with_status(claim, "contradicted", "line number not an int")
        resolved = _resolve_cited_path(
            path_str,
            file_paths=file_paths,
            feature_files=feature_files,
            feat_dir=feat_dir,
            repo_root=repo_root,
        )
        if isinstance(resolved, tuple):
            status, reason = resolved
            return _with_status(claim, status, reason)
        if not resolved.is_file():
            return _with_status(claim, "contradicted", "file not found on disk")
        try:
            line_count = sum(1 for _ in resolved.open("rb"))
        except OSError:
            return _with_status(claim, "ambiguous", "could not read file")
        if line_n < 1 or line_n > line_count:
            return _with_status(
                claim, "contradicted",
                f"file has {line_count} line(s), claim cites line {line_n}"
            )
        return _with_status(claim, "verified", None)

    return claim


def _resolve_cited_path(
    path_str: str,
    *,
    file_paths: frozenset[str],
    feature_files: frozenset[str],
    feat_dir: Path,
    repo_root: Path,
) -> Path | tuple[str, str]:
    """Resolve a cited path to a concrete file, or a (status, reason) verdict.

    Precedence (deterministic — never indexes an unsorted collection):

    1. Exact ``map/files.json`` entry.
    2. The literal path on disk under the repo root — manifests and docs the
       code index doesn't track (``package.json``, ``docs/spec.md``) are
       legitimate citation targets; the claim is about the file.
    3. A bare name among the feature's own docs (``spec.md:12`` cited from
       ``concerns.md``).
    4. Basename match over ``map/files.json``: a unique match resolves; with
       several matches, a *unique* hit among the feature's own ``files``
       resolves; otherwise the claim is ambiguous (fully qualify the path).
    """
    if path_str in file_paths:
        return repo_root / path_str
    on_disk = repo_root / path_str
    if on_disk.is_file():
        return on_disk
    if "/" not in path_str and (feat_dir / path_str).is_file():
        return feat_dir / path_str
    base = path_str.rsplit("/", 1)[-1]
    candidates = sorted(
        fp for fp in file_paths if fp.endswith("/" + base) or fp == base
    )
    if not candidates:
        return ("contradicted", "file not found in map/files.json or on disk")
    if len(candidates) == 1:
        return repo_root / candidates[0]
    scoped = sorted(set(candidates) & feature_files)
    if len(scoped) == 1:
        return repo_root / scoped[0]
    shown = ", ".join(candidates[:5]) + (", …" if len(candidates) > 5 else "")
    return (
        "ambiguous",
        f"basename matches {len(candidates)} files ({shown}) — "
        f"fully qualify the citation",
    )


def _is_external_reference(
    token: str, *, symbol_names: frozenset[str], repo_modules: frozenset[str]
) -> bool:
    """True when a dotted token is rooted outside the repo.

    ``os.environ.setdefault`` (stdlib), ``requests.get`` (third-party) and
    other attribute chains whose root segment is neither a repo symbol nor a
    repo top-level module are unverifiable, not contradicted. An undotted
    token — or one rooted in the repo (``app.missing_fn``) — is plausibly
    repo-local, so its absence stays a real contradiction.
    """
    t = token.strip()
    if t.endswith("()"):
        t = t[:-2]
    t = t.lstrip(".")
    if "." not in t:
        return False
    root = t.split(".", 1)[0]
    if root in symbol_names or root in repo_modules:
        return False
    # Either stdlib (sys.stdlib_module_names) or an unknown third-party /
    # alias root — both are outside what map/symbols.json can verify.
    return True


def _repo_module_names(file_paths: frozenset[str]) -> frozenset[str]:
    """Top-level import roots derivable from ``map/files.json``.

    The first path segment of nested files plus the stem of root-level files
    — enough to tell ``app.missing_fn`` (repo-rooted) from ``os.environ``
    (stdlib, see :data:`sys.stdlib_module_names`) or ``requests.get``.
    """
    out: set[str] = set()
    for p in file_paths:
        if "/" in p:
            out.add(p.split("/", 1)[0])
        else:
            out.add(p.rsplit(".", 1)[0])
    return frozenset(out)


def _with_status(claim: Claim, status: str, reason: Optional[str]) -> Claim:
    return Claim(
        text=claim.text,
        source_file=claim.source_file,
        kind=claim.kind,
        subject=claim.subject,
        object=claim.object,
        status=status,
        reason=reason,
    )


def _bare_name(token: str) -> str:
    """Strip ``()``, leading dot, and dotted prefixes for symbol lookup."""
    t = token.strip()
    if t.endswith("()"):
        t = t[:-2]
    t = t.lstrip(".")
    if "." in t:
        t = t.rsplit(".", 1)[-1]
    return t


def _summarize(feature_id: str, claims: list[Claim]) -> RealityReport:
    verified = sum(1 for c in claims if c.status == "verified")
    contradicted = sum(1 for c in claims if c.status == "contradicted")
    ambiguous = sum(1 for c in claims if c.status == "ambiguous")
    return RealityReport(
        schema_version=SCHEMA_VERSION,
        feature_id=feature_id,
        claims_total=len(claims),
        verified=verified,
        contradicted=contradicted,
        ambiguous=ambiguous,
        claims=tuple(claims),
    )


# ----- IO helpers -----------------------------------------------------------


def _load_symbols(context_dir: Path) -> tuple[frozenset[str], dict[str, str]]:
    """Read ``map/symbols.json``. Return (names, name → path)."""
    path = context_dir / "map" / "symbols.json"
    if not path.exists():
        return frozenset(), {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset(), {}
    names: set[str] = set()
    by_name: dict[str, str] = {}
    for s in payload.get("symbols", []) or []:
        n = s.get("name")
        p = s.get("path")
        if isinstance(n, str):
            names.add(n)
            if isinstance(p, str):
                by_name.setdefault(n, p)
    return frozenset(names), by_name


def _load_call_edges(
    context_dir: Path, symbol_names: frozenset[str]
) -> frozenset[tuple[str, str]]:
    """Read ``features/symbol-graph.json``. Return (subject_name, object_name) pairs.

    Edges in the graph are by node-id, not name. We resolve each end via
    its node's ``label`` field, since labels are how the call/uses
    relations are written.
    """
    path = context_dir / "features" / "symbol-graph.json"
    if not path.exists():
        return frozenset()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    label_by_id: dict[str, str] = {}
    for n in payload.get("nodes", []) or []:
        nid = n.get("id")
        label = n.get("label")
        if isinstance(nid, str) and isinstance(label, str):
            # Strip the same decorations we normalize in _bare_name so
            # the edge set matches what claims look like after parsing.
            clean = label.rstrip("()").lstrip(".")
            if "." in clean:
                clean = clean.rsplit(".", 1)[-1]
            label_by_id[nid] = clean
    edges: set[tuple[str, str]] = set()
    for e in payload.get("links", payload.get("edges", [])) or []:
        if e.get("relation") not in ("calls", "uses"):
            continue
        s = label_by_id.get(e.get("source"))
        t = label_by_id.get(e.get("target"))
        if s and t:
            edges.add((s, t))
    return frozenset(edges)


def _load_file_paths(context_dir: Path) -> frozenset[str]:
    """Repo-relative POSIX paths of every code file we know about."""
    path = context_dir / "map" / "files.json"
    if not path.exists():
        return frozenset()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    out: set[str] = set()
    for f in payload.get("files", []) or []:
        p = f.get("path")
        if isinstance(p, str):
            out.add(p)
    return frozenset(out)


def _load_feature_files(context_dir: Path, feature_id: str) -> frozenset[str]:
    """The feature's own ``files`` list from ``feature.json`` (tolerant).

    Used to disambiguate bare-basename file:line citations. A missing or
    malformed ``feature.json`` degrades to an empty set — the verifier then
    falls back to repo-wide resolution rather than failing the whole check.
    """
    try:
        return frozenset(read_feature_files(context_dir / "features", feature_id))
    except (OSError, ValueError):
        return frozenset()


def _repo_root_from_meta(context_dir: Path) -> Optional[str]:
    """Read the repo root recorded in ``meta.json``."""
    path = context_dir / "meta.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("root")
    except (OSError, json.JSONDecodeError):
        return None


# ----- Writers --------------------------------------------------------------


def write_report(feat_dir: Path, report: RealityReport) -> tuple[Path, Path]:
    """Atomically write the JSON + MD reports."""
    feat_dir = feat_dir.resolve()
    feat_dir.mkdir(parents=True, exist_ok=True)
    json_path = feat_dir / "_reality-check.json"
    md_path = feat_dir / "_reality-check.md"
    _atomic_write(json_path, json.dumps(report.to_dict(), indent=2) + "\n")
    _atomic_write(md_path, render_report_md(report))
    return json_path, md_path


def render_report_md(report: RealityReport) -> str:
    lines: list[str] = [
        f"# Reality check — `{report.feature_id}`",
        "",
        (
            f"_{report.claims_total} concrete claim(s) extracted from "
            f"the chairman's docs: "
            f"**{report.verified} verified**, "
            f"**{report.contradicted} contradicted**, "
            f"**{report.ambiguous} ambiguous**._"
        ),
        "",
    ]
    if report.has_contradictions:
        lines.append("## Contradicted")
        lines.append("")
        lines.append(
            "These claims couldn't be reconciled with the AST. The original "
            "persona should revise or remove them on the next council pass."
        )
        lines.append("")
        for c in report.claims:
            if c.status != "contradicted":
                continue
            lines.append(f"- `{c.text}` ({c.source_file}) — {c.reason or 'no detail'}")
        lines.append("")
    ambig = [c for c in report.claims if c.status == "ambiguous"]
    if ambig:
        lines.append("## Ambiguous")
        lines.append("")
        lines.append(
            "Symbols exist but the relation couldn't be confirmed. Often "
            "indirect calls or aliases — worth a manual look."
        )
        lines.append("")
        for c in ambig:
            lines.append(f"- `{c.text}` ({c.source_file}) — {c.reason or '—'}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


# ----- Confidence demotion --------------------------------------------------


# feature.json key holding the pre-demotion confidence so a clean re-run can
# restore it. Written by demote_feature_on_contradiction, consumed (popped) by
# promote_feature_on_clean.
DEMOTED_FROM_KEY = "confidence_demoted_from"

_VALID_CONFIDENCE_VALUES = frozenset(level.value for level in ConfidenceLevel)


def demote_feature_on_contradiction(features_dir: Path, report: RealityReport) -> bool:
    """When the report has contradictions, flip the feature's confidence
    to ``AMBIGUOUS`` in feature.json + INDEX.json. Returns True if
    anything was touched.

    The prior confidence is stashed under ``confidence_demoted_from`` so a
    later clean run can restore it (:func:`promote_feature_on_clean`).
    Idempotent: a second call after the confidence is already
    AMBIGUOUS is a no-op and leaves any existing stash untouched.
    """
    if not report.has_contradictions:
        return False
    feat_dir = features_dir / report.feature_id
    feature_json = feat_dir / "feature.json"
    if not feature_json.exists():
        return False
    try:
        payload = json.loads(feature_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    prior = payload.get("confidence")
    if prior == ConfidenceLevel.AMBIGUOUS:
        return False
    payload["confidence"] = ConfidenceLevel.AMBIGUOUS.value
    if (
        isinstance(prior, str)
        and prior in _VALID_CONFIDENCE_VALUES
        and DEMOTED_FROM_KEY not in payload
    ):
        payload[DEMOTED_FROM_KEY] = prior
    _atomic_write(feature_json, json.dumps(payload, indent=2) + "\n")

    _mirror_confidence_to_index(
        features_dir, report.feature_id, ConfidenceLevel.AMBIGUOUS.value
    )
    return True


def promote_feature_on_clean(features_dir: Path, report: RealityReport) -> bool:
    """The exact inverse of :func:`demote_feature_on_contradiction`.

    When a re-run is clean (zero contradictions) and the feature sits at
    ``AMBIGUOUS`` with a ``confidence_demoted_from`` stash, restore the
    stashed value (popping the stash) in feature.json + INDEX.json. Returns
    True if anything was touched. A dirty report, a non-AMBIGUOUS feature,
    or a missing/invalid stash are all no-ops — never destructive.
    """
    if report.has_contradictions:
        return False
    feat_dir = features_dir / report.feature_id
    feature_json = feat_dir / "feature.json"
    if not feature_json.exists():
        return False
    try:
        payload = json.loads(feature_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if payload.get("confidence") != ConfidenceLevel.AMBIGUOUS.value:
        return False
    stash = payload.get(DEMOTED_FROM_KEY)
    if not isinstance(stash, str) or stash not in _VALID_CONFIDENCE_VALUES:
        return False
    restored = ConfidenceLevel(stash)
    payload["confidence"] = restored.value
    del payload[DEMOTED_FROM_KEY]
    _atomic_write(feature_json, json.dumps(payload, indent=2) + "\n")

    _mirror_confidence_to_index(features_dir, report.feature_id, restored.value)
    return True


def _mirror_confidence_to_index(
    features_dir: Path, feature_id: str, confidence: str
) -> None:
    """Mirror a confidence change into INDEX.json so the table view matches."""
    index_path = features_dir / "INDEX.json"
    if not index_path.exists():
        return
    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for entry in idx.get("features", []) or []:
        if entry.get("feature_id") == feature_id:
            entry["confidence"] = confidence
    _atomic_write(index_path, json.dumps(idx, indent=2) + "\n")
