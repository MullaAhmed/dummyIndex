"""Blast-radius analysis: which surfaces a plugin declares and whether any of
them run code. Pure; no I/O. The safety spine of the install plan (spec §7)."""
from __future__ import annotations

from dataclasses import dataclass

from .enums import PluginSurface, TrustTier
from .marketplace import PluginEntry

# Surfaces that execute code when a plugin is enabled. Inert surfaces
# (agent/skill/command) are markdown — they never run code on their own.
_CODE_SURFACES: frozenset[str] = frozenset(
    {
        PluginSurface.HOOK.value,
        PluginSurface.MCP.value,
        PluginSurface.LSP.value,
        PluginSurface.BIN.value,
    }
)


@dataclass(frozen=True)
class BlastRadius:
    """What enabling a plugin would grant: its declared surfaces, whether any
    run code, and the trust tier of its source."""

    surfaces: tuple[str, ...]
    runs_code: bool
    tier: TrustTier


def analyze_blast_radius(entry: PluginEntry, *, trusted: bool) -> BlastRadius:
    surfaces = tuple(entry.declared_surfaces)
    runs_code = any(s in _CODE_SURFACES for s in surfaces)
    tier = TrustTier.TRUSTED if trusted else TrustTier.UNTRUSTED
    return BlastRadius(surfaces=surfaces, runs_code=runs_code, tier=tier)
