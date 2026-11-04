"""Qualify exact guidance edits with existing project tests and recoverable writes.

This checks project-test compatibility, not model improvement. Check code stays
outside the editable guidance; both arms use the same captured working inputs.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

CommandRunner = Callable[[list[str], Path], tuple[int, str]]
_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
    }
)
_STATE_PREFIXES = (".context/cache/", ".context/gc/evolve/")
_CONFIGS = ("pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")


class EvolveError(Exception):
    """An evolve operation could not safely complete."""


@dataclass(frozen=True)
class GateStage:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class GateResult:
    verdict: str
    stages: tuple[GateStage, ...]
    receipt_json: str = "{}"

    def to_dict(self) -> dict:
        qualification = "project tests only; model behavior improvement unmeasured"
        if self.verdict == "pass" and self.stages[0].status == "fail":
            qualification = "candidate passes project tests; baseline failed; model behavior improvement unmeasured"
        return {
            "verdict": self.verdict,
            "stages": [stage.to_dict() for stage in self.stages],
            "receipt": json.loads(self.receipt_json),
            "qualification": qualification,
        }


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_digest(value: object) -> str:
    return _digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def safe_file(root: Path, relative: str, *, exists: bool = True) -> Path:
    """Resolve a regular file without following any symlink or escaping root."""
    pure = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or pure.is_absolute()
        or PureWindowsPath(relative).drive
        or ".." in pure.parts
        or str(pure) == "."
    ):
        raise EvolveError(f"unsafe relative file path: {relative!r}")
    root = root.absolute()
    path = root
    for part in pure.parts:
        path = path / part
        if path.is_symlink():
            raise EvolveError(f"symlink is not an evolve input or destination: {path}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise EvolveError(f"path escapes its workspace: {path}")
    if exists and not path.is_file():
        raise EvolveError(f"required file missing: {path}")
    if path.exists() and not path.is_file():
        raise EvolveError(f"expected a regular file: {path}")
    return path


def staged_files(
    run_dir: Path, index: int, targets: tuple[str, ...]
) -> tuple[Path, ...]:
    """Use repo-relative staging; accept old basenames only when unambiguous."""
    if not targets or len({t.casefold() for t in targets}) != len(targets):
        raise EvolveError("candidate must have distinct, non-empty target paths")
    names = Counter(Path(t).name.casefold() for t in targets)
    stage_root = run_dir / "staged" / str(index)
    # Check ancestors too, not just paths below an already-linked stage root.
    safe_file(run_dir, f"staged/{index}/.path-check", exists=False)
    paths: list[Path] = []
    for target in targets:
        canonical = safe_file(stage_root, target, exists=False)
        if canonical.is_file():
            paths.append(canonical)
            continue
        if names[Path(target).name.casefold()] != 1:
            raise EvolveError(
                f"ambiguous legacy staging for {target}; use staged/{index}/{target}"
            )
        paths.append(safe_file(stage_root, Path(target).name))
    return tuple(paths)


def _included(relative: str) -> bool:
    return (
        not any(part in _IGNORED_DIRS for part in PurePosixPath(relative).parts)
        and not relative.startswith(_STATE_PREFIXES)
        and relative != ".context/gc/evolution.jsonl"
        and not relative.endswith((".pyc", ".pyo"))
    )


def _working_inputs(root: Path) -> dict[str, bytes]:
    """Capture tracked and nonignored working bytes, including dirty/untracked files."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is not None and result.returncode == 0:
        names = {os.fsdecode(p) for p in result.stdout.split(b"\0") if p}
    else:
        names: set[str] = set()
        for directory, dirs, files in os.walk(root, followlinks=False):
            base = Path(directory)
            dirs[:] = [
                d
                for d in dirs
                if _included((base / d).relative_to(root).as_posix() + "/")
                and not (base / d).is_symlink()
            ]
            names.update((base / f).relative_to(root).as_posix() for f in files)
    inputs: dict[str, bytes] = {}
    for relative in sorted(names):
        relative = relative.replace("\\", "/")
        if not _included(relative):
            continue
        try:
            path = safe_file(root, relative, exists=False)
        except EvolveError:
            continue  # Never follow unrelated symlinks into another workspace.
        if path.is_file():
            inputs[relative] = path.read_bytes()
    return inputs


def _selected_tests(
    targets: tuple[str, ...], inputs: dict[str, bytes], requested: tuple[str, ...]
) -> tuple[str, ...]:
    if requested:
        for test in requested:
            if (
                not test.startswith("tests/")
                or not test.endswith(".py")
                or test not in inputs
            ):
                raise EvolveError(
                    f"verification must name an existing project tests/*.py file: {test}"
                )
        return tuple(dict.fromkeys(requested))
    segments = {
        segment
        for target in targets
        for segment in (PurePosixPath(target).stem, *PurePosixPath(target).parts)
        if len(segment) >= 3
        and segment not in {"tests", "test", "dummyindex", "fixtures"}
    }
    return tuple(
        p
        for p in inputs
        if p.startswith("tests/")
        and PurePosixPath(p).name.startswith("test_")
        and p.endswith(".py")
        and any(s in p for s in segments)
    )


def _profile() -> dict:
    env = dict(os.environ)
    for name in (
        "PYTHONPATH",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "PYTEST_CURRENT_TEST",
    ):
        env.pop(name, None)
    return {
        "python": sys.executable,
        "python_version": sys.version,
        "pytest_version": importlib.metadata.version("pytest"),
        "gate_code_sha256": _digest(Path(__file__).read_bytes()),
        "promotion_code_sha256": _digest(
            Path(__file__).with_name("evolve_promotion.py").read_bytes()
        ),
        "environment_sha256": _json_digest(env),
        "pythonpath": "isolated project root",
        "user_site": False,
        "external_pytest_plugins": False,
    }


def _managed_overlay(
    inputs: dict[str, bytes], edits: dict[str, bytes], *, normalize: bool = False
) -> dict[str, bytes]:
    """Rebaseline generated bodies without changing measured bytes at promotion."""
    from .equip.generate.render import set_frontmatter_version
    from .equip.lifecycle.hashing import content_hash
    from .equip.lifecycle.status import _bump, is_lifecycle_managed
    from .equip.models import EquipmentManifest

    manifest_path = ".context/equipment.json"
    if manifest_path not in inputs or not any(
        p.startswith(".context/equipment/") for p in edits
    ):
        return edits
    try:
        raw = json.loads(inputs[manifest_path])
        manifest = EquipmentManifest.from_dict(raw)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise EvolveError(f"cannot validate equipment ownership: {exc}") from exc
    managed = [item for item in manifest.items if item.path in edits]
    if not managed:
        return edits
    if manifest_path in edits:
        raise EvolveError(
            "cannot mix an explicit equipment.json edit with managed-body changes"
        )
    if len({item.path for item in managed}) != len(managed):
        raise EvolveError("multiple equipment records own the same candidate path")
    result = dict(edits)
    for item in managed:
        if not is_lifecycle_managed(item):
            raise EvolveError(
                f"target is not a hash-owned generated capability: {item.path}"
            )
        try:
            # Equip hashes read_text() content, which uses universal newlines.
            incumbent = (
                inputs[item.path]
                .decode("utf-8")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
            )
            content = (
                edits[item.path]
                .decode("utf-8")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
            )
        except (KeyError, UnicodeDecodeError) as exc:
            raise EvolveError(
                f"managed capability is not readable UTF-8: {item.path}"
            ) from exc
        if content_hash(incumbent) != item.origin_hash:
            raise EvolveError(
                f"managed capability was edited outside evolve: {item.path}"
            )
        version = _bump(item.version, "patch")
        normalized = set_frontmatter_version(content, version).encode("utf-8")
        if not normalize and normalized != edits[item.path]:
            raise EvolveError(
                f"staged managed capability needs version {version}; rerun evolve apply: {item.path}"
            )
        result[item.path] = normalized
        record = next(
            record for record in raw["items"] if record.get("path") == item.path
        )
        record.update(
            version=version, origin_hash=content_hash(normalized.decode("utf-8"))
        )
    # Keep unknown fields and unrelated records byte-for-byte in meaning.
    result[manifest_path] = (json.dumps(raw, indent=2) + "\n").encode("utf-8")
    return result


def _normalize_managed_stage(
    targets: tuple[str, ...], run_dir: Path, index: int, project_root: Path
) -> None:
    paths = staged_files(run_dir, index, targets)
    edits = {t: p.read_bytes() for t, p in zip(targets, paths, strict=True)}
    normalized = _managed_overlay(_working_inputs(project_root), edits, normalize=True)
    for target, path in zip(targets, paths, strict=True):
        if normalized[target] != edits[target]:
            _atomic_bytes(path, normalized[target])


def _capture(
    targets: tuple[str, ...],
    run_dir: Path,
    index: int,
    project_root: Path,
    candidate: dict | None,
    requested: tuple[str, ...],
):
    staged = staged_files(run_dir, index, targets)
    for target in targets:
        safe_file(project_root, target)
    for test in requested:
        safe_file(project_root, test)
    inputs = _working_inputs(project_root)
    modes = {p: stat.S_IMODE(safe_file(project_root, p).stat().st_mode) for p in inputs}
    for target in targets:
        if target not in inputs:
            raise EvolveError(f"target is not a captured project input: {target}")
    edits = {
        target: path.read_bytes() for target, path in zip(targets, staged, strict=True)
    }
    edits = _managed_overlay(inputs, edits)
    tests = _selected_tests(targets, inputs, requested)
    config = next((name for name in _CONFIGS if name in inputs), "_evolve_pytest.ini")
    argv = [sys.executable, "-m", "pytest", "-q", "--rootdir=.", "-c", config, *tests]
    profile = _profile()
    checks = {
        p: _digest(b)
        for p, b in inputs.items()
        if p in tests or p in _CONFIGS or p.endswith("conftest.py")
    }
    receipt = {
        "schema_version": 1,
        "candidate_sha256": _json_digest(
            candidate if candidate is not None else {"target_file": list(targets)}
        ),
        "staged_sha256": {p: _digest(b) for p, b in edits.items()},
        "baseline_sha256": _json_digest(
            {p: [_digest(b), modes[p]] for p, b in inputs.items()}
        ),
        "baseline_targets": {p: _digest(inputs[p]) for p in edits},
        "verification_sha256": _json_digest(
            {"checks": checks, "argv": argv, "profile": profile}
        ),
        "tests": list(tests),
        "argv": argv,
        "profile": profile,
    }
    return receipt, inputs, edits, modes


def _default_runner(argv: list[str], cwd: Path) -> tuple[int, str]:
    env = dict(os.environ)
    env.update(
        PYTHONPATH=str(cwd), PYTHONNOUSERSITE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
    )
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvolveError(f"pytest could not run: {exc}") from exc
    return result.returncode, result.stdout + result.stderr


def _verdict(stages: tuple[GateStage, ...]) -> str:
    """Require candidate success; incumbent assertion failures are comparison data."""
    if not stages:
        return "blocked"
    if stages[-1].name == "candidate-pytest" and stages[-1].status == "fail":
        return "fail"
    if any(stage.status == "blocked" for stage in stages):
        return "blocked"
    if [stage.name for stage in stages] == ["baseline-pytest", "candidate-pytest"]:
        if stages[0].status in {"pass", "fail"} and stages[1].status == "pass":
            return "pass"
    return "blocked"


def run_gate(
    targets: tuple[str, ...],
    run_dir: Path,
    context_dir: Path,
    project_root: Path,
    *,
    candidate_index: int = 0,
    candidate_payload: dict | None = None,
    test_paths: tuple[str, ...] = (),
    runner: CommandRunner | None = None,
) -> GateResult:
    """Run existing checks against baseline and exact staged files at the same scratch root."""
    del context_dir  # Kept in the public signature for existing callers.
    _normalize_managed_stage(targets, run_dir, candidate_index, project_root)
    receipt, inputs, edits, modes = _capture(
        targets, run_dir, candidate_index, project_root, candidate_payload, test_paths
    )
    encoded = json.dumps(receipt, sort_keys=True)
    if not receipt["tests"]:
        return GateResult(
            "blocked",
            (
                GateStage(
                    "project-tests",
                    "blocked",
                    "no applicable project tests; model behavior improvement unmeasured",
                ),
            ),
            encoded,
        )
    stages: list[GateStage] = []
    execute = runner or _default_runner
    with tempfile.TemporaryDirectory(prefix="dummyindex-evolve-") as temp:
        workspace = Path(temp) / "workspace"
        for label, overlay in (("baseline-pytest", {}), ("candidate-pytest", edits)):
            if workspace.exists():
                if (
                    workspace.is_symlink()
                    or workspace.resolve().parent != Path(temp).resolve()
                ):
                    raise EvolveError(
                        "verification workspace escaped its temporary root"
                    )
                shutil.rmtree(workspace)
            workspace.mkdir()
            for relative, content in (inputs | overlay).items():
                path = safe_file(workspace, relative, exists=False)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                path.chmod(modes[relative])
            if receipt["argv"][6] == "_evolve_pytest.ini":
                (workspace / "_evolve_pytest.ini").write_text(
                    "[pytest]\n", encoding="utf-8"
                )
            try:
                code, output = execute(list(receipt["argv"]), workspace)
                status = "pass" if code == 0 else "fail" if code == 1 else "blocked"
                detail = output.strip()[-1000:]
            except (EvolveError, OSError) as exc:
                status, detail = "blocked", str(exc)
            stages.append(GateStage(label, status, detail))
    return GateResult(_verdict(tuple(stages)), tuple(stages), encoded)


def check_receipt(
    gate: dict,
    targets: tuple[str, ...],
    run_dir: Path,
    index: int,
    project_root: Path,
    candidate: dict,
) -> None:
    """Reject changed content/checks/profile even for a manual blocked override."""
    receipt = gate.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise EvolveError(
            "gate has no current qualification receipt; rerun evolve apply"
        )
    tests = receipt.get("tests")
    if not isinstance(tests, list) or not all(isinstance(p, str) for p in tests):
        raise EvolveError(
            "gate has malformed verification selection; rerun evolve apply"
        )
    current, _, _, _ = _capture(
        targets, run_dir, index, project_root, candidate, tuple(tests)
    )
    if current != receipt:
        raise EvolveError(
            "stale gate: candidate, baseline, verification or execution profile changed; rerun evolve apply"
        )
    stages = gate.get("stages")
    if (
        not isinstance(stages, list)
        or not stages
        or not all(isinstance(s, dict) for s in stages)
    ):
        raise EvolveError("malformed gate stages; rerun evolve apply")
    if tests:
        if [s.get("name") for s in stages] != ["baseline-pytest", "candidate-pytest"]:
            raise EvolveError("missing project-test stage; rerun evolve apply")
    elif gate.get("verdict") != "blocked":
        raise EvolveError(
            "no applicable checks cannot qualify as a pass; rerun evolve apply"
        )
    statuses = {s.get("status") for s in stages}
    if not statuses <= {"pass", "fail", "blocked"}:
        raise EvolveError("invalid gate status; rerun evolve apply")
    expected = _verdict(
        tuple(
            GateStage(s["name"], s["status"], str(s.get("detail", ""))) for s in stages
        )
    )
    if gate.get("verdict") != expected:
        raise EvolveError("gate verdict does not match its checks; rerun evolve apply")


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
