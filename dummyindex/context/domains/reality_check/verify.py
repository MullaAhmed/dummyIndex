"""Verification — check each extracted claim against the AST extraction.

Resolves symbols, call edges, and file:line citations against the
deterministic backbone (``map/symbols.json``, ``features/symbol-graph.json``,
``map/files.json``) plus the actual source on disk. Also hosts the public
orchestrator :func:`reality_check_feature`, which wires extraction →
verification → summary.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from dummyindex.context.domains.dev_pick import read_feature_files
from dummyindex.pipeline.io import (
    is_git_repo,
    is_safe_read_target,
    resolve_git_dir,
    resolve_under_root,
)

from .extract import _CANONICAL_DOCS, _extract_claims
from .models import SCHEMA_VERSION, Claim, RealityReport

# Largest file the verifier will line-count: a citation pointing at a huge
# blob is unverifiable rather than worth streaming. 16 MiB comfortably covers
# any real source/doc file in a repo while bounding the read.
_MAX_CITED_FILE_BYTES = 16 * 1024 * 1024

# Characters that turn a feature id into a path-traversal / write primitive.
# A feature id is a single directory name under ``features/`` — never a path.
_FEATURE_ID_FORBIDDEN = ("/", "\\", "..", "\x00")


def _reject_unsafe_feature_id(feature_id: str) -> None:
    """Raise ``ValueError`` if ``feature_id`` could traverse out of ``features/``.

    A feature id names a single subdirectory; ``/``, ``\\``, ``..`` or a NUL
    would let an LLM-authored or CLI-supplied id escape the feature tree and
    read/write arbitrary paths. Rejected here *and* at the CLI boundary
    (``cli/reality_check.py``) so neither entry point trusts the value.
    """
    if any(bad in feature_id for bad in _FEATURE_ID_FORBIDDEN):
        raise ValueError(
            f"unsafe feature id {feature_id!r}: must not contain "
            f"'/', '\\', '..', or NUL"
        )


def reality_check_feature(
    context_dir: Path,
    feature_id: str,
) -> RealityReport:
    """Read a feature's canonical docs, extract claims, verify against AST.

    Raises ``FileNotFoundError`` if the feature folder doesn't exist, or
    ``ValueError`` if ``feature_id`` is a path-traversal attempt.
    """
    _reject_unsafe_feature_id(feature_id)
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
                repo_root=_trusted_repo_root(context_dir),
            )
        )

    return _summarize(feature_id, verified_claims)


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
        if not is_safe_read_target(resolved, max_bytes=_MAX_CITED_FILE_BYTES):
            return _with_status(
                claim, "ambiguous",
                "cited path is not a safe regular file to read "
                "(symlink, non-regular, or too large)",
            )
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

    **Confinement:** every concrete-path branch is routed through
    :func:`resolve_under_root` against ``repo_root`` (or ``feat_dir`` for the
    feature-own-doc branch). A citation that resolves outside that root — an
    absolute path, a ``../`` escape, or an in-repo symlink whose realpath
    leaves the tree — yields a not-found verdict *without ever opening the
    target*, so the verifier is never a filesystem read oracle.
    """
    if path_str in file_paths:
        return _confine(repo_root / path_str, repo_root)
    on_disk = repo_root / path_str
    if on_disk.is_file():
        return _confine(on_disk, repo_root)
    if "/" not in path_str and (feat_dir / path_str).is_file():
        return _confine(feat_dir / path_str, feat_dir)
    base = path_str.rsplit("/", 1)[-1]
    candidates = sorted(
        fp for fp in file_paths if fp.endswith("/" + base) or fp == base
    )
    if not candidates:
        return ("contradicted", "file not found in map/files.json or on disk")
    if len(candidates) == 1:
        return _confine(repo_root / candidates[0], repo_root)
    scoped = sorted(set(candidates) & feature_files)
    if len(scoped) == 1:
        return _confine(repo_root / scoped[0], repo_root)
    shown = ", ".join(candidates[:5]) + (", …" if len(candidates) > 5 else "")
    return (
        "ambiguous",
        f"basename matches {len(candidates)} files ({shown}) — "
        f"fully qualify the citation",
    )


def _confine(candidate: Path, root: Path) -> Path | tuple[str, str]:
    """Return ``candidate`` iff it resolves under ``root``, else a verdict.

    Routes through :func:`resolve_under_root` (which resolves symlinks before
    the containment check). On escape, returns a ``("contradicted", …)``
    verdict so the caller never opens the file.
    """
    safe = resolve_under_root(candidate, root)
    if safe is None:
        return (
            "contradicted",
            "cited path resolves outside the repository root",
        )
    return safe


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


def _git_toplevel(context_dir: Path) -> Optional[Path]:
    """The resolved git working-tree root at or above ``context_dir``, if any.

    Walks ``context_dir`` and its ancestors looking for a git working tree
    (plain checkout *or* submodule/worktree, via :func:`is_git_repo`) and
    returns the **resolved** toplevel. ``None`` when no ancestor is a repo.
    This is the trusted anchor: a ``meta.json`` ``root`` is honored only when
    it resolves to exactly this directory.
    """
    here = context_dir.resolve()
    for candidate in (here, *here.parents):
        if is_git_repo(candidate):
            # resolve_git_dir hands back the .git dir; the working tree is the
            # candidate we matched (already resolved).
            if resolve_git_dir(candidate) is not None:
                return candidate
            return candidate
    return None


def _repo_root_from_meta(context_dir: Path) -> Optional[str]:
    """Read the repo root recorded in ``meta.json`` (untrusted, as-written)."""
    path = context_dir / "meta.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("root")
    except (OSError, json.JSONDecodeError):
        return None


def _trusted_repo_root(context_dir: Path) -> Path:
    """Resolve a trustworthy ``repo_root`` to confine every cited-path read.

    The recorded ``meta.json`` ``root`` is **untrusted** — it is honored only
    when it resolves to exactly the git toplevel (the trusted anchor). Anything
    else (e.g. a poisoned ``"/"``) falls back to the anchor, never to "any
    ancestor of ``context_dir``" (which would admit ``/``). When there is no
    git toplevel at all, fall back to ``context_dir.parent`` (the historical
    default for a non-repo ``.context/`` skeleton).

    Equality anchors to the **resolved** toplevel, not raw string equality —
    so ``"/repo/."`` or a symlinked spelling still matches.
    """
    anchor = _git_toplevel(context_dir)
    meta_root = _repo_root_from_meta(context_dir)
    if meta_root is not None and anchor is not None:
        if Path(meta_root).resolve() == anchor:
            return anchor
    if anchor is not None:
        return anchor
    return context_dir.parent.resolve()
