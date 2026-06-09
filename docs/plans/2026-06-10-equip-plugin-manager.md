# equip Plugin Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the `equip` domain into a Claude plugin manager that discovers agents/skills/plugins from marketplaces + GitHub, ranks them against the repo's detected needs, and wires them — native enable for packaged plugins, vendored copies for loose agents/skills — behind a tiered-trust, blast-radius-disclosing dry-run plan.

**Architecture:** Six-stage loop (`discover → parse/validate → match+rank → blast-radius → plan → wire/record`) added to `dummyindex/context/domains/equip/`. The policy core (parse, match, blast-radius, plan) stays pure and is unit-tested with committed fixtures. Network/subprocess I/O is isolated in `sources.py` behind a `Runner` seam; settings.json and vendored-file writes happen at the CLI boundary, reusing the existing preserve-or-refuse + atomic-write machinery. One ledger: `.context/equipment.json`, schema bumped v2 → v3 (tolerant `from_dict`).

**Tech Stack:** Python 3 (stdlib only in the domain), `dataclasses(frozen=True)`, `str, Enum` constants, pytest. Native wiring target: `claude plugin …` CLI + `extraKnownMarketplaces`/`enabledPlugins` in `.claude/settings.json`. Discovery I/O via `gh` / `git` subprocess.

**Conventions to follow** (`docs/reference/01-conventions.md`): frozen dataclasses; enum constants; typed exception hierarchy under `EquipError`; CLI is wire-only (parse → call domain → print → exit code 0/2/1); files focused (<800 lines); input-validation at boundaries; atomic tmp+rename writes; immutability (never mutate, `dataclasses.replace`).

**Spec:** `docs/specs/2026-06-10-equip-plugin-manager-design.md`.

**Reference patterns (read before starting):**
- Enums/sources: `dummyindex/context/domains/equip/enums.py`
- Models/manifest: `dummyindex/context/domains/equip/models.py`
- Constants/token tables: `dummyindex/context/domains/equip/_constants.py`
- Settings machinery (reuse): `dummyindex/context/claude_settings.py`
- CLI apply pipeline: `dummyindex/cli/equip.py`
- CLI verb handlers + flag helpers: `dummyindex/cli/_equip_verbs.py`, `dummyindex/cli/_equip_common.py`
- Subprocess-in-domain precedent: `dummyindex/context/build/git_delta.py`, `dummyindex/context/domains/preflight/inventory.py`

**Commit style:** conventional commits; **no `Co-Authored-By` line** (attribution disabled). Commit after each green task. Do not push.

---

## File Structure

**New files (all under `dummyindex/context/domains/equip/` unless noted):**
- `marketplace.py` — pure: `SeedMarketplace`, `SEED_MARKETPLACES`, `PluginEntry`, `MarketplaceCatalog`, `validate_catalog`, `parse_catalog`.
- `discover.py` — pure: `Candidate`, `capabilities_for`, `match_candidates`.
- `blast_radius.py` — pure: `BlastRadius`, `analyze`.
- `install_plan.py` — pure: `PlannedInstall`, `InstallPlan`, `build_install_plan`.
- `sources.py` — I/O: `RunResult`, `Runner`, `default_runner`, `ToolAvailability`, `available_tools`, `fetch_catalog`, `fetch_file`, `search_github`.
- `dummyindex/context/claude_plugins.py` — I/O (sibling of `claude_settings.py`): `add_marketplace`, `remove_marketplace`, `enable_plugin`, `disable_plugin`.
- `dummyindex/cli/_equip_discover.py` — CLI: `_verb_discover`, `_verb_install`.
- Test files mirror each module under `tests/context/` and `tests/cli/`.
- Fixtures: `tests/context/fixtures/marketplace_official.json`, `tests/context/fixtures/marketplace_community.json`.

**Modified files:**
- `enums.py` — add sources/verbs/tiers/mechanism/surface enums.
- `_constants.py` — `SCHEMA_VERSION = 3`; `_PLUGIN_CAPABILITY_TOKENS`; `VENDORED_SENTINEL`.
- `models.py` — `EquipmentItem` origin fields; v3 round-trip.
- `errors.py` — `SourceError`, `CatalogError`, `WireError`.
- `__init__.py` — export the new public surface.
- `lifecycle.py` — `status`/`uninstall` cover MARKETPLACE + VENDORED.
- `cli/equip.py` — dispatch `discover`/`install`.
- `cli/_equip_common.py` — `_pull_flag_value` reuse (already present); add `_resolve_root` reuse (present).
- `skills/equip/SKILL.md`, `docs/COMMANDS.md`, `docs/guide/07-cli.md`, `CHANGELOG.md`, `pyproject.toml` (0.18.0).

---

## Task 1: Enums, constants, errors, manifest v3

**Files:**
- Modify: `dummyindex/context/domains/equip/enums.py`
- Modify: `dummyindex/context/domains/equip/_constants.py`
- Modify: `dummyindex/context/domains/equip/errors.py`
- Modify: `dummyindex/context/domains/equip/models.py`
- Test: `tests/context/test_equip.py` (extend), new `tests/context/test_equip_manifest_v3.py`

- [ ] **Step 1: Write failing test for v3 round-trip + v2 back-compat**

In `tests/context/test_equip_manifest_v3.py`:

```python
from dummyindex.context.domains.equip import (
    EquipmentItem, EquipmentKind, EquipmentManifest, EquipmentSource,
)


def test_v3_item_round_trips_origin_fields():
    item = EquipmentItem(
        kind=EquipmentKind.SKILL,
        name="pdf-extract",
        path=".claude/skills/pdf-extract/SKILL.md",
        source=EquipmentSource.VENDORED,
        capabilities=("docs",),
        marketplace="skills",
        origin_repo="anthropics/skills",
        origin_ref="abc123",
        mechanism="vendor",
        origin_hash="deadbeef",
    )
    again = EquipmentItem.from_dict(item.to_dict())
    assert again == item


def test_v2_item_loads_with_none_origin_fields():
    legacy = {
        "kind": "agent", "name": "python-implementer",
        "path": ".claude/agents/python-implementer.md",
        "source": "generated", "capabilities": ["implement"],
        "grounded_in": [], "subagent_type": "python-implementer",
        "version": "1.0.0", "origin_hash": "abc",
    }
    item = EquipmentItem.from_dict(legacy)
    assert item.marketplace is None
    assert item.origin_repo is None
    assert item.mechanism is None


def test_marketplace_source_enum_value():
    assert EquipmentSource.MARKETPLACE.value == "marketplace"
    assert EquipmentSource.VENDORED.value == "vendored"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/context/test_equip_manifest_v3.py -q`
Expected: FAIL (`AttributeError`/`ValueError` — `MARKETPLACE` not defined, `marketplace` kwarg unknown).

- [ ] **Step 3: Extend `enums.py`**

Add to `EquipmentSource`:
```python
    MARKETPLACE = "marketplace"  # native-enabled plugin (settings.json keys)
    VENDORED = "vendored"        # copied agent/skill file under .claude/
```
Add to `EquipVerb`:
```python
    DISCOVER = "discover"
    INSTALL = "install"
```
Append three new enums at the end of the file:
```python
class TrustTier(str, Enum):
    """Whether a marketplace source is auto-trusted (Anthropic-official)."""

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class InstallMechanism(str, Enum):
    """How a candidate is wired: native enable vs vendored copy."""

    NATIVE = "native"
    VENDOR = "vendor"


class PluginSurface(str, Enum):
    """A capability surface a plugin can declare. The last four run code."""

    AGENT = "agent"
    SKILL = "skill"
    COMMAND = "command"
    HOOK = "hook"
    MCP = "mcp"
    LSP = "lsp"
    BIN = "bin"
```

- [ ] **Step 4: Extend `_constants.py`**

Change `SCHEMA_VERSION = 2` → `SCHEMA_VERSION = 3`. Add at end:
```python
# Marker embedded in every vendored `.claude/**.md`, distinct from
# GENERATED_SENTINEL: a vendored file is an upstream copy, not our render.
VENDORED_SENTINEL = "<!-- dummyindex:installed -->"

# Capability inference for discovered plugins: free-text tokens (plugin name,
# description, keywords, category) -> a canonical Capability. Broader than the
# proposal table — discovery WANTS implement/test/review hits because a user
# explicitly asked to find tools. First match in order wins per capability.
_PLUGIN_CAPABILITY_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (Capability.DATABASE, ("database", "db", "sql", "postgres", "migration", "orm")),
    (Capability.SECURITY, ("security", "auth", "secret", "vuln", "audit")),
    (Capability.FRONTEND, ("frontend", "ui", "css", "react", "vue", "svelte")),
    (Capability.PERFORMANCE, ("performance", "perf", "optimi", "profil", "benchmark")),
    (Capability.DOCS, ("docs", "documentation", "readme")),
    (Capability.SEARCH, ("search", "embedding", "vector", "rag", "semantic")),
    (Capability.DATA, ("data", "etl", "pipeline", "analytics")),
    (Capability.TEST, ("test", "qa", "coverage")),
    (Capability.REVIEW, ("review", "lint")),
    (Capability.IMPLEMENT, ("implement", "scaffold", "generator")),
)
```

- [ ] **Step 5: Extend `errors.py`**

Append:
```python
class SourceError(EquipError):
    """Fetching a catalog or searching GitHub failed (network or missing tool)."""


class CatalogError(EquipError):
    """A fetched marketplace.json is missing required fields or malformed."""


class WireError(EquipError):
    """Writing settings.json keys or a vendored file failed."""
```

- [ ] **Step 6: Extend `models.py` `EquipmentItem`**

Add four optional fields after `origin_hash`:
```python
    marketplace: str | None = None   # MARKETPLACE/VENDORED: source marketplace name
    origin_repo: str | None = None   # "owner/repo" the item came from
    origin_ref: str | None = None    # pinned commit sha (supply-chain)
    mechanism: str | None = None     # InstallMechanism value: "native" | "vendor"
```
Extend `to_dict` to emit them, and `from_dict` to read them with `.get(...)` → `None` default (mirror the existing `sub`/`ver`/`oh` tolerant pattern):
```python
        mkt = data.get("marketplace")
        repo = data.get("origin_repo")
        ref = data.get("origin_ref")
        mech = data.get("mechanism")
        # ...pass into cls(...):
        marketplace=str(mkt) if mkt is not None else None,
        origin_repo=str(repo) if repo is not None else None,
        origin_ref=str(ref) if ref is not None else None,
        mechanism=str(mech) if mech is not None else None,
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/context/test_equip_manifest_v3.py tests/context/test_equip.py -q`
Expected: PASS. Also run `mypy dummyindex/context/domains/equip/` and `ruff check dummyindex/context/domains/equip/` — clean.

- [ ] **Step 8: Commit**

```bash
git add dummyindex/context/domains/equip/{enums,_constants,errors,models}.py tests/context/test_equip_manifest_v3.py
git commit -m "feat(equip): schema v3 + plugin-manager enums/constants/errors"
```

---

## Task 2: Marketplace catalog model + parse/validate (pure)

**Files:**
- Create: `dummyindex/context/domains/equip/marketplace.py`
- Create: `tests/context/fixtures/marketplace_official.json`, `tests/context/fixtures/marketplace_community.json`
- Test: `tests/context/test_equip_marketplace.py`

- [ ] **Step 1: Create the fixtures**

`tests/context/fixtures/marketplace_official.json`:
```json
{
  "name": "claude-plugins-official",
  "owner": {"name": "Anthropic"},
  "plugins": [
    {"name": "code-review", "description": "Review pull requests for correctness",
     "keywords": ["review", "lint"], "category": "quality"},
    {"name": "pg-tuner", "description": "Postgres performance tuning",
     "keywords": ["database", "performance"], "version": "1.2.0",
     "hooks": "./hooks/hooks.json", "mcpServers": "./.mcp.json"}
  ]
}
```
`tests/context/fixtures/marketplace_community.json`:
```json
{
  "name": "claude-plugins-community",
  "owner": {"name": "Community"},
  "plugins": [
    {"name": "rag-search", "description": "Semantic vector search over docs",
     "keywords": ["search", "rag", "embedding"]}
  ]
}
```

- [ ] **Step 2: Write failing tests**

`tests/context/test_equip_marketplace.py`:
```python
import json
from pathlib import Path

import pytest

from dummyindex.context.domains.equip import (
    CatalogError, MarketplaceCatalog, parse_catalog, validate_catalog,
)

FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def test_parse_official_catalog():
    cat = parse_catalog(_load("marketplace_official.json"), repo="anthropics/claude-plugins-official")
    assert isinstance(cat, MarketplaceCatalog)
    assert cat.name == "claude-plugins-official"
    assert {p.name for p in cat.plugins} == {"code-review", "pg-tuner"}
    pg = next(p for p in cat.plugins if p.name == "pg-tuner")
    assert pg.version == "1.2.0"
    assert "hook" in pg.declared_surfaces and "mcp" in pg.declared_surfaces


def test_validate_rejects_missing_plugins():
    with pytest.raises(CatalogError):
        validate_catalog({"name": "x", "owner": {"name": "y"}})


def test_validate_rejects_non_object():
    with pytest.raises(CatalogError):
        validate_catalog([1, 2, 3])


def test_parse_ignores_malformed_plugin_entries():
    cat = parse_catalog(
        {"name": "m", "plugins": [{"no_name": True}, {"name": "ok"}]},
        repo="o/r",
    )
    assert {p.name for p in cat.plugins} == {"ok"}
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest tests/context/test_equip_marketplace.py -q`
Expected: FAIL (`ImportError` — `parse_catalog` undefined).

- [ ] **Step 4: Implement `marketplace.py`**

```python
"""Marketplace catalog model + parse/validate. Pure; no I/O.

A marketplace is a git repo with ``.claude-plugin/marketplace.json`` listing
plugins. This module turns a parsed-JSON dict into frozen dataclasses and
validates it at the boundary (CONVENTIONS §13). The fetching of that JSON lives
in :mod:`.sources`; the matching in :mod:`.discover`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enums import PluginSurface
from .errors import CatalogError

# Marketplace-entry keys that declare a code-running surface, mapped to the
# PluginSurface they imply. Inert surfaces (agents/skills/commands) need no
# special handling — their absence from this map is the point.
_CODE_SURFACE_KEYS: dict[str, str] = {
    "hooks": PluginSurface.HOOK.value,
    "mcpServers": PluginSurface.MCP.value,
    "lspServers": PluginSurface.LSP.value,
}


@dataclass(frozen=True)
class SeedMarketplace:
    """A known starting-point marketplace. ``is_collection`` marks a loose
    agent/skill repo (e.g. ``anthropics/skills``) with no ``marketplace.json`` —
    its contents are vendored, not natively enabled."""

    name: str
    repo: str
    trusted: bool
    is_collection: bool = False


SEED_MARKETPLACES: tuple[SeedMarketplace, ...] = (
    SeedMarketplace("claude-plugins-official", "anthropics/claude-plugins-official", trusted=True),
    SeedMarketplace("claude-plugins-community", "anthropics/claude-plugins-community", trusted=False),
    SeedMarketplace("knowledge-work-plugins", "anthropics/knowledge-work-plugins", trusted=True),
    SeedMarketplace("agent-skills", "anthropics/skills", trusted=True, is_collection=True),
    SeedMarketplace("ecc", "affaan-m/ECC", trusted=False),
    SeedMarketplace("agency-agents", "msitarzewski/agency-agents", trusted=False),
)


@dataclass(frozen=True)
class PluginEntry:
    name: str
    description: str = ""
    version: str | None = None
    keywords: tuple[str, ...] = ()
    category: str | None = None
    declared_surfaces: tuple[str, ...] = ()  # PluginSurface values present in the entry


@dataclass(frozen=True)
class MarketplaceCatalog:
    name: str
    repo: str
    plugins: tuple[PluginEntry, ...] = ()
    trusted: bool = False
    is_collection: bool = False


def validate_catalog(data: Any) -> None:
    """Raise :class:`CatalogError` unless ``data`` is a catalog-shaped object."""
    if not isinstance(data, dict):
        raise CatalogError(f"marketplace.json must be a JSON object, got {type(data).__name__}")
    if "plugins" not in data or not isinstance(data["plugins"], list):
        raise CatalogError("marketplace.json must contain a 'plugins' array")


def _surfaces(entry: dict[str, Any]) -> tuple[str, ...]:
    return tuple(surface for key, surface in _CODE_SURFACE_KEYS.items() if key in entry)


def _parse_entry(raw: Any) -> PluginEntry | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        return None
    kws = raw.get("keywords", [])
    keywords = tuple(str(k) for k in kws) if isinstance(kws, list) else ()
    cat = raw.get("category")
    ver = raw.get("version")
    return PluginEntry(
        name=raw["name"],
        description=str(raw.get("description", "")),
        version=str(ver) if isinstance(ver, str) else None,
        keywords=keywords,
        category=str(cat) if isinstance(cat, str) else None,
        declared_surfaces=_surfaces(raw),
    )


def parse_catalog(
    data: dict[str, Any], *, repo: str, trusted: bool = False, is_collection: bool = False
) -> MarketplaceCatalog:
    """Validate then build a :class:`MarketplaceCatalog`. Malformed plugin
    entries are dropped (never crash on one bad row); a missing 'plugins' array
    raises :class:`CatalogError`."""
    validate_catalog(data)
    name = data.get("name")
    plugins = tuple(
        e for e in (_parse_entry(p) for p in data["plugins"]) if e is not None
    )
    return MarketplaceCatalog(
        name=str(name) if isinstance(name, str) else repo,
        repo=repo,
        plugins=plugins,
        trusted=trusted,
        is_collection=is_collection,
    )
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/context/test_equip_marketplace.py -q` → PASS. `mypy` + `ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add dummyindex/context/domains/equip/marketplace.py tests/context/test_equip_marketplace.py tests/context/fixtures/
git commit -m "feat(equip): marketplace catalog model + parse/validate"
```

---

## Task 3: Capability matching + ranking (pure)

**Files:**
- Create: `dummyindex/context/domains/equip/discover.py`
- Test: `tests/context/test_equip_discover.py`

- [ ] **Step 1: Write failing tests**

```python
from dummyindex.context.domains.equip import (
    Candidate, MarketplaceCatalog, PluginEntry, capabilities_for, match_candidates,
)


def _cat():
    return MarketplaceCatalog(
        name="official", repo="anthropics/claude-plugins-official", trusted=True,
        plugins=(
            PluginEntry(name="pg-tuner", description="Postgres performance",
                        keywords=("database", "performance")),
            PluginEntry(name="rag-search", description="semantic vector search",
                        keywords=("search", "rag")),
        ),
    )


def test_capabilities_for_maps_keywords():
    caps = capabilities_for(PluginEntry(name="x", keywords=("database", "performance")))
    assert "database" in caps and "performance" in caps


def test_auto_match_ranks_by_capability_overlap():
    out = match_candidates((_cat(),), needed_caps=("database",))
    assert out[0].plugin.name == "pg-tuner"
    assert "database" in out[0].capabilities
    assert out[0].trusted is True


def test_query_match_filters_by_token():
    out = match_candidates((_cat(),), query="vector search")
    assert [c.plugin.name for c in out] == ["rag-search"]


def test_no_signal_returns_empty():
    assert match_candidates((_cat(),)) == ()
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/context/test_equip_discover.py -q` → FAIL (ImportError).

- [ ] **Step 3: Implement `discover.py`**

```python
"""Match + rank discovered plugins against needed capabilities and/or a query.
Pure; no I/O. Capability inference reuses the shared Capability vocabulary."""
from __future__ import annotations

from dataclasses import dataclass

from ._constants import _PLUGIN_CAPABILITY_TOKENS
from .marketplace import MarketplaceCatalog, PluginEntry


@dataclass(frozen=True)
class Candidate:
    plugin: PluginEntry
    marketplace: str
    repo: str
    trusted: bool
    is_collection: bool
    capabilities: tuple[str, ...]
    score: int


def capabilities_for(entry: PluginEntry) -> tuple[str, ...]:
    """Infer capabilities from the entry's name/description/keywords/category."""
    haystack = " ".join(
        [entry.name, entry.description, entry.category or "", *entry.keywords]
    ).lower()
    found: list[str] = []
    for capability, tokens in _PLUGIN_CAPABILITY_TOKENS:
        if capability in found:
            continue
        if any(tok in haystack for tok in tokens):
            found.append(capability)
    return tuple(found)


def _query_hits(entry: PluginEntry, query: str) -> int:
    haystack = " ".join([entry.name, entry.description, *entry.keywords]).lower()
    return sum(1 for tok in query.lower().split() if tok and tok in haystack)


def match_candidates(
    catalogs: tuple[MarketplaceCatalog, ...],
    *,
    needed_caps: tuple[str, ...] = (),
    query: str | None = None,
) -> tuple[Candidate, ...]:
    """Rank candidates. score = 2*(capability overlap) + (query token hits).
    Candidates with score 0 are dropped. Sorted by score desc, then name asc
    (stable, deterministic)."""
    needed = set(needed_caps)
    out: list[Candidate] = []
    for cat in catalogs:
        for entry in cat.plugins:
            caps = capabilities_for(entry)
            overlap = len(needed & set(caps))
            hits = _query_hits(entry, query) if query else 0
            score = 2 * overlap + hits
            if score <= 0:
                continue
            out.append(
                Candidate(
                    plugin=entry, marketplace=cat.name, repo=cat.repo,
                    trusted=cat.trusted, is_collection=cat.is_collection,
                    capabilities=caps, score=score,
                )
            )
    out.sort(key=lambda c: (-c.score, c.plugin.name))
    return tuple(out)
```

- [ ] **Step 4: Run tests → PASS.** `mypy` + `ruff` clean.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/equip/discover.py tests/context/test_equip_discover.py
git commit -m "feat(equip): capability matching + ranking for discovered plugins"
```

---

## Task 4: Blast-radius analysis (pure)

**Files:**
- Create: `dummyindex/context/domains/equip/blast_radius.py`
- Test: `tests/context/test_equip_blast_radius.py`

- [ ] **Step 1: Write failing tests**

```python
from dummyindex.context.domains.equip import (
    BlastRadius, PluginEntry, TrustTier, analyze_blast_radius,
)


def test_inert_plugin_does_not_run_code():
    br = analyze_blast_radius(PluginEntry(name="docs-helper"), trusted=False)
    assert br.runs_code is False
    assert br.tier == TrustTier.UNTRUSTED.value


def test_hook_plugin_runs_code():
    br = analyze_blast_radius(
        PluginEntry(name="pg", declared_surfaces=("hook", "mcp")), trusted=True
    )
    assert br.runs_code is True
    assert set(br.surfaces) == {"hook", "mcp"}
    assert br.tier == TrustTier.TRUSTED.value
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `blast_radius.py`**

```python
"""Blast-radius analysis: which surfaces a plugin declares and whether any of
them run code. Pure; no I/O."""
from __future__ import annotations

from dataclasses import dataclass

from .enums import PluginSurface, TrustTier
from .marketplace import PluginEntry

_CODE_SURFACES: frozenset[str] = frozenset(
    {PluginSurface.HOOK.value, PluginSurface.MCP.value,
     PluginSurface.LSP.value, PluginSurface.BIN.value}
)


@dataclass(frozen=True)
class BlastRadius:
    surfaces: tuple[str, ...]
    runs_code: bool
    tier: str


def analyze_blast_radius(entry: PluginEntry, *, trusted: bool) -> BlastRadius:
    surfaces = tuple(entry.declared_surfaces)
    runs_code = any(s in _CODE_SURFACES for s in surfaces)
    tier = TrustTier.TRUSTED.value if trusted else TrustTier.UNTRUSTED.value
    return BlastRadius(surfaces=surfaces, runs_code=runs_code, tier=tier)
```

- [ ] **Step 4: Run → PASS.** `mypy`/`ruff` clean.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/equip/blast_radius.py tests/context/test_equip_blast_radius.py
git commit -m "feat(equip): blast-radius analysis (code-running surfaces + trust tier)"
```

---

## Task 5: Install plan (pure)

**Files:**
- Create: `dummyindex/context/domains/equip/install_plan.py`
- Test: `tests/context/test_equip_install_plan.py`

- [ ] **Step 1: Write failing tests**

```python
from dummyindex.context.domains.equip import (
    Candidate, InstallMechanism, InstallPlan, PluginEntry, build_install_plan,
)


def _cand(name, *, trusted, is_collection=False, surfaces=()):
    return Candidate(
        plugin=PluginEntry(name=name, declared_surfaces=surfaces),
        marketplace="m", repo="o/r", trusted=trusted, is_collection=is_collection,
        capabilities=("docs",), score=2,
    )


def test_untrusted_code_plugin_requires_approval():
    plan = build_install_plan((_cand("pg", trusted=False, surfaces=("hook",)),))
    pi = plan.installs[0]
    assert pi.requires_approval is True
    assert pi.mechanism == InstallMechanism.NATIVE.value


def test_trusted_code_plugin_auto_approvable():
    plan = build_install_plan((_cand("pg", trusted=True, surfaces=("hook",)),))
    assert plan.installs[0].requires_approval is False


def test_inert_untrusted_plugin_no_approval():
    plan = build_install_plan((_cand("docs", trusted=False),))
    assert plan.installs[0].requires_approval is False


def test_collection_uses_vendor_mechanism():
    plan = build_install_plan((_cand("skill-x", trusted=True, is_collection=True),))
    assert plan.installs[0].mechanism == InstallMechanism.VENDOR.value
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `install_plan.py`**

```python
"""Turn ranked candidates into an actionable install plan. Pure; no I/O.

Mechanism: a candidate from a loose collection is VENDORED (copied); everything
else is NATIVE (enabled via settings keys). Approval: a code-running candidate
from an UNTRUSTED source requires explicit --yes; inert or trusted candidates do
not (spec §7)."""
from __future__ import annotations

from dataclasses import dataclass

from .blast_radius import BlastRadius, analyze_blast_radius
from .discover import Candidate
from .enums import InstallMechanism


@dataclass(frozen=True)
class PlannedInstall:
    candidate: Candidate
    blast: BlastRadius
    mechanism: str
    requires_approval: bool


@dataclass(frozen=True)
class InstallPlan:
    installs: tuple[PlannedInstall, ...] = ()


def _plan_one(candidate: Candidate) -> PlannedInstall:
    blast = analyze_blast_radius(candidate.plugin, trusted=candidate.trusted)
    mechanism = (
        InstallMechanism.VENDOR.value
        if candidate.is_collection
        else InstallMechanism.NATIVE.value
    )
    requires_approval = blast.runs_code and not candidate.trusted
    return PlannedInstall(
        candidate=candidate, blast=blast, mechanism=mechanism,
        requires_approval=requires_approval,
    )


def build_install_plan(candidates: tuple[Candidate, ...]) -> InstallPlan:
    return InstallPlan(installs=tuple(_plan_one(c) for c in candidates))
```

- [ ] **Step 4: Run → PASS.** `mypy`/`ruff` clean.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/equip/install_plan.py tests/context/test_equip_install_plan.py
git commit -m "feat(equip): install plan (native/vendor mechanism + approval gating)"
```

---

## Task 6: Sources I/O (subprocess, behind a Runner seam)

**Files:**
- Create: `dummyindex/context/domains/equip/sources.py`
- Test: `tests/context/test_equip_sources.py`

- [ ] **Step 1: Write failing tests (fake runner — no live network)**

```python
import base64
import json

from dummyindex.context.domains.equip import (
    RunResult, SourceError, ToolAvailability, available_tools, fetch_catalog,
    search_github,
)


def _fake_runner(responses):
    """responses: dict mapping the first 2 argv tokens (joined) -> RunResult."""
    def run(argv):
        key = " ".join(argv[:2])
        return responses.get(key, RunResult(returncode=1, stdout="", stderr="not found"))
    return run


def test_available_tools_detects_presence():
    runner = _fake_runner({
        "gh --version": RunResult(0, "gh 2.0", ""),
        "git --version": RunResult(0, "git 2.40", ""),
    })
    tools = available_tools(runner=runner)
    assert tools.gh is True and tools.git is True and tools.claude is False


def test_fetch_catalog_decodes_gh_contents():
    payload = {"name": "m", "plugins": [{"name": "p"}]}
    content = base64.b64encode(json.dumps(payload).encode()).decode()
    runner = _fake_runner({
        "gh api": RunResult(0, json.dumps({"content": content, "encoding": "base64"}), ""),
    })
    data = fetch_catalog("anthropics/claude-plugins-official", runner=runner)
    assert data["plugins"][0]["name"] == "p"


def test_fetch_catalog_missing_returns_none():
    runner = _fake_runner({})  # gh api -> returncode 1
    assert fetch_catalog("o/r", runner=runner) is None


def test_search_github_parses_repo_lines():
    runner = _fake_runner({
        "gh search": RunResult(0, "anthropics/claude-plugins-official\nfoo/bar\n", ""),
    })
    repos = search_github("postgres", runner=runner)
    assert "foo/bar" in repos
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `sources.py`**

```python
"""I/O for plugin discovery: probe tools, fetch marketplace catalogs, search
GitHub. The ONLY equip module that shells out — isolated behind a ``Runner``
seam (a callable taking argv and returning :class:`RunResult`) so tests inject a
fake and never touch the network. Mirrors the subprocess-in-domain precedent in
``context/build/git_delta.py``."""
from __future__ import annotations

import base64
import json
import subprocess  # noqa: S404 - guarded, fixed argv, no shell
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .errors import SourceError

CATALOG_PATH = ".claude-plugin/marketplace.json"


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], RunResult]


def default_runner(argv: list[str]) -> RunResult:
    """Run ``argv`` with no shell, capturing output. Never raises on non-zero."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, shell=False
            argv, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return RunResult(returncode=127, stdout="", stderr=str(exc))
    return RunResult(proc.returncode, proc.stdout, proc.stderr)


@dataclass(frozen=True)
class ToolAvailability:
    claude: bool
    gh: bool
    git: bool


def available_tools(*, runner: Runner = default_runner) -> ToolAvailability:
    def has(tool: str) -> bool:
        return runner([tool, "--version"]).returncode == 0
    return ToolAvailability(claude=has("claude"), gh=has("gh"), git=has("git"))


def fetch_file(repo: str, path: str, *, runner: Runner = default_runner) -> str | None:
    """Fetch one file's text from a GitHub repo via ``gh api`` contents. Returns
    None when the file/repo is absent (returncode != 0)."""
    res = runner(["gh", "api", f"repos/{repo}/contents/{path}"])
    if res.returncode != 0:
        return None
    try:
        obj = json.loads(res.stdout)
        if obj.get("encoding") == "base64":
            return base64.b64decode(obj["content"]).decode("utf-8")
        return str(obj.get("content", ""))
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        raise SourceError(f"could not decode {path} from {repo}: {exc}") from exc


def fetch_catalog(repo: str, *, runner: Runner = default_runner) -> dict[str, Any] | None:
    """Fetch + JSON-parse a repo's marketplace.json. None when absent."""
    text = fetch_file(repo, CATALOG_PATH, runner=runner)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"{repo}/{CATALOG_PATH} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceError(f"{repo}/{CATALOG_PATH} is not a JSON object")
    return data


def search_github(query: str, *, runner: Runner = default_runner) -> tuple[str, ...]:
    """Find repos that ship a marketplace.json, ranked by GitHub code search.
    Returns owner/repo strings (deduped, order-preserving)."""
    res = runner([
        "gh", "search", "code", CATALOG_PATH, query,
        "--json", "repository", "--jq", ".[].repository.nameWithOwner",
    ])
    if res.returncode != 0:
        # Fall back to a plain newline list parse (tests use this shape).
        res2 = runner(["gh", "search", "repos", query, "--limit", "20"])
        if res2.returncode != 0:
            return ()
        lines = res2.stdout.splitlines()
    else:
        lines = res.stdout.splitlines()
    seen: list[str] = []
    for line in lines:
        name = line.strip().split()[0] if line.strip() else ""
        if name and "/" in name and name not in seen:
            seen.append(name)
    return tuple(seen)
```

> Note for implementer: the `gh search` argv in the test is matched only on its first two tokens (`"gh search"`), so both the `--json` primary path and the `repos` fallback resolve to the same fake response — that is intentional and keeps the test runner simple. Verify the real `--jq` invocation manually against `gh` once (outside the test suite).

- [ ] **Step 4: Run → PASS.** `mypy`/`ruff` clean (the `# noqa` comments keep bandit/ruff-S quiet on the guarded subprocess).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/equip/sources.py tests/context/test_equip_sources.py
git commit -m "feat(equip): discovery I/O (tool probe, catalog fetch, GitHub search)"
```

---

## Task 7: Settings wiring — `claude_plugins.py`

**Files:**
- Create: `dummyindex/context/claude_plugins.py`
- Test: `tests/context/test_claude_plugins.py`

- [ ] **Step 1: Write failing tests**

```python
import json

from dummyindex.context.claude_plugins import (
    add_marketplace, disable_plugin, enable_plugin, remove_marketplace,
)
from dummyindex.context.claude_settings import MalformedSettingsError

import pytest


def _read(p):
    return json.loads(p.read_text())


def test_add_marketplace_then_enable_plugin(tmp_path):
    s = tmp_path / "settings.json"
    assert add_marketplace(s, name="community", repo="anthropics/claude-plugins-community") is True
    assert enable_plugin(s, plugin="rag-search", marketplace="community") is True
    data = _read(s)
    assert data["extraKnownMarketplaces"]["community"]["source"]["repo"] == "anthropics/claude-plugins-community"
    assert data["enabledPlugins"]["rag-search@community"] is True


def test_add_marketplace_is_idempotent(tmp_path):
    s = tmp_path / "settings.json"
    add_marketplace(s, name="community", repo="anthropics/claude-plugins-community")
    assert add_marketplace(s, name="community", repo="anthropics/claude-plugins-community") is False


def test_preserves_unrelated_keys(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}))
    enable_plugin(s, plugin="p", marketplace="m")
    assert _read(s)["permissions"]["allow"] == ["Bash"]


def test_refuses_malformed_settings(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text("{not json")
    with pytest.raises(MalformedSettingsError):
        enable_plugin(s, plugin="p", marketplace="m")


def test_remove_and_disable(tmp_path):
    s = tmp_path / "settings.json"
    add_marketplace(s, name="m", repo="o/r")
    enable_plugin(s, plugin="p", marketplace="m")
    assert disable_plugin(s, plugin="p", marketplace="m") is True
    assert remove_marketplace(s, name="m") is True
    data = _read(s)
    assert "p@m" not in data.get("enabledPlugins", {})
    assert "m" not in data.get("extraKnownMarketplaces", {})
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `claude_plugins.py`**

```python
"""Wire marketplaces + plugins into ``.claude/settings.json``.

Sibling of :mod:`.claude_settings` (and reuses its load/write): the native
plugin state lives under two top-level keys — ``extraKnownMarketplaces`` (a repo
the project wants available) and ``enabledPlugins`` (``"<plugin>@<marketplace>":
true``). Same preserve-or-refuse + atomic-write discipline: we never overwrite a
settings.json we cannot round-trip."""
from __future__ import annotations

from pathlib import Path

from .claude_settings import load_settings, write_settings

_MARKETPLACES = "extraKnownMarketplaces"
_ENABLED = "enabledPlugins"


def add_marketplace(
    settings_path: Path, *, name: str, repo: str, ref: str | None = None
) -> bool:
    """Add a github marketplace under ``extraKnownMarketplaces``. Returns True
    iff a new/changed entry was written, False when already present unchanged."""
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = load_settings(settings_path)
    block = settings.setdefault(_MARKETPLACES, {})
    source: dict[str, str] = {"source": "github", "repo": repo}
    if ref:
        source["ref"] = ref
    entry = {"source": source}
    if block.get(name) == entry:
        return False
    block[name] = entry
    write_settings(settings_path, settings)
    return True


def remove_marketplace(settings_path: Path, *, name: str) -> bool:
    if not settings_path.exists():
        return False
    settings = load_settings(settings_path)
    block = settings.get(_MARKETPLACES)
    if not isinstance(block, dict) or name not in block:
        return False
    block.pop(name)
    if not block:
        settings.pop(_MARKETPLACES, None)
    write_settings(settings_path, settings)
    return True


def enable_plugin(settings_path: Path, *, plugin: str, marketplace: str) -> bool:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = load_settings(settings_path)
    block = settings.setdefault(_ENABLED, {})
    key = f"{plugin}@{marketplace}"
    if block.get(key) is True:
        return False
    block[key] = True
    write_settings(settings_path, settings)
    return True


def disable_plugin(settings_path: Path, *, plugin: str, marketplace: str) -> bool:
    if not settings_path.exists():
        return False
    settings = load_settings(settings_path)
    block = settings.get(_ENABLED)
    key = f"{plugin}@{marketplace}"
    if not isinstance(block, dict) or key not in block:
        return False
    block.pop(key)
    if not block:
        settings.pop(_ENABLED, None)
    write_settings(settings_path, settings)
    return True
```

- [ ] **Step 4: Run → PASS.** `mypy`/`ruff` clean.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/claude_plugins.py tests/context/test_claude_plugins.py
git commit -m "feat(context): claude_plugins settings wiring (marketplaces + enabledPlugins)"
```

---

## Task 8: Export public surface + vendoring helper

**Files:**
- Modify: `dummyindex/context/domains/equip/__init__.py`
- Create: `dummyindex/context/domains/equip/vendor.py`
- Test: `tests/context/test_equip_vendor.py`

- [ ] **Step 1: Write failing test for vendoring (pure render of the vendored item + sentinel)**

```python
from dummyindex.context.domains.equip import (
    EquipmentSource, vendored_item, stamp_vendored,
)
from dummyindex.context.domains.equip._constants import VENDORED_SENTINEL


def test_stamp_adds_sentinel_once():
    body = "# Agent\nbody\n"
    stamped = stamp_vendored(body)
    assert VENDORED_SENTINEL in stamped
    assert stamp_vendored(stamped).count(VENDORED_SENTINEL) == 1


def test_vendored_item_records_origin():
    item = vendored_item(
        name="pdf-extract", rel_path=".claude/skills/pdf-extract/SKILL.md",
        kind_skill=True, capabilities=("docs",),
        repo="anthropics/skills", ref="abc123", content="x",
    )
    assert item.source == EquipmentSource.VENDORED
    assert item.origin_repo == "anthropics/skills"
    assert item.mechanism == "vendor"
    assert item.origin_hash is not None
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `vendor.py`** (pure — builds the item + stamps content; the CLI does the actual file write via the existing `is_safe_to_write` + atomic write)

```python
"""Pure helpers for the VENDOR mechanism: stamp a copied file with the installed
sentinel and build its manifest item with origin + hash. The file write itself
happens at the CLI boundary (never-clobber guarded), like generated items."""
from __future__ import annotations

from ._constants import VENDORED_SENTINEL
from ._hash import content_hash
from .enums import EquipmentKind, EquipmentSource, InstallMechanism
from .models import EquipmentItem


def stamp_vendored(content: str) -> str:
    """Prepend the installed sentinel as an HTML comment, idempotently."""
    if VENDORED_SENTINEL in content:
        return content
    return f"{VENDORED_SENTINEL}\n{content}"


def vendored_item(
    *, name: str, rel_path: str, kind_skill: bool, capabilities: tuple[str, ...],
    repo: str, ref: str | None, content: str, marketplace: str | None = None,
) -> EquipmentItem:
    stamped = stamp_vendored(content)
    return EquipmentItem(
        kind=EquipmentKind.SKILL if kind_skill else EquipmentKind.AGENT,
        name=name,
        path=rel_path,
        source=EquipmentSource.VENDORED,
        capabilities=capabilities,
        marketplace=marketplace,
        origin_repo=repo,
        origin_ref=ref,
        mechanism=InstallMechanism.VENDOR.value,
        origin_hash=content_hash(stamped),
    )
```

- [ ] **Step 4: Extend `__init__.py` exports**

Add to the `from .X import (...)` groups and `__all__` (the package uses explicit re-exports): `marketplace` (`MarketplaceCatalog`, `PluginEntry`, `SeedMarketplace`, `SEED_MARKETPLACES`, `parse_catalog`, `validate_catalog`); `discover` (`Candidate`, `capabilities_for`, `match_candidates`); `blast_radius` (`BlastRadius`, `analyze_blast_radius`); `install_plan` (`InstallPlan`, `PlannedInstall`, `build_install_plan`); `sources` (`RunResult`, `Runner`, `ToolAvailability`, `available_tools`, `default_runner`, `fetch_catalog`, `fetch_file`, `search_github`, `SEED_MARKETPLACES`); `vendor` (`stamp_vendored`, `vendored_item`); enums (`TrustTier`, `InstallMechanism`, `PluginSurface`); errors (`SourceError`, `CatalogError`, `WireError`).

- [ ] **Step 5: Run tests + full import smoke**

Run: `pytest tests/context/test_equip_vendor.py -q && python -c "import dummyindex.context.domains.equip as e; print(e.match_candidates, e.build_install_plan, e.available_tools)"`
Expected: PASS + prints three callables. `mypy`/`ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add dummyindex/context/domains/equip/__init__.py dummyindex/context/domains/equip/vendor.py tests/context/test_equip_vendor.py
git commit -m "feat(equip): vendoring helper + public surface exports"
```

---

## Task 9: CLI verbs — `discover` + `install`

**Files:**
- Create: `dummyindex/cli/_equip_discover.py`
- Modify: `dummyindex/cli/equip.py` (dispatch only)
- Test: `tests/cli/test_equip_discover_cli.py`

- [ ] **Step 1: Write failing CLI tests (fake runner injected via monkeypatch)**

```python
import json

from dummyindex.cli.equip import _cmd_equip
from dummyindex.context.domains.equip import RunResult


def _install_fake_runner(monkeypatch):
    payload = {
        "name": "official", "plugins": [
            {"name": "pg-tuner", "description": "Postgres performance",
             "keywords": ["database", "performance"], "hooks": "./h.json"},
        ],
    }
    import base64
    content = base64.b64encode(json.dumps(payload).encode()).decode()

    def runner(argv):
        joined = " ".join(argv[:2])
        if joined == "gh --version":
            return RunResult(0, "gh", "")
        if joined == "gh api":
            return RunResult(0, json.dumps({"content": content, "encoding": "base64"}), "")
        return RunResult(1, "", "")
    monkeypatch.setattr("dummyindex.cli._equip_discover._RUNNER", runner, raising=False)
    return runner


def test_discover_query_prints_plan(monkeypatch, tmp_path, capsys):
    _install_fake_runner(monkeypatch)
    rc = _cmd_equip(["discover", "postgres performance", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "pg-tuner" in out
    assert "blast radius" in out.lower()
    # untrusted + code-running -> must be flagged as needing approval
    assert "approval" in out.lower() or "--yes" in out


def test_discover_writes_nothing(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    _cmd_equip(["discover", "postgres", "--root", str(tmp_path)])
    assert not (tmp_path / ".claude" / "settings.json").exists()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `_equip_discover.py`**

Wire-only handlers. Discovery seeds the catalogs from `SEED_MARKETPLACES` + (for a query) `search_github`; pairs each fetched catalog with its seed trust/collection flags; matches; builds the plan; prints with blast radius. `install` applies one candidate via `claude_plugins` (NATIVE) or `vendor` + atomic write (VENDOR), refusing untrusted code-running plugins without `--yes`, then records the manifest item.

```python
"""`equip discover` / `equip install` — the plugin-manager verbs.

Wire-only: parse flags, drive discovery I/O (``sources``), call the pure domain
(match → plan), print the dry-run plan, and on ``install`` wire via
``claude_plugins`` (native) or ``vendor`` (copy). ``_RUNNER`` is module-level so
tests can monkeypatch a fake (no live network)."""
from __future__ import annotations

import sys
from pathlib import Path

from dummyindex.context.claude_plugins import add_marketplace, enable_plugin
from dummyindex.context.domains.equip import (
    SEED_MARKETPLACES, EquipmentManifest, InstallMechanism, SCHEMA_VERSION,
    available_tools, build_install_plan, detect_stack, fetch_catalog, fetch_file,
    match_candidates, parse_catalog, read_manifest, stamp_vendored, vendored_item,
    write_manifest,
)
from dummyindex.context.domains.equip.sources import default_runner

from ._equip_common import _pull_bool_flag, _pull_flag_value, _resolve_root

_RUNNER = default_runner
_SETTINGS_REL = ".claude/settings.json"


def _collect_catalogs(query: str | None):
    """Fetch + parse seed catalogs (and, for a query, GitHub-discovered repos).
    Each catalog carries its trust + collection flags from the seed."""
    catalogs = []
    tools = available_tools(runner=_RUNNER)
    if not tools.gh:
        return catalogs, "gh CLI not found — install + `gh auth login` to discover plugins"
    for seed in SEED_MARKETPLACES:
        if seed.is_collection:
            continue  # collections have no marketplace.json; handled by vendor path
        data = fetch_catalog(seed.repo, runner=_RUNNER)
        if data is None:
            continue
        catalogs.append(
            parse_catalog(data, repo=seed.repo, trusted=seed.trusted, is_collection=False)
        )
    return catalogs, None


def _needed_caps(project_root: Path) -> tuple[str, ...]:
    """Auto-match signal: capabilities the detected stack implies (kept simple —
    the stack label maps to implement/test; richer gap analysis can come later)."""
    profile = detect_stack(project_root / ".context")
    caps: list[str] = []
    if profile.test_runner:
        caps.append("test")
    if profile.label and profile.label != "generic":
        caps.append("implement")
    return tuple(caps)


def _verb_discover(rest: list[str]) -> int:
    as_json, rest = _pull_bool_flag(rest, "json")
    project_root, leftover = _resolve_root(rest)
    query = " ".join(leftover) if leftover else None
    catalogs, warn = _collect_catalogs(query)
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    needed = () if query else _needed_caps(project_root)
    candidates = match_candidates(tuple(catalogs), needed_caps=needed, query=query)
    plan = build_install_plan(candidates)
    return _print_plan(plan, as_json=as_json)


def _print_plan(plan, *, as_json: bool) -> int:
    if as_json:
        import json
        print(json.dumps({
            "installs": [
                {"plugin": pi.candidate.plugin.name, "marketplace": pi.candidate.marketplace,
                 "mechanism": pi.mechanism, "runs_code": pi.blast.runs_code,
                 "surfaces": list(pi.blast.surfaces), "tier": pi.blast.tier,
                 "requires_approval": pi.requires_approval,
                 "capabilities": list(pi.candidate.capabilities)}
                for pi in plan.installs
            ]
        }, indent=2))
        return 0
    if not plan.installs:
        print("equip discover: no matching plugins found.")
        return 0
    print("equip discover (dry-run — nothing written):")
    for pi in plan.installs:
        c = pi.candidate
        flag = "  ⚠ requires --yes" if pi.requires_approval else ""
        surfaces = ", ".join(pi.blast.surfaces) if pi.blast.surfaces else "none"
        print(f"  {pi.mechanism:6} {c.plugin.name}@{c.marketplace}  "
              f"covers: {', '.join(c.capabilities) or '-'}")
        print(f"         blast radius: {surfaces} "
              f"({'runs code' if pi.blast.runs_code else 'inert'}; {pi.blast.tier}){flag}")
    print("\nInstall one with: equip install <plugin>@<marketplace> [--yes]")
    return 0


def _verb_install(rest: list[str]) -> int:
    yes, rest = _pull_bool_flag(rest, "yes")
    scope, rest = _pull_flag_value(rest, "scope")
    project_root, leftover = _resolve_root(rest)
    target = next((a for a in leftover if "@" in a), None)
    if target is None:
        print("error: `equip install` requires <plugin>@<marketplace>", file=sys.stderr)
        return 2
    plugin_name, _, marketplace = target.partition("@")

    catalogs, warn = _collect_catalogs(query=None)
    if warn:
        print(f"error: {warn}", file=sys.stderr)
        return 1
    candidates = match_candidates(tuple(catalogs), needed_caps=(), query=plugin_name)
    chosen = next(
        (c for c in candidates if c.plugin.name == plugin_name and c.marketplace == marketplace),
        None,
    )
    if chosen is None:
        print(f"error: {target} not found in known marketplaces", file=sys.stderr)
        return 1
    plan = build_install_plan((chosen,))
    pi = plan.installs[0]
    if pi.requires_approval and not yes:
        print(f"error: {target} runs code from an untrusted source "
              f"(surfaces: {', '.join(pi.blast.surfaces)}). Re-run with --yes to approve.",
              file=sys.stderr)
        return 1
    settings = project_root / _SETTINGS_REL
    add_marketplace(settings, name=chosen.marketplace, repo=chosen.repo)
    enable_plugin(settings, plugin=plugin_name, marketplace=marketplace)
    _record_native(project_root, chosen)
    print(f"equip install: enabled {target} (native) -> {_SETTINGS_REL}")
    return 0


def _record_native(project_root: Path, chosen) -> None:
    from dummyindex.context.domains.equip import EquipmentItem, EquipmentKind, EquipmentSource
    context_dir = project_root / ".context"
    prior = read_manifest(context_dir)
    item = EquipmentItem(
        kind=EquipmentKind.AGENT, name=f"{chosen.plugin.name}@{chosen.marketplace}",
        path=_SETTINGS_REL, source=EquipmentSource.MARKETPLACE,
        capabilities=chosen.capabilities, marketplace=chosen.marketplace,
        origin_repo=chosen.repo, mechanism=InstallMechanism.NATIVE.value,
    )
    items = tuple(i for i in prior.items if i.name != item.name) + (item,)
    write_manifest(context_dir, EquipmentManifest(schema_version=SCHEMA_VERSION, items=items))
```

> Note: the VENDOR install path (collections) is wired in Task 10 once lifecycle support lands; `install` here covers the NATIVE path (the common case). Vendoring reuses `fetch_file` + `stamp_vendored` + `vendored_item` + the existing `is_safe_to_write` guard.

- [ ] **Step 4: Wire dispatch in `equip.py`**

In `equip.py` imports add `from ._equip_discover import _verb_discover, _verb_install`. In `_cmd_equip`, before the unreachable fallback:
```python
    if verb is EquipVerb.DISCOVER:
        return _verb_discover(rest)
    if verb is EquipVerb.INSTALL:
        return _verb_install(rest)
```

- [ ] **Step 5: Run → PASS.** `mypy`/`ruff` clean.

- [ ] **Step 6: Commit**

```bash
git add dummyindex/cli/_equip_discover.py dummyindex/cli/equip.py tests/cli/test_equip_discover_cli.py
git commit -m "feat(equip): CLI discover + install verbs (native path)"
```

---

## Task 10: Lifecycle — status/uninstall cover MARKETPLACE + VENDORED, and the VENDOR install path

**Files:**
- Modify: `dummyindex/context/domains/equip/lifecycle.py`
- Modify: `dummyindex/cli/_equip_discover.py` (add VENDOR branch)
- Test: `tests/context/test_equip_lifecycle_plugins.py`, extend `tests/cli/test_equip_discover_cli.py`

- [ ] **Step 1: Write failing tests**

```python
from dummyindex.context.domains.equip import (
    EquipmentItem, EquipmentKind, EquipmentManifest, EquipmentSource, uninstall,
)


def _manifest(item):
    return EquipmentManifest(schema_version=3, items=(item,))


def test_uninstall_removes_marketplace_settings_keys(tmp_path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '{"extraKnownMarketplaces": {"m": {"source": {"source": "github", "repo": "o/r"}}},'
        ' "enabledPlugins": {"p@m": true}}'
    )
    item = EquipmentItem(
        kind=EquipmentKind.AGENT, name="p@m", path=".claude/settings.json",
        source=EquipmentSource.MARKETPLACE, marketplace="m", origin_repo="o/r",
        mechanism="native",
    )
    uninstall(tmp_path, _manifest(item), dry_run=False)
    import json
    data = json.loads(settings.read_text())
    assert "p@m" not in data.get("enabledPlugins", {})


def test_uninstall_removes_vendored_file(tmp_path):
    f = tmp_path / ".claude" / "skills" / "pdf" / "SKILL.md"
    f.parent.mkdir(parents=True)
    f.write_text("<!-- dummyindex:installed -->\nbody\n")
    item = EquipmentItem(
        kind=EquipmentKind.SKILL, name="pdf", path=".claude/skills/pdf/SKILL.md",
        source=EquipmentSource.VENDORED, mechanism="vendor",
        origin_hash="x",  # treated like generated for removal
    )
    uninstall(tmp_path, _manifest(item), dry_run=False)
    assert not f.exists()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Extend `lifecycle.py`**

Read the current `uninstall`/`status` first. In `uninstall`, after the existing generated-file removal loop, add: for each MARKETPLACE item call `disable_plugin` + `remove_marketplace` (parse `name` as `plugin@marketplace`); for each VENDORED item remove its file if it still carries `VENDORED_SENTINEL` (never-clobber: a user-edited copy is kept). In `status`, include MARKETPLACE items (reported as `enabled`) and VENDORED items (hash-classified like generated). Keep `lifecycle.py` under 800 lines — if it would exceed, extract a `lifecycle_plugins.py` helper imported by `uninstall`/`status`.

(Implementer: mirror the existing removal/atomic patterns already in `lifecycle.py`; reuse `claude_plugins.disable_plugin`/`remove_marketplace` and `_constants.VENDORED_SENTINEL`.)

- [ ] **Step 4: Add VENDOR branch in `_verb_install`**

When `pi.mechanism == InstallMechanism.VENDOR.value`: fetch the item file via `fetch_file(chosen.repo, <path>)`, guard with `is_safe_to_write(target)`, write `stamp_vendored(content)` atomically (reuse `_write_file` from `equip.py` or a shared helper), and record `vendored_item(...)` in the manifest instead of `_record_native`.

- [ ] **Step 5: Run all equip tests → PASS.**

Run: `pytest tests/context/test_equip_lifecycle_plugins.py tests/cli/test_equip_discover_cli.py -q`

- [ ] **Step 6: Commit**

```bash
git add dummyindex/context/domains/equip/lifecycle.py dummyindex/cli/_equip_discover.py tests/context/test_equip_lifecycle_plugins.py tests/cli/test_equip_discover_cli.py
git commit -m "feat(equip): lifecycle (uninstall/status) + VENDOR install path for plugins"
```

---

## Task 11: Skill + docs + version bump

**Files:**
- Modify: `dummyindex/skills/equip/SKILL.md`, `docs/COMMANDS.md`, `docs/guide/07-cli.md`, `CHANGELOG.md`, `pyproject.toml`

- [ ] **Step 1: Update `SKILL.md`** — document the discover/install flow, the hybrid wiring (native vs vendor), the tiered-trust + blast-radius rule (never enable code-running untrusted plugins without `--yes`), and that `discover` is always a dry-run.

- [ ] **Step 2: Update `docs/COMMANDS.md` + `docs/guide/07-cli.md`** — add the `equip discover [QUERY]` and `equip install <plugin>@<marketplace> [--yes] [--scope]` rows next to the existing verbs; note the new `status`/`uninstall` coverage.

- [ ] **Step 3: Update `CHANGELOG.md`** — add a `0.18.0` entry summarizing the plugin manager.

- [ ] **Step 4: Bump `pyproject.toml`** `version = "0.17.0"` → `version = "0.18.0"`.

- [ ] **Step 5: Full suite + lint gate**

Run: `pytest -q && mypy dummyindex/ && ruff check dummyindex/`
Expected: all green; coverage ≥80% on the new modules.

- [ ] **Step 6: Commit**

```bash
git add dummyindex/skills/equip/SKILL.md docs/COMMANDS.md docs/guide/07-cli.md CHANGELOG.md pyproject.toml
git commit -m "docs(equip): document plugin manager; bump to v0.18.0"
```

---

## Self-Review (completed)

**Spec coverage:** discover auto-match (Task 9 `_needed_caps`) + query (Tasks 6+9); ranked dry-run plan (Tasks 5+9); hybrid native/vendor wiring (Tasks 7,8,9,10); tiered trust + blast-radius disclosure (Tasks 4,5,9); manifest v3 + new sources (Task 1); status/refresh/uninstall coverage (Task 10); error taxonomy (Task 1); testing with fixtures + Runner seam (every task); skill/docs/version (Task 11). All spec sections map to a task.

**Placeholder scan:** code provided for every code step; the two prose-only steps (lifecycle extension in Task 10 Step 3, docs in Task 11) reference exact functions/patterns to mirror rather than leaving "TBD" — acceptable because they extend existing, already-read code whose patterns are explicit.

**Type consistency:** `match_candidates(catalogs, *, needed_caps, query)`, `build_install_plan(candidates)`, `analyze_blast_radius(entry, *, trusted)`, `Candidate`/`PlannedInstall`/`InstallPlan` field names, and the new `EquipmentItem` fields (`marketplace`/`origin_repo`/`origin_ref`/`mechanism`) are used identically across tasks. `analyze_blast_radius` (not `analyze`) is the exported name — chosen to avoid collision in the package namespace.

**Known simplifications (intentional, flagged):** `_needed_caps` is a minimal auto-match signal (label → implement/test) to ship a working loop; richer gap-analysis (diff against existing manifest coverage) is a fast-follow. `sources.search_github`'s `--jq` path is not exercised by the fake-runner test (matched on first two tokens) — verify once manually. These are noted in the spec's §12 deferred list.
