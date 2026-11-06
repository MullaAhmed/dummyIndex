"""Bounded immutable input and actor snapshots for native replay."""

import hashlib
import importlib.metadata
import os
import platform
import stat
import sys
from pathlib import Path

from dummyindex.export import storage as graph_storage

from .evidence import digest
from .evolve_gate import EvolveError, _environment, _working_inputs, safe_file


def _hashes(inputs):
    return {p: hashlib.sha256(b).hexdigest() for p, b in inputs.items()}


def _controller():
    return _hashes(
        {
            name: Path(__file__).with_name(name).read_bytes()
            for name in (
                "evolve_native.py",
                "evolve_native_snapshot.py",
                "evolve_native_response.py",
                "evolve_experiments.py",
                "evolve.py",
                "evolve_gate.py",
                "evidence.py",
                "evolve_promotion.py",
                "atomic_io.py",
            )
        }
        | {"export/storage.py": Path(graph_storage.__file__).read_bytes()}
    )


def _inputs(root):
    inputs = {
        p: b
        for p, b in _working_inputs(root).items()
        if not p.startswith((".context/gc/experiments/", ".context/gc/learning/"))
        and p not in {".context/gc/evidence.json", ".context/gc/guidance-utility.json"}
    }
    manifest = ".context/features/symbol-graph.json"
    if manifest not in inputs:
        return inputs
    # Omit generated history only after verifying the complete captured generation.
    try:
        data = graph_storage._decode(inputs[manifest], root / manifest)
        if data.get("format") == graph_storage._FORMAT:
            graph_storage._read_manifest(data, root / manifest, len(inputs[manifest]))
            active = {".context/features/" + d["path"] for d in data["shards"]}
            if any(
                ".context/features/" + d["path"] not in inputs
                or hashlib.sha256(inputs[".context/features/" + d["path"]]).hexdigest()
                != d["sha256"]
                for d in data["shards"]
            ):
                return inputs
        elif isinstance(data.get("nodes"), list) and isinstance(
            data.get("links", data.get("edges")), list
        ):
            active = set()
        else:
            return inputs
    except (OSError, ValueError):
        return inputs
    prefix = ".context/features/symbol-graph.parts/"
    return {
        p: b
        for p, b in inputs.items()
        if p in active
        or not (
            p.startswith(prefix)
            and p.endswith(".json")
            and graph_storage._HASH_RE.fullmatch(p[len(prefix) : -5])
        )
    }


def _tree(directory):
    """Capture bounded actor artifacts without following links or hiding source in caches."""
    result, size = {}, 0
    for base, dirs, names in os.walk(directory, followlinks=False):
        for name in dirs + names:
            path = Path(base) / name
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise EvolveError("native artifacts cannot contain links or junctions")
        dirs[:] = [d for d in dirs if d not in {".git", ".pytest_cache"}]
        for name in sorted(names):
            path = Path(base) / name
            if path.suffix == ".pyc" and "__pycache__" in path.parts:
                continue
            relative = path.relative_to(directory).as_posix()
            content = safe_file(directory, relative).read_bytes()
            size += len(content)
            if size > 64_000_000 or len(result) >= 10000:
                raise EvolveError(
                    "native artifact snapshot exceeds 64 MB or 10000 files"
                )
            result[relative] = content
    return result


def _modes(root, inputs):
    return {p: stat.S_IMODE(safe_file(root, p).stat().st_mode) for p in inputs}


def _materialize(root, relative, inputs, modes=None):
    if len(inputs) > 10000 or sum(map(len, inputs.values())) > 64_000_000:
        raise EvolveError("native snapshot exceeds 64 MB or 10000 files")
    directory = safe_file(root, relative + "/.check", exists=False).parent
    if directory.exists():
        raise EvolveError(
            "native workspace already exists; do not rerun an outstanding action"
        )
    directory.mkdir(parents=True)
    for name, content in inputs.items():
        target = safe_file(directory, name, exists=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod((modes or {}).get(name, 0o644))
    return directory


def _runtime():
    return digest(
        [
            _environment(),
            platform.platform(),
            sys.executable,
            sys.version,
            sorted(
                (d.metadata.get("Name", ""), d.version)
                for d in importlib.metadata.distributions()
            ),
        ]
    )


def _artifact(directory):
    files = _tree(directory)
    return digest([_hashes(files), _modes(directory, files)])
