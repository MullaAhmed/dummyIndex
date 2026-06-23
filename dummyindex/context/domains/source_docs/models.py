"""Frozen dataclasses: DocEntry + DocCatalog."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from dummyindex.context.enums import DocConfidence

from .constants import SCHEMA_VERSION


@dataclass(frozen=True)
class DocEntry:
    path: str  # repo-relative POSIX path (or absolute for external)
    abs_path: str  # absolute path on disk (audit trail for external docs)
    doc_type: str  # markdown / rst / pdf / html / docx / xlsx / txt
    title: str | None
    headings: tuple[str, ...]
    sha256: str
    size_bytes: int
    mtime: float
    age_delta_seconds: float | None  # mtime(doc) - newest code mtime; None if no code
    age_bucket: str
    referenced_count: int
    broken_refs: tuple[str, ...]
    broken_ratio: float
    confidence: str  # "high" | "medium" | "low"
    is_external: bool  # came from --docs PATH outside the repo
    source_root: str  # POSIX absolute of the discovery root that found this

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "abs_path": self.abs_path,
            "doc_type": self.doc_type,
            "title": self.title,
            "headings": list(self.headings),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mtime": self.mtime,
            "age_delta_seconds": self.age_delta_seconds,
            "age_bucket": self.age_bucket,
            "referenced_count": self.referenced_count,
            "broken_refs": list(self.broken_refs),
            "broken_ratio": round(self.broken_ratio, 4),
            "confidence": self.confidence,
            "is_external": self.is_external,
            "source_root": self.source_root,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DocEntry:
        return cls(
            path=str(payload.get("path", "")),
            abs_path=str(payload.get("abs_path", "")),
            doc_type=str(payload.get("doc_type", "markdown")),
            title=payload.get("title"),
            headings=tuple(payload.get("headings", ())),
            sha256=str(payload.get("sha256", "")),
            size_bytes=int(payload.get("size_bytes", 0)),
            mtime=float(payload.get("mtime", 0.0)),
            age_delta_seconds=(
                None
                if payload.get("age_delta_seconds") is None
                else float(payload["age_delta_seconds"])
            ),
            age_bucket=str(payload.get("age_bucket", "unknown")),
            referenced_count=int(payload.get("referenced_count", 0)),
            broken_refs=tuple(payload.get("broken_refs", ())),
            broken_ratio=float(payload.get("broken_ratio", 0.0)),
            confidence=str(payload.get("confidence", DocConfidence.MEDIUM)),
            is_external=bool(payload.get("is_external", False)),
            source_root=str(payload.get("source_root", "")),
        )


@dataclass(frozen=True)
class DocCatalog:
    schema_version: int
    generated_at: str
    repo_root: str
    docs: tuple[DocEntry, ...]
    extra_doc_roots: tuple[str, ...] = ()
    default_discovery_used: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "repo_root": self.repo_root,
            "default_discovery_used": self.default_discovery_used,
            "extra_doc_roots": list(self.extra_doc_roots),
            "doc_count": len(self.docs),
            "by_confidence": _confidence_breakdown(self.docs),
            "docs": [d.to_dict() for d in self.docs],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DocCatalog:
        return cls(
            schema_version=int(payload.get("schema_version", SCHEMA_VERSION)),
            generated_at=str(payload.get("generated_at", "")),
            repo_root=str(payload.get("repo_root", "")),
            docs=tuple(DocEntry.from_dict(d) for d in payload.get("docs", [])),
            extra_doc_roots=tuple(payload.get("extra_doc_roots", ())),
            default_discovery_used=bool(payload.get("default_discovery_used", True)),
        )


def _confidence_breakdown(docs: Iterable[DocEntry]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for d in docs:
        counts[d.confidence] = counts.get(d.confidence, 0) + 1
    return counts
