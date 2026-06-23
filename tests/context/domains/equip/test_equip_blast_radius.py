"""Blast-radius analysis (pure)."""

from dummyindex.context.domains.equip import (
    BlastRadius,
    PluginEntry,
    TrustTier,
    analyze_blast_radius,
)


def test_inert_plugin_does_not_run_code():
    br = analyze_blast_radius(PluginEntry(name="docs-helper"), trusted=False)
    assert isinstance(br, BlastRadius)
    assert br.runs_code is False
    assert br.surfaces == ()
    assert br.tier == TrustTier.UNTRUSTED.value


def test_hook_plugin_runs_code_and_keeps_surfaces():
    br = analyze_blast_radius(
        PluginEntry(name="pg", declared_surfaces=("hook", "mcp")), trusted=True
    )
    assert br.runs_code is True
    assert set(br.surfaces) == {"hook", "mcp"}
    assert br.tier == TrustTier.TRUSTED.value
    assert br.tier is TrustTier.TRUSTED  # field is the enum, not a bare str


def test_bin_surface_runs_code():
    br = analyze_blast_radius(
        PluginEntry(name="tool", declared_surfaces=("bin",)), trusted=False
    )
    assert br.runs_code is True
