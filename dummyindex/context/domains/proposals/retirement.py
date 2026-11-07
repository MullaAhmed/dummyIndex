"""Read-only knowledge and reference guards shared by closeout and GC."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from ..docguard.citations import cites_disposable
from .errors import CloseoutError

ADMIN_FILES = frozenset(
    {"proposal.json", "checklist.md", "checks.json", "audit.json", "description.md"}
)
_TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".rst",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
}
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".claude",
    ".agents",
    ".codex",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def contained(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise CloseoutError(f"path escapes allowed root: {path}")
    return resolved


def workspace_inventory(workspace: Path) -> dict[str, str]:
    result = {}
    for path in sorted(workspace.rglob("*")):
        contained(path, workspace)
        if path.is_file():
            result[path.relative_to(workspace).as_posix()] = digest(path.read_bytes())
    if len(result) > 2000:
        raise CloseoutError("closeout exceeds 2000 files; split the workspace review")
    return result


def receipt_path(context_dir: Path, kind: str, slug: str) -> Path:
    return contained(
        context_dir / "gc" / "closeouts" / f"{kind}-{slug}.json", context_dir
    )


def durable_references(context_dir: Path, workspace: Path) -> list[str]:
    root = context_dir.parent.resolve()
    relative = workspace.relative_to(context_dir).as_posix()
    direct = re.compile(re.escape(relative) + r"(?=[/\\\s#`'\"\])]|$)")
    family, _, slug = relative.rpartition("/")
    split = re.compile(
        re.escape(family) + r"""["']\s*[,/+]\s*["']""" + re.escape(slug) + r"""["']"""
    )
    hits = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        dirs[:] = [
            name
            for name in dirs
            if name not in _SKIP_DIRS
            and not (
                parent == context_dir
                and name in {"proposals", "audits", "cache", "gc", "map", "source-docs"}
            )
        ]
        for name in files:
            path = parent / name
            if path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            # Machine graph payloads are not authored inbound dependencies.
            if parent == context_dir / "features" and name in {
                "symbol-graph.json",
                "graph.json",
                "seed-rank.json",
                "graph-communities.json",
            }:
                continue
            contained(path, root)
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeError:
                continue
            except OSError as exc:
                raise CloseoutError(
                    f"cannot inspect durable references in {path}: {exc}"
                ) from exc
            if direct.search(text.replace("\\", "/")) or split.search(text):
                hits.append(path.relative_to(root).as_posix())
    return hits


def text_unit(data: bytes) -> bytes:
    return data.decode("utf-8").replace("\r\n", "\n").strip("\n").encode("utf-8")


def unit_present(path: Path, unit: dict, *, data: bytes | None = None) -> bool:
    if data is None:
        if not path.is_file():
            return False
        data = path.read_bytes()
    if unit["kind"] == "fixture":
        return digest(data) == unit["sha256"]
    try:
        lines = text_unit(data).split(b"\n")
    except UnicodeError:
        return False
    width = unit["lines"]
    return any(
        digest(b"\n".join(lines[i : i + width])) == unit["sha256"]
        for i in range(len(lines) - width + 1)
    )


def durable_evidence(context_dir: Path, rows: list) -> list[dict]:
    """Bind outcomes to current durable files after resolving path aliases."""
    if not isinstance(rows, list):
        raise CloseoutError("evidence must be a list")
    result = []
    for row in rows:
        target = contained(context_dir.parent / row["path"], context_dir.parent)
        relative = target.relative_to(context_dir.parent).as_posix()
        if (
            any(
                target.is_relative_to(context_dir / family)
                for family in ("cache", "proposals", "audits")
            )
            or cites_disposable(relative)
            or digest(target.read_bytes()) != row["sha256"]
        ):
            raise CloseoutError(
                f"outcome evidence is missing/stale/disposable: {relative}"
            )
        result.append({**row, "path": relative})
    return result


def retirement_block(context_dir: Path, workspace: Path, *, kind: str) -> str | None:
    refs = durable_references(context_dir, workspace)
    if refs:
        return "durable references remain: " + ", ".join(refs[:8])
    path = receipt_path(context_dir, kind, workspace.name)
    if path.with_suffix(".pending.json").exists():
        return "interrupted closeout; review current files and resume explicitly"
    if not path.exists():
        return (
            "knowledge review/closeout receipt required"
            if _has_material(workspace)
            else None
        )
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if (
            receipt.get("schema_version") != 1
            or receipt.get("kind") != kind
            or receipt.get("slug") != workspace.name
        ):
            return "closeout receipt identity does not match the workspace"
        if receipt.get("workspace_files") != workspace_inventory(workspace):
            return "workspace changed after closeout; review the delta"
        durable_evidence(context_dir, receipt.get("evidence", []))
        for resolution in receipt.get("resolved_verification", {}).values():
            if not durable_evidence(context_dir, resolution["evidence"]):
                return "verification resolution is missing durable evidence"
        superseded = receipt.get("superseded", {})
        for unit in receipt["transfers"]:
            if superseded.get(unit["id"], "").strip():
                continue
            target = contained(context_dir.parent / unit["target"], context_dir.parent)
            if not unit_present(target, unit):
                return f"accepted knowledge/fixture missing or changed: {unit['id']}"
    except (CloseoutError, OSError, ValueError, KeyError, TypeError) as exc:
        return f"invalid closeout receipt: {exc}"
    return None


def _has_material(workspace: Path) -> bool:
    from .store import _checklist_template, _plan_template, _spec_template

    try:
        head = json.loads((workspace / "proposal.json").read_text(encoding="utf-8"))
        title = head.get("title", "")
    except (OSError, ValueError):
        title = ""
    templates = {
        "spec.md": _spec_template(title),
        "plan.md": _plan_template(title),
        "checklist.md": _checklist_template(title),
    }
    for name in workspace_inventory(workspace):
        if name == "checks.json":
            return (
                True  # Execution evidence must survive in the durable closeout receipt.
            )
        if name in ADMIN_FILES:
            continue
        if name in templates:
            text = (workspace / name).read_text(encoding="utf-8")
            text = re.sub(
                r"<!-- dummyindex:consistency:begin -->.*?<!-- dummyindex:consistency:end -->",
                "",
                text,
                flags=re.S,
            )
            expected = re.sub(
                r"<!-- dummyindex:consistency:begin -->.*?<!-- dummyindex:consistency:end -->",
                "",
                templates[name],
                flags=re.S,
            )
            if text.strip() == expected.strip():
                continue
        return True
    return False
