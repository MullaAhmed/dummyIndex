"""Per-file ownership for installed skill families; stamps are version hints."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

from dummyindex.context.domains.atomic_io import write_text_atomic

MANIFEST_NAME = ".dummyindex-files.json"
VERSION_NAME = ".dummyindex_version"


@lru_cache(maxsize=1)
def package_source_hash() -> str:
    """Identity of the source this CLI process actually loaded from disk."""
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".md", ".tmpl"):
            digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def source_hash(files: dict[str, str]) -> str:
    hashes = {name: content_hash(text.encode("utf-8")) for name, text in files.items()}
    return content_hash(json.dumps(hashes, sort_keys=True).encode("utf-8"))


def _safe_relative(name: object) -> bool:
    return (
        isinstance(name, str)
        and bool(name)
        and "\\" not in name
        and ":" not in name
        and not PurePosixPath(name).is_absolute()
        and ".." not in PurePosixPath(name).parts
        and PurePosixPath(name).as_posix() == name
        and name not in (".", MANIFEST_NAME, VERSION_NAME)
    )


def _plain_target(directory: Path, relative: str) -> Path | None:
    if not _safe_relative(relative) or _is_link(directory):
        return None
    target = directory
    for part in PurePosixPath(relative).parts:
        target /= part
        if _is_link(target):
            return None
    return target


def _is_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def read_manifest(directory: Path) -> dict | None:
    path = directory / MANIFEST_NAME
    if _is_link(path):
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    files = value.get("files") if isinstance(value, dict) else None
    if (
        not isinstance(files, dict)
        or value.get("schema_version") != 1
        or not all(
            _safe_relative(name)
            and isinstance(digest, str)
            and len(digest) == 64
            and all(c in "0123456789abcdef" for c in digest)
            for name, digest in files.items()
        )
    ):
        return None
    return value


def _baselines(
    directory: Path, *, family: str | None = None
) -> dict[str, tuple[str, ...]]:
    manifest = read_manifest(directory)
    if manifest is not None:
        return {name: (digest,) for name, digest in manifest["files"].items()}
    if (directory / MANIFEST_NAME).exists() or (directory / MANIFEST_NAME).is_symlink():
        return {}
    try:
        stamp = (directory / VERSION_NAME).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return {}
    from .legacy_fingerprints import LEGACY_FILES, LEGACY_VERSION

    if stamp != LEGACY_VERSION:
        return {}
    return LEGACY_FILES.get(family or directory.name, {})


def _matches(path: Path | None, digests: tuple[str, ...]) -> bool:
    if path is None or _is_link(path):
        return False
    try:
        return content_hash(path.read_bytes()) in digests
    except OSError:
        return False


def family_is_pristine(directory: Path, *, family: str | None = None) -> bool:
    """Every existing file must have byte-level ownership, with no unknowns."""
    baselines = _baselines(directory, family=family)
    if not _matches(
        _plain_target(directory, "SKILL.md"), baselines.get("SKILL.md", ())
    ):
        return False
    for path in directory.rglob("*"):
        relative = path.relative_to(directory).as_posix()
        if _is_link(path):
            return False
        if path.is_dir() and not any(
            name.startswith(relative + "/") for name in baselines
        ):
            return False
        if path.is_file() and relative not in (MANIFEST_NAME, VERSION_NAME):
            if not _matches(path, baselines.get(relative, ())):
                return False
    return True


@dataclass(frozen=True)
class InstallFilesResult:
    written: tuple[str, ...]
    removed: tuple[str, ...]
    preserved: tuple[str, ...]
    complete: bool


def sync_family(
    directory: Path,
    files: dict[str, str],
    *,
    family: str,
    version: str,
    layout: str = "full",
    force_downgrade: bool = False,
) -> InstallFilesResult:
    """Refresh only absent, exact-current, or hash-proven stock files."""
    if _is_link(directory) or (directory.exists() and not directory.is_dir()):
        raise OSError(f"refusing skill family path: {directory}")
    from .common import _compare_stamp, _read_stamp

    stamp = _read_stamp(directory / VERSION_NAME)
    if (
        stamp
        and stamp != version
        and _compare_stamp(stamp, version) in ("newer", "unknown")
        and not force_downgrade
    ):
        return InstallFilesResult((), (), tuple(sorted(files)), False)
    for name in (MANIFEST_NAME, VERSION_NAME):
        if _is_link(directory / name):
            raise OSError(f"refusing symlinked ownership metadata: {directory / name}")
    if (directory / MANIFEST_NAME).exists() and read_manifest(directory) is None:
        raise OSError(f"unreadable ownership manifest preserved: {directory}")
    baselines = _baselines(directory, family=family)
    owned: dict[str, str] = {}
    written: list[str] = []
    removed: list[str] = []
    preserved: list[str] = []
    for relative, text in sorted(files.items()):
        target = _plain_target(directory, relative)
        expected = content_hash(text.encode("utf-8"))
        if target is None:
            preserved.append(relative)
            if relative in baselines:
                owned[relative] = baselines[relative][0]
            continue
        if target.exists() and not _matches(target, (expected,)):
            if not _matches(target, baselines.get(relative, ())):
                preserved.append(relative)
                if relative in baselines:
                    owned[relative] = baselines[relative][0]
                continue
        if not _matches(target, (expected,)):
            write_text_atomic(target, text)
            written.append(relative)
        owned[relative] = expected
    for relative, hashes in baselines.items():
        if relative in files:
            continue
        target = _plain_target(directory, relative)
        if _matches(target, hashes):
            target.unlink()
            removed.append(relative)
        elif target is None or target.exists():
            preserved.append(relative)
            owned[relative] = hashes[0]
    complete = not any(name in files for name in preserved)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "family": family,
        "version": version,
        "layout": layout,
        "source_sha256": source_hash(files),
        "package_source_sha256": package_source_hash(),
        "complete": complete,
        "files": owned,
    }
    manifest_text = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if not _matches(
        directory / MANIFEST_NAME, (content_hash(manifest_text.encode("utf-8")),)
    ):
        write_text_atomic(directory / MANIFEST_NAME, manifest_text)
    if complete:
        if not _matches(
            directory / VERSION_NAME, (content_hash(version.encode("utf-8")),)
        ):
            write_text_atomic(directory / VERSION_NAME, version)
    return InstallFilesResult(
        tuple(written), tuple(removed), tuple(preserved), complete
    )


def source_status(directory: Path, expected: dict[str, str]) -> str | None:
    """A version stamp alone cannot prove source identity or a complete update."""
    manifest = read_manifest(directory)
    if manifest is None:
        return "source unverified (no valid per-file ownership manifest)"
    if not manifest.get("complete"):
        return "customized or incomplete (preserved files need review)"
    if manifest.get("package_source_sha256") != package_source_hash():
        return "CLI source differs from the package that prepared these skills"
    if manifest.get("source_sha256") != source_hash(expected):
        return "skill source differs despite its version stamp"
    for name, text in expected.items():
        if not _matches(
            _plain_target(directory, name), (content_hash(text.encode("utf-8")),)
        ):
            return "installed content changed or is unreadable"
    return None


def remove_family(directory: Path, *, family: str | None = None) -> tuple[str, ...]:
    """Remove proven unchanged files; retain edits, unknowns and their baselines."""
    if (directory / MANIFEST_NAME).exists() and read_manifest(directory) is None:
        return ()
    baselines = _baselines(directory, family=family)
    removed: list[str] = []
    survivors = False
    for relative, hashes in baselines.items():
        target = _plain_target(directory, relative)
        if _matches(target, hashes):
            target.unlink()
            removed.append(relative)
        elif target is None or target.exists():
            survivors = True
    if baselines and not survivors:
        for name in (MANIFEST_NAME, VERSION_NAME):
            target = directory / name
            if target.is_file() and not _is_link(target):
                target.unlink()
    if directory.is_dir() and not _is_link(directory):
        parents = {
            parent
            for relative in removed
            for parent in (directory / relative).parents
            if parent != directory and directory in parent.parents
        }
        for child in sorted(parents, key=lambda p: len(p.parts), reverse=True):
            if child.is_dir() and not _is_link(child):
                try:
                    child.rmdir()
                except OSError:
                    pass
        try:
            directory.rmdir()
        except OSError:
            pass
    return tuple(removed)
