"""Frozen dataclasses for the equip flow + the generated-file sentinel.

Data only; behaviour lives in the sibling detect/render/manifest/safety modules.
:class:`StackProfile` is derived from ``.context/map/files.json``;
:class:`EquipmentManifest` is the ``.context/equipment.json`` payload.
``GENERATED_SENTINEL`` marks every generated ``.md`` so a later run regenerates
only its own output, never clobbering a user-authored file at the same path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import SCHEMA_VERSION
from .enums import EquipmentKind, EquipmentSource

# Marker embedded in every generated `.md`. A markdown comment, so it is
# invisible in the rendered file yet greppable for the never-clobber check.
GENERATED_SENTINEL = "<!-- dummyindex:generated -->"

__all__ = [
    "GENERATED_SENTINEL",
    "SCHEMA_VERSION",
    "AdoptSpec",
    "CatalogDecision",
    "EquipmentItem",
    "EquipmentManifest",
    "GenerateSpec",
    "HookSpec",
    "StackProfile",
]


@dataclass(frozen=True)
class StackProfile:
    """The repo's dominant stack + its detected toolchain.

    ``label`` + ``frameworks`` come from ``map/files.json`` and the manifests;
    the eight toolchain fields are derived from the same raw-manifest token scan
    (no TOML/JSON parsing). Each ``*_command`` is the literal shell command a
    generated tool runs; ``None`` everywhere when nothing was detected, so equip
    still produces a usable (if untuned) toolkit on a fresh repo.
    """

    label: str  # e.g. "python" / "typescript" / "generic"
    frameworks: tuple[str, ...] = ()  # detected framework labels, most-common first
    formatter: str | None = None  # "ruff" | "black" | "prettier"
    format_command: str | None = None
    test_runner: str | None = None  # "pytest" | "jest" | "vitest" | "go test" | ...
    test_command: str | None = None
    linter: str | None = None  # "ruff" | "eslint"
    lint_command: str | None = None
    type_checker: str | None = None  # "mypy" | "pyright" | "tsc"
    typecheck_command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "frameworks": list(self.frameworks),
            "formatter": self.formatter,
            "format_command": self.format_command,
            "test_runner": self.test_runner,
            "test_command": self.test_command,
            "linter": self.linter,
            "lint_command": self.lint_command,
            "type_checker": self.type_checker,
            "typecheck_command": self.typecheck_command,
        }


@dataclass(frozen=True)
class EquipmentItem:
    """One tuned tool equip rendered (or recorded, for the format hook).

    The v2 fields (``subagent_type`` / ``version`` / ``origin_hash``) default to
    ``None`` so a v1 entry loads. ``subagent_type`` is the build skill's dispatch
    target. On generated files, ``version`` + ``origin_hash`` drive the
    hash-baselined lifecycle (refresh/reset/patch); hooks and adoptions leave
    them ``None``.
    """

    kind: EquipmentKind
    name: str
    path: str  # repo-relative POSIX path
    source: EquipmentSource
    capabilities: tuple[str, ...] = ()
    grounded_in: tuple[str, ...] = ()
    # Canary metadata: convention substrings a generated tool must preserve.
    # Omitted from to_dict when empty so v3 manifests stay byte-identical.
    invariants: tuple[str, ...] = ()
    subagent_type: str | None = None
    version: str | None = None
    origin_hash: str | None = None
    # v3 origin fields, set only on MARKETPLACE / VENDORED items: where a
    # discovered item came from and how it was wired. ``None`` lets v2 load.
    marketplace: str | None = None  # source marketplace name
    origin_repo: str | None = None  # "owner/repo" the item came from
    origin_ref: str | None = None  # pinned commit sha (supply-chain)
    mechanism: str | None = None  # InstallMechanism value: "native" | "vendor"
    capability_id: str | None = None
    package_version: str | None = None
    package_source: str | None = None
    package_sha256: str | None = None
    required_tools: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()
    qualification_refs: tuple[str, ...] = ()
    project_binding: dict[str, Any] = field(default_factory=dict)
    # Specialist dimension ("procedure" | "domain"); None for legacy entries.
    dimension: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "source": self.source,
            "capabilities": list(self.capabilities),
            "grounded_in": list(self.grounded_in),
            "subagent_type": self.subagent_type,
            "version": self.version,
            "origin_hash": self.origin_hash,
            "marketplace": self.marketplace,
            "origin_repo": self.origin_repo,
            "origin_ref": self.origin_ref,
            "mechanism": self.mechanism,
        }
        # Omit when empty so a v3 manifest stays byte-identical.
        if self.invariants:
            data["invariants"] = list(self.invariants)
        for name in (
            "capability_id",
            "package_version",
            "package_source",
            "package_sha256",
        ):
            if getattr(self, name) is not None:
                data[name] = getattr(self, name)
        for name in ("required_tools", "triggers", "qualification_refs"):
            if getattr(self, name):
                data[name] = list(getattr(self, name))
        if self.project_binding:
            data["project_binding"] = self.project_binding
        if self.dimension is not None:
            data["dimension"] = self.dimension
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EquipmentItem:
        sub = data.get("subagent_type")
        ver = data.get("version")
        oh = data.get("origin_hash")
        mkt = data.get("marketplace")
        repo = data.get("origin_repo")
        ref = data.get("origin_ref")
        mech = data.get("mechanism")
        return cls(
            kind=EquipmentKind(data["kind"]),
            name=str(data["name"]),
            path=str(data["path"]),
            source=EquipmentSource(data["source"]),
            capabilities=tuple(str(c) for c in data.get("capabilities", [])),
            grounded_in=tuple(str(g) for g in data.get("grounded_in", [])),
            invariants=tuple(str(i) for i in data.get("invariants", [])),
            subagent_type=str(sub) if sub is not None else None,
            version=str(ver) if ver is not None else None,
            origin_hash=str(oh) if oh is not None else None,
            marketplace=str(mkt) if mkt is not None else None,
            origin_repo=str(repo) if repo is not None else None,
            origin_ref=str(ref) if ref is not None else None,
            mechanism=str(mech) if mech is not None else None,
            **{
                name: str(data[name]) if data.get(name) is not None else None
                for name in (
                    "capability_id",
                    "package_version",
                    "package_source",
                    "package_sha256",
                )
            },
            **{
                name: tuple(str(value) for value in data.get(name, []))
                for name in ("required_tools", "triggers", "qualification_refs")
            },
            project_binding=dict(data["project_binding"])
            if isinstance(data.get("project_binding"), dict)
            else {},
            dimension=str(data["dimension"])
            if data.get("dimension") is not None
            else None,
        )


@dataclass(frozen=True)
class AdoptSpec:
    """One specialist equip *adopts* rather than generates (manifest-only).

    Adoption never writes a file: a project agent already exists under
    ``.claude/agents/`` (``path`` points at it), and a registry specialist has no
    project file (``path=""``). ``subagent_type`` is the build skill's dispatch
    target: the agent's file stem, or the registry member's exact global name.
    """

    name: str
    subagent_type: str
    capabilities: tuple[str, ...]
    source: EquipmentSource = EquipmentSource.INSTALLED
    path: str = ""


@dataclass(frozen=True)
class GenerateSpec:
    """One tool the catalog decided equip should *generate* (render + write).

    ``template`` is the shipped ``*.md.tmpl`` filename; ``rel_path`` is the
    repo-relative target. ``grounding_docs`` are extra ``.context/`` docs a
    *specialist* cites: they enrich the manifest's ``grounded_in`` only, never
    the rendered bytes, so they never affect the origin hash. The core four
    leave it empty.
    """

    name: str
    kind: EquipmentKind
    template: str
    capabilities: tuple[str, ...]
    rel_path: str
    grounding_docs: tuple[str, ...] = ()
    dimension: str | None = None


@dataclass(frozen=True)
class HookSpec:
    """One settings.json hook entry the catalog decided equip should wire."""

    name: str
    event: str
    matcher: str
    command: str


@dataclass(frozen=True)
class CatalogDecision:
    """The full equip decision: what to generate, adopt, and wire."""

    generate: tuple[GenerateSpec, ...] = ()
    adopt: tuple[AdoptSpec, ...] = ()
    hooks: tuple[HookSpec, ...] = ()


@dataclass(frozen=True)
class EquipmentManifest:
    """The ``.context/equipment.json`` payload."""

    schema_version: int
    items: tuple[EquipmentItem, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EquipmentManifest:
        raw_items = data.get("items", [])
        items = tuple(
            EquipmentItem.from_dict(i) for i in raw_items if isinstance(i, dict)
        )
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            items=items,
        )
